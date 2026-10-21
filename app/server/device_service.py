import datetime
import hashlib
import secrets
import threading
from typing import Optional, Tuple, List

from app.core.database import get_db_connection
from app.core.logger import get_logger

logger = get_logger("IssueSlipApp.DeviceService")


class DeviceService:
    _lock = threading.RLock()  # re-entrant: get_active_pairing_code() -> generate_pairing_code()
    _active_pairing_code: Optional[str] = None
    _pairing_code_expiry: Optional[datetime.datetime] = None
    _failed_attempts: int = 0
    MAX_FAILED_ATTEMPTS = 5

    @classmethod
    def generate_pairing_code(cls, expiry_minutes: int = 15) -> str:
        """Generate a random 6-digit pairing code with expiration."""
        with cls._lock:
            code = f"{100000 + secrets.randbelow(900000)}"
            cls._failed_attempts = 0
            cls._active_pairing_code = code
            cls._pairing_code_expiry = datetime.datetime.utcnow() + datetime.timedelta(minutes=expiry_minutes)
            logger.info(f"Generated new mobile pairing code: {code} (expires in {expiry_minutes}m)")
            return code

    @classmethod
    def get_active_pairing_code(cls) -> str:
        with cls._lock:
            if cls._active_pairing_code and cls._pairing_code_expiry:
                if datetime.datetime.utcnow() < cls._pairing_code_expiry:
                    return cls._active_pairing_code
            return cls.generate_pairing_code()

    @classmethod
    def hash_token(cls, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def verify_and_pair(cls, code: str, device_name: str) -> Tuple[bool, str, Optional[str], Optional[dict]]:
        """
        Verify pairing code and register device, generating a long-lived bearer token.
        Returns (success, message, token, device_info).
        """
        clean_code = str(code).strip()
        name = str(device_name).strip() or "Mobile Scanner"

        with cls._lock:
            if not cls._active_pairing_code or not cls._pairing_code_expiry:
                return False, "No active pairing code. Please generate one on desktop.", None, None

            if datetime.datetime.utcnow() > cls._pairing_code_expiry:
                cls._active_pairing_code = None
                return False, "Pairing code has expired. Please refresh the code on desktop.", None, None

            if not secrets.compare_digest(clean_code, cls._active_pairing_code):
                cls._failed_attempts += 1
                if cls._failed_attempts >= cls.MAX_FAILED_ATTEMPTS:
                    # Too many wrong guesses: burn the code so it cannot be brute-forced.
                    cls._active_pairing_code = None
                    cls._pairing_code_expiry = None
                    cls._failed_attempts = 0
                    logger.warning("Pairing code invalidated after too many failed attempts.")
                    return False, "Too many wrong attempts. Please generate a new pairing code on desktop.", None, None
                return False, "Invalid pairing code. Please check the code displayed on desktop.", None, None

            # Generate long-lived cryptographically secure token
            raw_token = secrets.token_hex(32)
            token_hash = cls.hash_token(raw_token)

            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO devices (name, token_hash, created_at, last_seen, revoked)
                        VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0);
                    """, (name, token_hash))
                    device_id = cursor.lastrowid
                    conn.commit()

                    device_info = {
                        "id": device_id,
                        "name": name,
                        "created_at": datetime.datetime.utcnow().isoformat(),
                        "revoked": 0
                    }
                    logger.info(f"Device successfully paired: #{device_id} '{name}'")
                    # Pairing codes are single-use: burn it so nobody else can reuse it.
                    cls._active_pairing_code = None
                    cls._pairing_code_expiry = None
                    cls._failed_attempts = 0
                    return True, "Pairing successful.", raw_token, device_info
            except Exception as exc:
                logger.error(f"Error registering device: {exc}")
                return False, f"Database error: {exc}", None, None

    @classmethod
    def validate_token(cls, token: str) -> Optional[dict]:
        """Validate bearer token, check revocation, and update last_seen timestamp."""
        if not token:
            return None
        token_hash = cls.hash_token(token.strip())

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name, created_at, last_seen, revoked
                    FROM devices
                    WHERE token_hash = ?;
                """, (token_hash,))
                row = cursor.fetchone()
                if not row:
                    return None
                if row["revoked"] == 1:
                    logger.warning(f"Rejected revoked device attempt: #{row['id']} '{row['name']}'")
                    return None

                # Update last_seen
                cursor.execute("""
                    UPDATE devices
                    SET last_seen = CURRENT_TIMESTAMP
                    WHERE id = ?;
                """, (row["id"],))
                conn.commit()

                return dict(row)
        except Exception as exc:
            logger.error(f"Token validation error: {exc}")
            return None

    @classmethod
    def get_paired_devices(cls) -> List[dict]:
        """List all paired mobile devices for desktop UI management."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name, created_at, last_seen, revoked
                    FROM devices
                    ORDER BY id DESC;
                """)
                return [dict(r) for r in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"Error fetching devices list: {exc}")
            return []

    # Alias for list_devices
    list_devices = get_paired_devices

    @classmethod
    def revoke_device(cls, device_id: int) -> Tuple[bool, str]:
        """Immediately revoke a paired phone device."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE devices
                    SET revoked = 1
                    WHERE id = ?;
                """, (device_id,))
                conn.commit()
                logger.info(f"Device #{device_id} has been revoked.")
                return True, f"Device #{device_id} has been revoked successfully."
        except Exception as exc:
            logger.error(f"Error revoking device #{device_id}: {exc}")
            return False, f"Error revoking device: {exc}"

    @classmethod
    def unrevoke_device(cls, device_id: int) -> bool:
        """Un-revoke / re-enable a paired phone device."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE devices
                    SET revoked = 0, last_seen = CURRENT_TIMESTAMP
                    WHERE id = ?;
                """, (device_id,))
                conn.commit()
                logger.info(f"Device #{device_id} has been re-enabled.")
                return True
        except Exception as exc:
            logger.error(f"Error re-enabling device #{device_id}: {exc}")
            return False

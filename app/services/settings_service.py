from datetime import datetime
from app.core.database import get_db_connection
from app.core.logger import get_logger

logger = get_logger("IssueSlipApp.SettingsService")


class SettingsService:
    @staticmethod
    def get_setting(key: str, default: str = "") -> str:
        """Fetch a single configuration setting by key."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM app_settings WHERE key = ?;", (key,))
                row = cursor.fetchone()
                if row:
                    return str(row["value"])
        except Exception as exc:
            logger.error(f"Failed to read setting '{key}': {exc}")
        return default

    @staticmethod
    def set_setting(key: str, value: str, category: str = "general", description: str = "") -> bool:
        """Update or insert a configuration setting."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO app_settings (key, value, category, description, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP;
                """, (key, str(value), category, description))
                logger.info(f"Setting updated: {key}='{value}'")
                return True
        except Exception as exc:
            logger.error(f"Failed to set setting '{key}': {exc}")
            return False

    @classmethod
    def get_all_settings(cls) -> dict[str, str]:
        """Fetch all settings as a dictionary."""
        settings = {}
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM app_settings;")
                for row in cursor.fetchall():
                    settings[row["key"]] = str(row["value"])
        except Exception as exc:
            logger.error(f"Failed to read all settings: {exc}")
        return settings

    @classmethod
    def save_settings_dict(cls, data: dict[str, str]) -> tuple[bool, str]:
        """Atomically persist multiple settings to database."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for key, val in data.items():
                    cursor.execute("""
                        INSERT INTO app_settings (key, value, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET
                            value = excluded.value,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (key, str(val)))
            logger.info(f"Successfully saved {len(data)} settings.")
            return True, "Application settings saved successfully."
        except Exception as exc:
            msg = f"Failed to save settings: {exc}"
            logger.error(msg)
            return False, msg

    @classmethod
    def get_departments(cls) -> list[str]:
        """Return configured departments as a clean list of trimmed strings."""
        raw = cls.get_setting("departments", "")
        if not raw:
            return []
        return [dept.strip() for dept in raw.split(",") if dept.strip()]

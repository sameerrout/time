import datetime
import math
import uuid
from typing import Optional, Tuple, List, Dict

from app.core.database import get_db_connection
from app.core.logger import get_logger
from app.services.material_service import MaterialService
from app.services.settings_service import SettingsService

logger = get_logger("IssueSlipApp.ScanService")


class ScanService:
    @staticmethod
    def parse_qr_text(raw_qr: str) -> Tuple[str, str, str]:
        """
        Parse QR code content supporting both formats:
          a) Plain material code, e.g. "1001NM210010BL421"
          b) Pipe-delimited "CODE|NAME|UOM", e.g. "1001NM210010BL421|INM 210 LTRS...|EA"
        Returns (code, name, uom).
        """
        text = str(raw_qr).strip()
        if "|" in text:
            parts = [p.strip() for p in text.split("|")]
            code = parts[0]
            name = parts[1] if len(parts) > 1 else ""
            uom = parts[2] if len(parts) > 2 else ""
            return code, name, uom
        return text, "", ""

    @staticmethod
    def _num(payload: dict, key: str, default: float) -> float:
        """
        Parse an optional numeric payload field.
        Missing / null / empty -> default. Garbage, NaN or infinity -> ValueError.
        (A legitimate 0 is kept as 0, it is NOT replaced by the default.)
        """
        raw = payload.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return default
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"'{key}' must be a number, got {raw!r}")
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"'{key}' must be a finite number")
        return value

    @classmethod
    def _reject(cls, device: dict, event_id: str, mode: str, reason: str, *,
                material_code: str = "", material_name: str = "", uom: str = "",
                qty: float = 0.0, required_qty: float = 0.0, unit_price: float = 0.0,
                gst_pct: float = 18.0, total_price: float = 0.0, purpose: str = "") -> Tuple[bool, str, dict]:
        """Persist a rejected event and build the standard rejection response."""
        logger.warning(f"Scan rejected for device #{device['id']} ({device['name']}): {reason}")
        cls._record_event(
            event_id=event_id, device_id=device["id"], device_name=device["name"],
            mode=mode, material_code=material_code, material_name=material_name, uom=uom,
            qty=qty, required_qty=required_qty, unit_price=unit_price, gst_pct=gst_pct,
            total_price=total_price, purpose=purpose, status="rejected", reject_reason=reason
        )
        return False, reason, {"event_id": event_id, "status": "rejected", "reject_reason": reason}

    @classmethod
    def process_scan(cls, device: dict, payload: dict) -> Tuple[bool, str, dict]:
        """
        Process incoming mobile scan event with strict idempotency and validation.
        Returns (success, message, result_dict).

        Lifecycle of a scan event:
          pending  -> received & validated by the server, waiting for the desktop to use it
          applied  -> the desktop really consumed it (added to the issue slip / posted inward)
          rejected -> refused (validation failed, or the desktop could not use it)
        The desktop calls mark_event_applied() / mark_event_rejected() to finish the cycle,
        so a scan can never be reported as 'applied' while it was silently dropped.

        result_dict["duplicate"] is True when the event_id was already processed; callers must
        NOT forward duplicates to the desktop again (that would double-count the quantity).
        """
        event_id = str(payload.get("event_id") or uuid.uuid4()).strip()
        mode = str(payload.get("mode", "")).strip().upper()
        raw_code = str(payload.get("material_code", "")).strip()

        # Parse QR text format (plain code vs CODE|NAME|UOM)
        parsed_code, parsed_name, parsed_uom = cls.parse_qr_text(raw_code)
        mat_code = parsed_code

        # Validate mode
        if mode not in ("ISSUE", "RECEIVE"):
            return False, f"Invalid mode '{mode}'. Must be ISSUE or RECEIVE.", {
                "event_id": event_id, "status": "rejected", "reject_reason": "Invalid mode"
            }

        # Idempotency: has this event_id already been processed?
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT event_id, status, reject_reason, mode, material_code, qty, applied_at
                    FROM scan_events
                    WHERE event_id = ?;
                """, (event_id,))
                existing = cursor.fetchone()
                if existing:
                    logger.info(f"Duplicate scan event received: {event_id} (already {existing['status']})")
                    result = dict(existing)
                    result["duplicate"] = True
                    return True, f"Event already processed with status: {existing['status']}", result
        except Exception as exc:
            logger.error(f"Error checking event idempotency: {exc}")

        # Parse numeric fields safely (bad input -> clean rejection, never an HTTP 500)
        try:
            qty = cls._num(payload, "qty", 1.0)
            required_qty = cls._num(payload, "required_qty", 0.0)
            gst_pct = cls._num(payload, "gst_pct", 18.0)
            payload_price = cls._num(payload, "unit_price", -1.0)  # -1 = "not supplied"
            total_price = cls._num(payload, "total_price", 0.0)
        except ValueError as exc:
            return cls._reject(device, event_id, mode, f"Invalid numeric value: {exc}",
                               material_code=mat_code, material_name=parsed_name, uom=parsed_uom)
        purpose = str(payload.get("purpose") or "").strip()

        # Resolve material against database
        mat = MaterialService.get_by_code(mat_code)
        if not mat:
            return cls._reject(device, event_id, mode, f"Unknown material code: '{mat_code}'.",
                               material_code=mat_code, material_name=parsed_name, uom=parsed_uom,
                               qty=max(qty, 0.0), required_qty=required_qty, purpose=purpose)

        common = dict(material_code=mat["material_code"], material_name=mat["name"], uom=mat["unit"],
                      purpose=purpose)

        if qty <= 0:
            return cls._reject(device, event_id, mode, "Invalid quantity: Quantity must be greater than zero.",
                               **common)
        if required_qty < 0:
            return cls._reject(device, event_id, mode, "Invalid required quantity: cannot be negative.",
                               qty=qty, **common)
        if not (0.0 <= gst_pct <= 100.0):
            return cls._reject(device, event_id, mode, "Invalid GST %: must be between 0 and 100.",
                               qty=qty, **common)

        current_stock = float(mat.get("current_stock") or 0.0)

        # Do not allow issuing more than physical stock (unless the setting permits it)
        if mode == "ISSUE" and qty > current_stock:
            allow_negative = SettingsService.get_setting("allow_negative_stock", "0").strip() == "1"
            if not allow_negative:
                return cls._reject(
                    device, event_id, mode,
                    f"Insufficient stock for '{mat['material_code']}': requested {qty:g}, available {current_stock:g}.",
                    qty=qty, required_qty=required_qty, **common)

        # Price: ISSUE always uses the master price from the database (the phone must not be
        # able to dictate it). RECEIVE may carry the actual purchase price from the phone.
        db_price = float(mat.get("unit_price") or 0.0)
        if mode == "RECEIVE" and payload_price > 0:
            unit_price = payload_price
        else:
            unit_price = db_price

        # Calculate total price (a real supplied total is respected, 0/missing is computed)
        if total_price <= 0.0 and unit_price > 0:
            subtotal = qty * unit_price
            total_price = round(subtotal + (subtotal * gst_pct / 100.0), 2)

        # Save as PENDING - the desktop confirms (applied) or rejects it afterwards
        cls._record_event(
            event_id=event_id, device_id=device["id"], device_name=device["name"], mode=mode,
            qty=qty, required_qty=required_qty, unit_price=unit_price, gst_pct=gst_pct,
            total_price=total_price, status="pending", reject_reason="", **common
        )

        event_record = {
            "event_id": event_id,
            "device_id": device["id"],
            "device_name": device["name"],
            "mode": mode,
            "material_id": mat["id"],
            "material_code": mat["material_code"],
            "material_name": mat["name"],
            "uom": mat["unit"],
            "qty": qty,
            "required_qty": required_qty,
            "unit_price": unit_price,
            "gst_pct": gst_pct,
            "total_price": total_price,
            "purpose": purpose,
            "current_stock": current_stock,
            "status": "pending",
            "reject_reason": "",
            "duplicate": False,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }

        logger.info(f"Scan received from #{device['id']} ({device['name']}): [{mode}] {mat['material_code']} x {qty:g} {mat['unit']} (pending desktop confirmation)")
        return True, "Scan received. Waiting for desktop confirmation.", event_record

    @classmethod
    def mark_event_applied(cls, event_id: str) -> bool:
        """Desktop confirms it really used the scan (added to slip / posted inward)."""
        return cls._finish_event(event_id, "applied", "")

    @classmethod
    def mark_event_rejected(cls, event_id: str, reason: str) -> bool:
        """Desktop could not use the scan (e.g. phone scanning OFF, slip finalized)."""
        return cls._finish_event(event_id, "rejected", (reason or "Rejected by desktop").strip())

    @classmethod
    def _finish_event(cls, event_id: str, status: str, reason: str) -> bool:
        event_id = str(event_id or "").strip()
        if not event_id:
            return False
        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE scan_events
                    SET status = ?,
                        reject_reason = ?,
                        applied_at = CASE WHEN ? = 'applied' THEN CURRENT_TIMESTAMP ELSE applied_at END
                    WHERE event_id = ? AND status = 'pending';
                """, (status, reason, status, event_id))
                changed = cur.rowcount > 0
            if changed:
                logger.info(f"Scan event {event_id} marked {status}" + (f": {reason}" if reason else ""))
            return changed
        except Exception as exc:
            logger.error(f"Could not mark scan event {event_id} as {status}: {exc}")
            return False

    @classmethod
    def _record_event(
        cls,
        event_id: str,
        device_id: int,
        device_name: str,
        mode: str,
        material_code: str,
        material_name: str = "",
        uom: str = "",
        qty: float = 0.0,
        required_qty: float = 0.0,
        unit_price: float = 0.0,
        gst_pct: float = 18.0,
        total_price: float = 0.0,
        purpose: str = "",
        status: str = "pending",
        reject_reason: str = ""
    ):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO scan_events (
                        event_id, device_id, device_name, mode, material_code,
                        material_name, uom, qty, required_qty, unit_price,
                        gst_pct, total_price, purpose, status, reject_reason,
                        created_at, applied_at
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        CURRENT_TIMESTAMP,
                        CASE WHEN ? = 'applied' THEN CURRENT_TIMESTAMP ELSE NULL END
                    )
                    ON CONFLICT(event_id) DO UPDATE SET
                        status = excluded.status,
                        reject_reason = excluded.reject_reason,
                        applied_at = excluded.applied_at;
                """, (
                    event_id, device_id, device_name, mode, material_code,
                    material_name, uom, qty, required_qty, unit_price,
                    gst_pct, total_price, purpose, status, reject_reason,
                    status
                ))
                conn.commit()
        except Exception as exc:
            logger.error(f"Error persisting scan event {event_id}: {exc}")

    @classmethod
    def get_event_status(cls, event_id: str) -> Optional[dict]:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT event_id, device_id, device_name, mode, material_code,
                           material_name, uom, qty, required_qty, unit_price,
                           gst_pct, total_price, purpose, status, reject_reason,
                           created_at, applied_at
                    FROM scan_events
                    WHERE event_id = ?;
                """, (event_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as exc:
            logger.error(f"Error fetching event {event_id}: {exc}")
            return None

    @classmethod
    def get_recent_scans(cls, limit: int = 15) -> List[dict]:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT event_id, device_id, device_name, mode, material_code,
                           material_name, uom, qty, required_qty, unit_price,
                           total_price, status, created_at
                    FROM scan_events
                    ORDER BY created_at DESC
                    LIMIT ?;
                """, (limit,))
                return [dict(r) for r in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"Error fetching recent scans: {exc}")
            return []

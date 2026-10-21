import datetime
from typing import Optional
from app.core.database import get_db_connection
from app.core.logger import get_logger
from app.services.settings_service import SettingsService

logger = get_logger("IssueSlipApp.IssueSlipService")


class IssueSlipService:
    @staticmethod
    def generate_next_slip_no() -> str:
        """Generate the next unique sequential issue slip number based on configured prefix."""
        prefix = SettingsService.get_setting("slip_prefix", "IS-").strip() or "IS-"
        today_str = datetime.datetime.now().strftime("%Y%m%d")

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM issue_slips;")
                count = cursor.fetchone()[0] + 1
                return f"{prefix}{today_str}-{count:04d}"
        except Exception:
            return f"{prefix}{today_str}-0001"

    @classmethod
    def save_draft_slip(
        cls,
        slip_data: dict,
        items: list[dict]
    ) -> tuple[bool, str, Optional[str]]:
        """
        Save or update an Issue Slip as DRAFT without deducting inventory or writing to stock ledger.
        Prevents silently overwriting an existing finalized slip.
        """
        slip_no = slip_data.get("slip_no", "").strip() or cls.generate_next_slip_no()
        department = slip_data.get("department", "").strip()
        slip_date = slip_data.get("slip_date", datetime.date.today().isoformat())
        cost_center_no = slip_data.get("cost_center_no", "").strip()
        gl_no = slip_data.get("gl_no", "").strip()
        stores_posting_no = slip_data.get("stores_posting_no", "").strip()
        store_posting_date = slip_data.get("store_posting_date", "").strip()
        reservation_no = slip_data.get("reservation_no", "").strip()
        receiver = slip_data.get("receiver", "").strip()
        purpose = slip_data.get("purpose", "").strip()
        remarks = slip_data.get("remarks", "").strip()
        created_by = slip_data.get("created_by", "Storekeeper").strip()

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Check if slip already exists
                cursor.execute("SELECT id, status FROM issue_slips WHERE slip_no = ?;", (slip_no,))
                existing = cursor.fetchone()

                if existing:
                    if existing["status"] == "FINALIZED":
                        return False, f"Issue Slip '{slip_no}' is already FINALIZED and cannot be overwritten.", None
                    slip_id = existing["id"]
                    # Update draft header
                    cursor.execute("""
                        UPDATE issue_slips
                        SET slip_date = ?, department = ?, receiver = ?, purpose = ?,
                            cost_center_no = ?, gl_no = ?, stores_posting_no = ?,
                            store_posting_date = ?, reservation_no = ?,
                            total_items = ?, remarks = ?, created_by = ?, status = 'DRAFT'
                        WHERE id = ?;
                    """, (
                        slip_date, department, receiver, purpose,
                        cost_center_no, gl_no, stores_posting_no,
                        store_posting_date, reservation_no,
                        len(items), remarks, created_by, slip_id
                    ))
                    # Clear previous line items for this draft
                    cursor.execute("DELETE FROM issue_slip_items WHERE slip_id = ?;", (slip_id,))
                else:
                    cursor.execute("""
                        INSERT INTO issue_slips (
                            slip_no, slip_date, department, receiver, purpose,
                            cost_center_no, gl_no, stores_posting_no,
                            store_posting_date, reservation_no,
                            total_items, remarks, created_by, status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT');
                    """, (
                        slip_no, slip_date, department, receiver, purpose,
                        cost_center_no, gl_no, stores_posting_no,
                        store_posting_date, reservation_no,
                        len(items), remarks, created_by
                    ))
                    slip_id = cursor.lastrowid

                # Insert items
                for idx, item in enumerate(items, start=1):
                    mat_id = item.get("material_id")
                    mat_code = item.get("material_code", "").strip()
                    mat_name = item.get("material_name", "").strip()
                    unit = item.get("unit", "PCS").strip()
                    req_qty = float(item.get("required_qty", item.get("quantity", 1.0)))
                    iss_qty = float(item.get("quantity_issued", item.get("quantity", 1.0)))
                    item_purpose = item.get("purpose", purpose).strip()
                    item_receiver = item.get("receiver_name", receiver).strip()
                    item_cc = item.get("cost_center_no", cost_center_no).strip()

                    cursor.execute("""
                        INSERT INTO issue_slip_items (
                            slip_id, material_id, material_code, material_name,
                            unit, quantity_issued, sr_no, required_qty, purpose, receiver_name, cost_center_no
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        slip_id, mat_id, mat_code, mat_name,
                        unit, iss_qty, idx, req_qty, item_purpose, item_receiver, item_cc
                    ))

                logger.info(f"Draft Issue Slip '{slip_no}' saved successfully with {len(items)} items.")
                return True, f"Draft Issue Slip '{slip_no}' saved successfully.", slip_no

        except Exception as exc:
            msg = f"Failed to save draft issue slip: {exc}"
            logger.error(msg, exc_info=True)
            return False, msg, None

    @classmethod
    def create_and_finalize_slip(
        cls,
        slip_data: dict,
        items: list[dict]
    ) -> tuple[bool, str, Optional[str]]:
        """
        Atomically finalize the issue slip, record all items, deduct physical inventory,
        and write movement logs to the stock ledger.
        Locks finalized slip against accidental duplicate posting or overwriting.
        """
        slip_no = slip_data.get("slip_no", "").strip() or cls.generate_next_slip_no()
        department = slip_data.get("department", "").strip()
        receiver = slip_data.get("receiver", "").strip()
        requester = slip_data.get("requester", "").strip()
        purpose = slip_data.get("purpose", "").strip()
        remarks = slip_data.get("remarks", "").strip()
        cost_center_no = slip_data.get("cost_center_no", "").strip()
        gl_no = slip_data.get("gl_no", "").strip()
        stores_posting_no = slip_data.get("stores_posting_no", "").strip()
        store_posting_date = slip_data.get("store_posting_date", "").strip()
        reservation_no = slip_data.get("reservation_no", "").strip()
        created_by = slip_data.get("created_by", "Storekeeper").strip()
        slip_date = slip_data.get("slip_date", datetime.date.today().isoformat())

        if not department:
            return False, "Department is required.", None
        if not items:
            return False, "At least one material item must be added to the issue slip.", None

        # If receiver is not in slip header, check if item-level receivers exist
        if not receiver:
            has_item_receiver = any(item.get("receiver_name", "").strip() for item in items)
            if not has_item_receiver:
                return False, "Receiver name is required on header or material rows.", None
            receiver = next((item.get("receiver_name", "").strip() for item in items if item.get("receiver_name", "").strip()), "Store Receiver")

        allow_negative = SettingsService.get_setting("allow_negative_stock", "0") == "1"

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # Step 0: Check if slip already exists and is finalized
                cursor.execute("SELECT id, status FROM issue_slips WHERE slip_no = ?;", (slip_no,))
                existing = cursor.fetchone()
                if existing and existing["status"] == "FINALIZED":
                    return False, f"Issue Slip '{slip_no}' is already FINALIZED. Duplicate posting is prohibited.", None

                # Step 1: Pre-validation of stock quantities
                for item in items:
                    mat_id = item.get("material_id")
                    mat_code = item.get("material_code", "").strip()
                    qty_to_issue = float(item.get("quantity_issued", item.get("quantity", 0.0)))
                    if qty_to_issue <= 0:
                        return False, f"Issued quantity for '{item.get('material_name', mat_code)}' must be greater than zero.", None

                    if mat_id:
                        cursor.execute("SELECT id, current_stock, name FROM materials WHERE id = ?;", (mat_id,))
                    else:
                        cursor.execute("SELECT id, current_stock, name FROM materials WHERE material_code = ?;", (mat_code,))

                    mat_row = cursor.fetchone()
                    if not mat_row:
                        return False, f"Material '{mat_code}' not found in database.", None

                    item["material_id"] = mat_row["id"]
                    curr_stock = float(mat_row["current_stock"])
                    if not allow_negative and qty_to_issue > curr_stock:
                        return (
                            False,
                            f"Insufficient stock for '{mat_row['name']}'. Requested: {qty_to_issue}, Available: {curr_stock}.",
                            None
                        )

                # Step 2: Insert or Update Issue Slip Header to 'FINALIZED'
                if existing:
                    slip_id = existing["id"]
                    cursor.execute("""
                        UPDATE issue_slips
                        SET slip_date = ?, department = ?, requester = ?, receiver = ?, purpose = ?,
                            cost_center_no = ?, gl_no = ?, stores_posting_no = ?,
                            store_posting_date = ?, reservation_no = ?,
                            status = 'FINALIZED', total_items = ?, remarks = ?, created_by = ?
                        WHERE id = ?;
                    """, (
                        slip_date, department, requester, receiver, purpose,
                        cost_center_no, gl_no, stores_posting_no,
                        store_posting_date, reservation_no,
                        len(items), remarks, created_by, slip_id
                    ))
                    cursor.execute("DELETE FROM issue_slip_items WHERE slip_id = ?;", (slip_id,))
                else:
                    cursor.execute("""
                        INSERT INTO issue_slips (
                            slip_no, slip_date, department, requester, receiver, purpose,
                            cost_center_no, gl_no, stores_posting_no,
                            store_posting_date, reservation_no,
                            status, total_items, remarks, created_by
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'FINALIZED', ?, ?, ?);
                    """, (
                        slip_no, slip_date, department, requester, receiver, purpose,
                        cost_center_no, gl_no, stores_posting_no,
                        store_posting_date, reservation_no,
                        len(items), remarks, created_by
                    ))
                    slip_id = cursor.lastrowid

                # Step 3: Insert Items, Deduct Stock, and Write Ledger atomically
                for idx, item in enumerate(items, start=1):
                    mat_id = item["material_id"]
                    mat_code = item["material_code"]
                    mat_name = item.get("material_name", "")
                    unit = item.get("unit", "PCS")
                    req_qty = float(item.get("required_qty", item.get("quantity", 1.0)))
                    qty_to_issue = float(item.get("quantity_issued", item.get("quantity", 1.0)))
                    item_purpose = item.get("purpose", purpose).strip()
                    item_receiver = item.get("receiver_name", receiver).strip()
                    item_cc = item.get("cost_center_no", cost_center_no).strip()

                    # Insert slip line item
                    cursor.execute("""
                        INSERT INTO issue_slip_items (
                            slip_id, material_id, material_code, material_name,
                            unit, quantity_issued, sr_no, required_qty, purpose, receiver_name, cost_center_no
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        slip_id, mat_id, mat_code, mat_name,
                        unit, qty_to_issue, idx, req_qty, item_purpose, item_receiver, item_cc
                    ))

                    # Deduct physical stock
                    cursor.execute("""
                        UPDATE materials
                        SET current_stock = current_stock - ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?;
                    """, (qty_to_issue, mat_id))

                    # Read new balance for ledger accuracy
                    cursor.execute("SELECT current_stock FROM materials WHERE id = ?;", (mat_id,))
                    new_balance = float(cursor.fetchone()["current_stock"])

                    # Record transaction in stock ledger
                    cursor.execute("""
                        INSERT INTO stock_ledger (material_id, transaction_type, quantity, balance_after, reference_no, reason)
                        VALUES (?, 'ISSUE', ?, ?, ?, ?);
                    """, (mat_id, -qty_to_issue, new_balance, slip_no, f"Issued to {department} ({item_receiver}): {item_purpose}"))

                logger.info(f"Successfully finalized Issue Slip {slip_no} with {len(items)} items.")
                return True, f"Issue Slip {slip_no} finalized and stock deducted successfully.", slip_no

        except Exception as exc:
            msg = f"Failed to finalize issue slip: {exc}"
            logger.error(msg, exc_info=True)
            return False, msg, None

    @staticmethod
    def get_issue_slip(slip_no: str) -> Optional[dict]:
        """Retrieve full details of an issue slip including line items."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM issue_slips WHERE slip_no = ?;", (slip_no,))
                slip = cursor.fetchone()
                if not slip:
                    return None

                result = dict(slip)
                cursor.execute("""
                    SELECT * FROM issue_slip_items
                    WHERE slip_id = ?
                    ORDER BY sr_no ASC, id ASC;
                """, (result["id"],))
                result["items"] = [dict(row) for row in cursor.fetchall()]
                return result
        except Exception as exc:
            logger.error(f"Error fetching issue slip '{slip_no}': {exc}")
            return None

    @staticmethod
    def get_recent_slips(limit: int = 20) -> list[dict]:
        """Fetch recently created or saved issue slips."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT slip_no, slip_date, department, receiver, status, total_items, created_at
                    FROM issue_slips
                    ORDER BY id DESC
                    LIMIT ?;
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"Error fetching recent slips: {exc}")
            return []

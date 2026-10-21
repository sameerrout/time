import json
import os
import unittest
import uuid
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.core.config import DATA_DIR
from app.core.database import initialize_database, get_db_connection
from app.server.cert_manager import ensure_certificate, get_local_ip
from app.server.device_service import DeviceService
from app.server.scan_service import ScanService
from app.server.http_server import LocalServer, get_server, server_signals
from app.services.material_service import MaterialService
from app.services.purchased_material_service import PurchasedMaterialService
from app.ui.dialogs.connect_phone_dialog import ConnectPhoneDialog
from app.ui.views.barcode_entry_view import BarcodeEntryView
from app.ui.views.purchased_material_view import PurchasedMaterialView

# Ensure QApplication instance exists for GUI tests
app = QApplication.instance()
if not app:
    app = QApplication([])


class TestCheckpoint8MobileScanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        # Ensure at least one test material exists in database
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO materials (
                    material_code, name, category, unit, barcode, current_stock, unit_price, is_active, plant
                ) VALUES ('1001NM210010BL421', 'INM 210 LTRS (10.0) S42-BS BLUE 50 mm', 'Plant Materials', 'EA', '1001NM210010BL421', 110.0, 150.0, 1, '1304 HYDERABAD')
                ON CONFLICT(material_code) DO UPDATE SET
                    name = excluded.name,
                    unit = excluded.unit,
                    current_stock = 110.0,
                    unit_price = 150.0;
            """)

    # ----------------------------------------------------
    # 1. Certificate and LAN IP Tests
    # ----------------------------------------------------
    def test_01_local_ip_and_certificate_generation(self):
        ip = get_local_ip()
        self.assertTrue(bool(ip), "Local IP should not be empty")

        cert_file, key_file = ensure_certificate(ip)
        self.assertTrue(cert_file.exists(), f"Certificate file should exist at: {cert_file}")
        self.assertTrue(key_file.exists(), f"Key file should exist at: {key_file}")
        self.assertGreater(cert_file.stat().st_size, 500)
        self.assertGreater(key_file.stat().st_size, 500)

    # ----------------------------------------------------
    # 2. Device Pairing and Security Tests
    # ----------------------------------------------------
    def test_02_device_pairing_and_revocation(self):
        code = DeviceService.generate_pairing_code()
        self.assertEqual(len(code), 6, "Pairing code must be 6 digits")

        # Pairing with invalid code should fail
        ok, msg, token, dev = DeviceService.verify_and_pair("000000", "Test Terminal")
        self.assertFalse(ok)
        self.assertIsNone(token)

        # Pairing with correct code should succeed
        ok, msg, token, dev = DeviceService.verify_and_pair(code, "Galaxy Tab A")
        self.assertTrue(ok)
        self.assertIsNotNone(token)
        self.assertIn("id", dev)
        self.assertEqual(dev["name"], "Galaxy Tab A")

        # Validate token
        validated_dev = DeviceService.validate_token(token)
        self.assertIsNotNone(validated_dev)
        self.assertEqual(validated_dev["name"], "Galaxy Tab A")

        # Revoke device
        dev_id = validated_dev["id"]
        rev_ok, rev_msg = DeviceService.revoke_device(dev_id)
        self.assertTrue(rev_ok)

        # Revoked device token should now be rejected immediately
        self.assertIsNone(DeviceService.validate_token(token))

    # ----------------------------------------------------
    # 3. QR Content Parsing & Material Resolution Tests
    # ----------------------------------------------------
    def test_03_qr_parsing_both_formats(self):
        # Format a: Plain code
        code_a, name_a, uom_a = ScanService.parse_qr_text("1001NM210010BL421")
        self.assertEqual(code_a, "1001NM210010BL421")
        self.assertEqual(name_a, "")

        # Format b: Pipe-delimited CODE|NAME|UOM
        raw_b = "1001NM210010BL421|INM 210 LTRS (10.0) S42-BS BLUE 50 mm|EA"
        code_b, name_b, uom_b = ScanService.parse_qr_text(raw_b)
        self.assertEqual(code_b, "1001NM210010BL421")
        self.assertEqual(name_b, "INM 210 LTRS (10.0) S42-BS BLUE 50 mm")
        self.assertEqual(uom_b, "EA")

    def test_04_scan_validation_and_idempotency(self):
        # Setup mock device
        code = DeviceService.generate_pairing_code()
        _, _, token, dev = DeviceService.verify_and_pair(code, "Test Scanner")

        # Case 1: Unknown material should be rejected
        unknown_event_id = str(uuid.uuid4())
        ok, msg, res = ScanService.process_scan(dev, {
            "event_id": unknown_event_id,
            "mode": "ISSUE",
            "material_code": "NON_EXISTENT_CODE_9999",
            "qty": 5.0
        })
        self.assertFalse(ok)
        self.assertEqual(res["status"], "rejected")

        # Case 2: Valid registered material in ISSUE mode
        valid_event_id = str(uuid.uuid4())
        ok, msg, res = ScanService.process_scan(dev, {
            "event_id": valid_event_id,
            "mode": "ISSUE",
            "material_code": "1001NM210010BL421",
            "qty": 12.0,
            "purpose": "BM Production"
        })
        self.assertTrue(ok)
        # A fresh scan is PENDING until the desktop really uses it
        self.assertEqual(res["status"], "pending")
        self.assertEqual(res["qty"], 12.0)
        self.assertEqual(res["material_code"], "1001NM210010BL421")

        # Case 3: Duplicate scan event (same event_id sent again due to network retry)
        ok_dup, msg_dup, res_dup = ScanService.process_scan(dev, {
            "event_id": valid_event_id,
            "mode": "ISSUE",
            "material_code": "1001NM210010BL421",
            "qty": 12.0
        })
        self.assertTrue(ok_dup, "Duplicate scan should be acknowledged idempotently without error")
        self.assertIn("already", msg_dup.lower())

    # ----------------------------------------------------
    # 4. Desktop Issue Slip Page Live Integration Tests
    # ----------------------------------------------------
    def test_05_desktop_issue_slip_phone_integration(self):
        view = BarcodeEntryView()
        self.assertTrue(view.btn_phone_toggle.isChecked(), "Phone scanning should default to ON")

        # Simulated phone scan event
        event_issue = {
            "event_id": str(uuid.uuid4()),
            "device_name": "Warehouse Android 1",
            "mode": "ISSUE",
            "material_code": "1001NM210010BL421",
            "material_name": "INM 210 LTRS (10.0) S42-BS BLUE 50 mm",
            "uom": "EA",
            "qty": 10.0,
            "required_qty": 10.0,
            "purpose": "Floor Batch A",
            "current_stock": 110.0
        }

        initial_count = len(view.current_slip_items)
        view.handle_phone_scan(event_issue)
        self.assertEqual(len(view.current_slip_items), initial_count + 1)
        self.assertEqual(view.current_slip_items[-1]["quantity_issued"], 10.0)
        self.assertEqual(view.current_slip_items[-1]["material_code"], "1001NM210010BL421")

        # Scanning the same item again should increment quantity on the open slip
        event_issue_same = {
            **event_issue,
            "event_id": str(uuid.uuid4()),
            "qty": 5.0
        }
        view.handle_phone_scan(event_issue_same)
        self.assertEqual(len(view.current_slip_items), initial_count + 1, "Item count should not duplicate")
        self.assertEqual(view.current_slip_items[-1]["quantity_issued"], 15.0, "Quantity should sum up")

    # ----------------------------------------------------
    # 5. Desktop Purchased Material (Plant Inward) Tests
    # ----------------------------------------------------
    def test_06_desktop_purchased_material_phone_integration(self):
        view = PurchasedMaterialView()
        self.assertFalse(view.btn_auto_receive.isChecked(), "Auto-receive should default to OFF")

        event_receive = {
            "event_id": str(uuid.uuid4()),
            "device_name": "Gate Phone 2",
            "mode": "RECEIVE",
            "material_code": "1001NM210010BL421",
            "material_name": "INM 210 LTRS (10.0) S42-BS BLUE 50 mm",
            "uom": "EA",
            "qty": 50.0,
            "unit_price": 145.0,
            "gst_pct": 18.0
        }

        # Case A: Auto-receive is OFF -> fills form fields
        view.handle_phone_scan(event_receive)
        self.assertEqual(view.txt_code.text(), "1001NM210010BL421")
        self.assertEqual(view.spin_received.value(), 50.0)
        self.assertEqual(view.spin_unit_price.value(), 145.0)

        # Case B: Auto-receive is ON -> posts directly to database and updates stock
        view.btn_auto_receive.setChecked(True)
        initial_records = len(view.records)

        event_receive_auto = {
            **event_receive,
            "event_id": str(uuid.uuid4()),
            "qty": 20.0
        }
        view.handle_phone_scan(event_receive_auto)
        view.refresh_records()
        self.assertGreater(len(view.records), initial_records, "New row should be posted directly")
        latest = view.records[0]
        self.assertEqual(latest["material_code"], "1001NM210010BL421")
        self.assertEqual(latest["device_name"], "Gate Phone 2")

    # ----------------------------------------------------
    # 6. Connect Phone Dialog Tests
    # ----------------------------------------------------
    def test_07_connect_phone_dialog(self):
        dlg = ConnectPhoneDialog()
        self.assertIsNotNone(dlg.lbl_code.text())
        self.assertEqual(len(dlg.lbl_code.text()), 6)
        self.assertTrue("https://" in dlg.lbl_url.text())
        self.assertIsNotNone(dlg.lbl_qr_image.pixmap())


if __name__ == "__main__":
    unittest.main()

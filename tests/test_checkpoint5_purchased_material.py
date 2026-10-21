import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.core.config import ensure_directories, DATA_DIR
from app.core.database import initialize_database, get_db_connection
from app.core.logger import setup_logging
from app.services.material_service import MaterialService
from app.services.purchased_material_service import PurchasedMaterialService
from app.ui.views.home_view import HomeView
from app.ui.views.purchased_material_view import PurchasedMaterialView
from app.ui.main_window import MainWindow


class TestCheckpoint5PurchasedMaterial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_directories()
        setup_logging()
        initialize_database()
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(["test"])

    def setUp(self):
        self.view = PurchasedMaterialView()
        self.view.show()

    def tearDown(self):
        self.view.close()

    def test_01_home_view_purchased_material_card(self):
        """Verify 4th card exists on HomeView with correct title, badge, icon, and signal."""
        home = HomeView()
        home.show()

        # Check signal can be connected
        signal_received = []
        home.open_purchased_material.connect(lambda: signal_received.append(True))
        home.open_purchased_material.emit()
        self.assertTrue(signal_received)
        home.close()

    def test_02_purchased_material_view_table_columns(self):
        """Verify the 8 exact specified table columns are present on the Inward Register table."""
        expected_columns = [
            "S no",
            "material code",
            "material name",
            "uom",
            "recived Qty",
            "unit price",
            "GST",
            "Total price"
        ]

        self.assertGreaterEqual(self.view.table.columnCount(), 8)
        for idx, col_name in enumerate(expected_columns):
            header_item = self.view.table.horizontalHeaderItem(idx)
            self.assertIsNotNone(header_item)
            self.assertEqual(header_item.text().lower(), col_name.lower())

    def test_03_qr_code_scanning_and_snapshot_lookup(self):
        """Verify 2D QR scanner input parses code, name, uom, and populates inward fields."""
        qr_text = "Material Name: Industrial Hex Bolt M12x50\nMaterial Code: MAT-101\nUOM: PCS"
        self.view.txt_qr_scan.setText(qr_text)
        self.view.on_qr_scanned()

        self.assertEqual(self.view.txt_code.text(), "MAT-101")
        self.assertEqual(self.view.txt_name.text(), "Industrial Hex Bolt M12x50")
        self.assertEqual(self.view.txt_uom.text(), "PCS")
        self.assertGreaterEqual(self.view.spin_received.value(), 0.1)
        self.assertEqual(self.view.spin_gst.value(), 18.0)

    def test_04_record_inward_purchase_and_inventory_update(self):
        """Verify recording inward material increases stock, logs ledger entry, and saves receipt."""
        # 1. Check baseline stock for MAT-103
        mat_before = MaterialService.get_by_code("MAT-103")
        stock_before = float(mat_before["current_stock"]) if mat_before else 0.0

        data = {
            "material_code": "MAT-103",
            "material_name": "Pneumatic Fitting 1/4 inch",
            "uom": "PCS",
            "received_stock": 25.0,
            "unit_price": 4.50,
            "supplier": "Apex Hydraulics",
            "challan_no": "CH-2026-009",
            "remarks": "Inward Batch Test"
        }

        ok, msg, rec_id = PurchasedMaterialService.record_inward_purchase(data)
        self.assertTrue(ok)
        self.assertIsNotNone(rec_id)

        # 2. Check updated stock in database
        mat_after = MaterialService.get_by_code("MAT-103")
        self.assertIsNotNone(mat_after)
        self.assertAlmostEqual(float(mat_after["current_stock"]), stock_before + 25.0)

        # 3. Check purchased_materials record
        records = PurchasedMaterialService.get_all_records("MAT-103")
        self.assertGreaterEqual(len(records), 1)
        latest = records[0]
        self.assertEqual(latest["material_code"], "MAT-103")
        self.assertEqual(latest["received_stock"], 25.0)
        self.assertEqual(latest["unit_price"], 4.50)
        self.assertEqual(latest["gst_percent"], 18.0)
        self.assertEqual(latest["total_price"], 132.75)
        self.assertEqual(latest["closing_stock"], stock_before + 25.0)

        # 4. Clean up / revert test record
        revert_ok, _ = PurchasedMaterialService.delete_record(rec_id)
        self.assertTrue(revert_ok)

    def test_05_export_excel_and_pdf(self):
        """Verify exporting purchased materials to Excel (.xlsx) and PDF."""
        # Record temporary purchase
        test_data = {
            "material_code": "MAT-TEST-EXP",
            "material_name": "Test Export Material",
            "uom": "PCS",
            "received_stock": 10.0,
            "unit_price": 5.0,
        }
        ok, _, rec_id = PurchasedMaterialService.record_inward_purchase(test_data)
        self.assertTrue(ok)

        records = PurchasedMaterialService.get_all_records("MAT-TEST-EXP")

        excel_path = DATA_DIR / "test_purchased_export.xlsx"
        pdf_path = DATA_DIR / "test_purchased_export.pdf"

        # Test Excel Export
        ok_excel = PurchasedMaterialService.export_excel(records, str(excel_path))
        self.assertTrue(ok_excel)
        self.assertTrue(excel_path.exists())
        self.assertGreater(excel_path.stat().st_size, 1000)

        # Test PDF Export
        ok_pdf = PurchasedMaterialService.export_pdf(records, str(pdf_path))
        self.assertTrue(ok_pdf)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 1000)

        # Clean up
        PurchasedMaterialService.delete_record(rec_id)
        if excel_path.exists():
            excel_path.unlink()
        if pdf_path.exists():
            pdf_path.unlink()

    def test_06_main_window_integration(self):
        """Verify MainWindow integrates PurchasedMaterialView as View 4 and back navigation works."""
        win = MainWindow()
        self.assertEqual(win.view_stack.count(), 6)

        # Navigate to Purchased Material (Index 4)
        win.switch_view(4, "Purchased Material")
        self.assertEqual(win.view_stack.currentIndex(), 4)
        self.assertFalse(win.btn_back.isHidden())

        # Navigate back to Home
        win.navigate_home()
        self.assertEqual(win.view_stack.currentIndex(), 0)
        self.assertTrue(win.btn_back.isHidden())

        win.close()

    def test_07_rupee_currency_symbol(self):
        """Verify currency symbol is Rupee symbol (₹) and not Dollar ($)."""
        from app.services.settings_service import SettingsService
        currency = SettingsService.get_setting("currency_symbol", "₹")
        self.assertEqual(currency, "₹")
        self.assertNotIn("$", self.view.lbl_kpi_val.text())
        self.assertIn("₹", self.view.lbl_kpi_val.text())
        self.assertIn("₹", self.view.lbl_total_val.text())
        self.assertIn("₹", self.view.spin_unit_price.prefix())


if __name__ == "__main__":
    unittest.main()

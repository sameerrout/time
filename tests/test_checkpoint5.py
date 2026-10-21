import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.core.config import ensure_directories, DATA_DIR
from app.core.database import initialize_database
from app.core.logger import setup_logging
from app.services.material_service import MaterialService
from app.ui.views.stock_database_view import StockDatabaseView


class TestCheckpoint5StockDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_directories()
        setup_logging()
        initialize_database()
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(["test"])

        test_mats = [
            ("MAT-101", "Industrial Hex Bolt M12x50", "Hardware", "PCS", "BAR-101", 250.0, 50.0),
            ("MAT-102", "Safety Goggles ANSI Z87", "Safety PPE", "PAIR", "BAR-102", 40.0, 10.0),
        ]
        for c, n, cat, u, b, cs, ms in test_mats:
            if not MaterialService.get_by_code(c):
                MaterialService.add_material(c, n, cat, u, b, cs, ms)

    @classmethod
    def tearDownClass(cls):
        from app.core.database import get_db_connection
        with get_db_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.execute("DELETE FROM purchased_materials;")
            conn.execute("DELETE FROM issue_slip_items;")
            conn.execute("DELETE FROM issue_slips;")
            conn.execute("DELETE FROM stock_ledger;")
            conn.execute("DELETE FROM materials;")
            conn.execute("PRAGMA foreign_keys = ON;")

    def setUp(self):
        self.view = StockDatabaseView()
        self.view.show()

    def tearDown(self):
        self.view.close()

    def test_01_search_and_table_population(self):
        """Verify initial table population, exact 10 columns, and search filtering."""
        self.assertGreater(self.view.table.rowCount(), 0)

        # Verify exact 10 columns
        expected_cols = [
            "S no", "material code", "material name", "uom",
            "opening stock", "recived stock", "issued stock",
            "closing stock", "unit price", "total price"
        ]
        self.assertEqual(self.view.table.columnCount(), 10)
        actual_cols = [self.view.table.horizontalHeaderItem(i).text() for i in range(10)]
        self.assertEqual(actual_cols, expected_cols)

        # Search for bolt
        self.view.txt_search.setText("bolt")
        self.assertGreaterEqual(self.view.table.rowCount(), 1)
        # Check first match (column 0 is S no, column 1 is material code)
        s_no = self.view.table.item(0, 0).text()
        code = self.view.table.item(0, 1).text()
        self.assertEqual(s_no, "1")
        self.assertEqual(code, "MAT-101")

        # Clear search
        self.view.txt_search.clear()
        self.assertGreaterEqual(self.view.table.rowCount(), len(self.view.materials))

    def test_02_add_and_update_material(self):
        """Verify creating a new material and editing its properties."""
        test_code = "MAT-TEST-99"
        test_barcode = "BAR-TEST-99"

        # Cleanup if exists from previous run
        existing = MaterialService.get_by_code(test_code)
        if not existing:
            ok, msg, mat_id = MaterialService.add_material(
                test_code, "Test Component", "Testing", "PCS", test_barcode, 50.0, 5.0
            )
            self.assertTrue(ok)
            self.assertIsNotNone(mat_id)
        else:
            mat_id = existing["id"]

        # Update material
        ok_upd, msg_upd = MaterialService.update_material(
            mat_id, "Test Component Updated", "Testing", "PCS", test_barcode, 10.0
        )
        self.assertTrue(ok_upd)

        # Verify update
        updated = MaterialService.get_by_code(test_code)
        self.assertEqual(updated["name"], "Test Component Updated")
        self.assertEqual(updated["min_stock"], 10.0)

    def test_03_stock_adjustment_with_audit_reason(self):
        """Verify stock adjustment records delta in stock_ledger and updates balance."""
        mat = MaterialService.get_by_code("MAT-101")
        self.assertIsNotNone(mat)
        initial_stock = float(mat["current_stock"])

        # Add 20.0 with reason
        ok, msg = MaterialService.adjust_stock(
            mat["id"], "ADD", 20.0, "Physical stocktake count surplus", user_name="Auditor"
        )
        self.assertTrue(ok)

        mat_after = MaterialService.get_by_code("MAT-101")
        self.assertEqual(float(mat_after["current_stock"]), initial_stock + 20.0)

        # Check stock movement history
        history = MaterialService.get_stock_history(mat["id"])
        self.assertGreater(len(history), 0)
        latest = history[0]
        self.assertEqual(latest["transaction_type"], "ADJUSTMENT")
        self.assertEqual(latest["quantity"], 20.0)
        self.assertIn("Auditor", latest["reason"])

    def test_04_csv_export_and_import(self):
        """Verify exporting inventory to CSV and re-importing."""
        test_csv = DATA_DIR / "test_inventory_roundtrip.csv"

        # Export
        ok_exp, msg_exp = MaterialService.export_to_csv(str(test_csv))
        self.assertTrue(ok_exp)
        self.assertTrue(test_csv.exists())
        self.assertGreater(test_csv.stat().st_size, 50)

        # Import
        added, updated, errors = MaterialService.import_from_csv(str(test_csv))
        self.assertEqual(len(errors), 0, f"Import reported unexpected errors: {errors}")
        self.assertGreater(updated, 0)

        if test_csv.exists():
            test_csv.unlink()


if __name__ == "__main__":
    unittest.main()

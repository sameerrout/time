import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QSize
from app.core.config import ensure_directories
from app.core.database import initialize_database, get_database_stats, check_database_integrity
from app.core.logger import setup_logging
from app.ui.main_window import MainWindow
from app.services.material_service import MaterialService
from app.services.settings_service import SettingsService


class TestCheckpoint6SystemValidation(unittest.TestCase):
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
            ("MAT-103", "Pneumatic Fitting 1/4 inch", "Pneumatics", "PCS", "BAR-103", 15.0, 5.0),
            ("MAT-104", "Synthetic Lubricant Grease EP-2", "Consumables", "KG", "BAR-104", 30.0, 5.0),
            ("MAT-105", "Heavy Duty Nitrile Gloves (L)", "Safety PPE", "BOX", "BAR-105", 100.0, 20.0),
            ("MAT-106", "Timing Belt 240-3M-15", "Spare Parts", "PCS", "BAR-106", 8.0, 2.0),
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
        self.window = MainWindow()
        self.window.show()

    def tearDown(self):
        self.window.close()

    def test_01_full_navigation_cycle(self):
        """Verify seamless transitions through all 3 modules and settings back to Home."""
        # 1. Barcode Entry
        self.window.switch_view(1, "Barcode Entry")
        self.assertEqual(self.window.view_stack.currentIndex(), 1)
        self.assertFalse(self.window.btn_back.isHidden())
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)
        self.assertTrue(self.window.btn_back.isHidden())

        # 2. Barcode Generator
        self.window.switch_view(2, "Barcode Generator")
        self.assertEqual(self.window.view_stack.currentIndex(), 2)
        self.assertFalse(self.window.btn_back.isHidden())
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)

        # 3. Stock Database
        self.window.switch_view(3, "Stock Database")
        self.assertEqual(self.window.view_stack.currentIndex(), 3)
        self.assertFalse(self.window.btn_back.isHidden())
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)

        # 4. Purchased Material
        self.window.switch_view(4, "Purchased Material")
        self.assertEqual(self.window.view_stack.currentIndex(), 4)
        self.assertFalse(self.window.btn_back.isHidden())
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)

        # 5. Settings
        self.window.navigate_settings()
        self.assertEqual(self.window.view_stack.currentIndex(), 5)
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)

    def test_02_window_resizing_adaptability(self):
        """Verify window scales smoothly across standard screen resolutions."""
        resolutions = [
            (1080, 680),  # Minimum allowed size
            (1280, 720),  # HD Standard
            (1366, 768),  # Laptop Standard
            (1920, 1080)  # Full HD 1080p
        ]
        for w, h in resolutions:
            self.window.resize(w, h)
            self.app.processEvents()
            self.assertEqual(self.window.size(), QSize(w, h))
            self.assertIsNotNone(self.window.centralWidget())

    def test_03_database_preservation_and_integrity(self):
        """Verify database remains intact with zero corruption after multiple operational cycles."""
        ok, msg = check_database_integrity()
        self.assertTrue(ok, f"Integrity check failed: {msg}")

        stats = get_database_stats()
        self.assertTrue(stats["exists"])
        self.assertGreaterEqual(stats["schema_version"], 2)
        self.assertEqual(stats["journal_mode"], "WAL")
        self.assertGreaterEqual(stats["table_count"], 4)

        # Verify materials remain intact
        materials = MaterialService.get_all(active_only=False)
        self.assertGreaterEqual(len(materials), 6)

    def test_04_keyboard_usability(self):
        """Verify Enter key on QR scanner input triggers parsing, material lookup, and row addition."""
        issue_view = self.window.barcode_entry_view
        self.window.switch_view(1, "Issue Slip Creation")

        # Focus QR scanner input and trigger Enter
        issue_view.txt_qr_scan.setText("Material Name: Industrial Hex Bolt M12x50\nMaterial Code: MAT-101")
        issue_view.txt_qr_scan.returnPressed.emit()

        # Item should be immediately added to paper template table
        self.assertEqual(len(issue_view.current_slip_items), 1)
        self.assertEqual(issue_view.current_slip_items[0]["material_code"], "MAT-101")
        self.app.processEvents()
        self.assertEqual(issue_view.txt_qr_scan.text(), "")


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QLabel
from app.core.config import ensure_directories, ICONS_DIR
from app.core.database import initialize_database
from app.core.logger import setup_logging
from app.ui.main_window import MainWindow
from app.ui.views.home_view import HomeView, ModuleCard


class TestCheckpoint2HomeScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_directories()
        setup_logging()
        initialize_database()
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(["test"])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()

    def tearDown(self):
        self.window.close()

    def test_01_three_module_cards_present(self):
        """Verify the main screen has 4 primary module cards with correct titles and icons."""
        home_view = self.window.home_view
        cards = home_view.findChildren(ModuleCard)
        self.assertEqual(len(cards), 4, "Home view must contain 4 primary module cards")
        
        # Verify icon files exist
        self.assertTrue((ICONS_DIR / "icon_scanner.png").exists(), "icon_scanner.png must exist")
        self.assertTrue((ICONS_DIR / "icon_generator.png").exists(), "icon_generator.png must exist")
        self.assertTrue((ICONS_DIR / "icon_database.png").exists(), "icon_database.png must exist")
        self.assertTrue((ICONS_DIR / "icon_purchase.png").exists(), "icon_purchase.png must exist")

    def test_02_card_1_navigation(self):
        """Verify clicking Barcode Entry card switches view and reveals Back button."""
        self.window.home_view.open_barcode_entry.emit()
        self.assertEqual(self.window.view_stack.currentIndex(), 1)
        self.assertFalse(self.window.btn_back.isHidden(), "Back button must be visible in module")
        
        # Click back
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)
        self.assertTrue(self.window.btn_back.isHidden(), "Back button must be hidden on Home")

    def test_03_card_2_navigation(self):
        """Verify clicking Barcode Generator card switches view and reveals Back button."""
        self.window.home_view.open_barcode_generator.emit()
        self.assertEqual(self.window.view_stack.currentIndex(), 2)
        self.assertFalse(self.window.btn_back.isHidden())
        
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)
        self.assertTrue(self.window.btn_back.isHidden())

    def test_04_card_3_navigation(self):
        """Verify clicking Stock Database card switches view and reveals Back button."""
        self.window.home_view.open_stock_database.emit()
        self.assertEqual(self.window.view_stack.currentIndex(), 3)
        self.assertFalse(self.window.btn_back.isHidden())
        
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)
        self.assertTrue(self.window.btn_back.isHidden())

    def test_04b_card_4_navigation(self):
        """Verify clicking Purchased Material card switches view and reveals Back button."""
        self.window.home_view.open_purchased_material.emit()
        self.assertEqual(self.window.view_stack.currentIndex(), 4)
        self.assertFalse(self.window.btn_back.isHidden())
        
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)
        self.assertTrue(self.window.btn_back.isHidden())

    def test_05_discreet_settings(self):
        """Verify settings is accessible discreetly without cluttering home screen."""
        self.window.navigate_settings()
        self.assertEqual(self.window.view_stack.currentIndex(), 5)
        self.assertFalse(self.window.btn_back.isHidden())
        
        self.window.navigate_home()
        self.assertEqual(self.window.view_stack.currentIndex(), 0)

    def test_06_no_technical_jargon_on_home(self):
        """Verify customer screen does NOT contain developer/internal jargon."""
        home_text = " ".join([lbl.text() for lbl in self.window.home_view.findChildren(QLabel)])
        forbidden_terms = ["sqlite", "journal_mode", "wal mode", "busy_timeout", "schema_version", "roadmap", "checkpoint"]
        for term in forbidden_terms:
            self.assertNotIn(term, home_text.lower(), f"Forbidden developer term '{term}' found on Home Screen")


if __name__ == "__main__":
    unittest.main()

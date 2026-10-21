import os
import sys
import unittest

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import (
    BASE_DIR, DATA_DIR, LOGS_DIR, BACKUPS_DIR, DB_FILE,
    APP_ICON_PNG, APP_ICON_ICO, check_storage_writable, get_drive_info
)
from app.core.logger import setup_logging, get_recent_logs
from app.core.database import initialize_database, get_connection, check_database_integrity, get_database_stats
from app.services.settings_service import SettingsService


class TestModule1Foundation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.core.config import ensure_directories
        ensure_directories()
        setup_logging()
        initialize_database()

    def test_01_directories_and_storage(self):
        """Verify storage directories and writability."""
        self.assertTrue(DATA_DIR.exists(), "Data directory should exist")
        self.assertTrue(LOGS_DIR.exists(), "Logs directory should exist")
        self.assertTrue(BACKUPS_DIR.exists(), "Backups directory should exist")
        
        writable, msg = check_storage_writable()
        self.assertTrue(writable, f"Storage should be writable: {msg}")

        drive_info = get_drive_info()
        self.assertIn("drive_letter", drive_info)
        self.assertIn("drive_type_desc", drive_info)

    def test_02_icons_exist(self):
        """Verify icon assets were generated properly."""
        self.assertTrue(APP_ICON_PNG.exists(), "app_icon.png should exist")
        self.assertTrue(APP_ICON_ICO.exists(), "app_icon.ico should exist")
        self.assertGreater(APP_ICON_PNG.stat().st_size, 1000, "PNG icon should have valid size")
        self.assertGreater(APP_ICON_ICO.stat().st_size, 1000, "ICO icon should have valid size")

    def test_03_database_initialization_and_pragmas(self):
        """Verify database schema, WAL mode, foreign keys, and integrity."""
        self.assertTrue(DB_FILE.exists(), "SQLite database file should exist")
        
        conn = get_connection()
        cur = conn.cursor()
        
        # Test foreign keys
        cur.execute("PRAGMA foreign_keys;")
        self.assertEqual(cur.fetchone()[0], 1, "Foreign keys should be ON")
        
        # Test journal mode (WAL)
        cur.execute("PRAGMA journal_mode;")
        self.assertEqual(cur.fetchone()[0].upper(), "WAL", "Journal mode should be WAL")
        
        # Test schema version (version 1 or later migration)
        cur.execute("SELECT MAX(version) FROM schema_version;")
        ver = cur.fetchone()[0]
        self.assertGreaterEqual(ver, 1, "Schema version should be at least 1")
        
        # Test integrity
        ok, msg = check_database_integrity()
        self.assertTrue(ok, f"Integrity check failed: {msg}")
        
        conn.close()

    def test_04_settings_service(self):
        """Verify settings service read, write, and defaults."""
        original_company = SettingsService.get_setting("company_name")
        self.assertTrue(bool(original_company))
        
        # Test updating setting
        success = SettingsService.set_setting("company_name", "Global Warehouse Corp")
        self.assertTrue(success)
        self.assertEqual(SettingsService.get_setting("company_name"), "Global Warehouse Corp")
        
        # Revert back to original
        SettingsService.set_setting("company_name", original_company)
        self.assertEqual(SettingsService.get_setting("company_name"), original_company)
        
        # Test departments
        depts = SettingsService.get_departments()
        self.assertIsInstance(depts, list)
        self.assertIn("BM production", depts)

    def test_05_logging(self):
        """Verify rotating logs capture entries."""
        logs = get_recent_logs(20)
        self.assertIsInstance(logs, list)
        self.assertGreater(len(logs), 0, "Log file should contain initial startup lines")

    def test_06_ui_headless_instantiation(self):
        """Verify PySide6 MainWindow and views instantiate without error in offscreen mode."""
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtWidgets import QApplication
        from app.ui.main_window import MainWindow

        app = QApplication.instance()
        if not app:
            app = QApplication(["test"])
        
        window = MainWindow()
        self.assertIsNotNone(window)
        # 6 views in the architecture: Home (4 cards) + 4 modules + Settings
        self.assertEqual(window.view_stack.count(), 6, "Should have 6 navigation views registered")
        
        window.show()
        # Test default home state
        self.assertEqual(window.view_stack.currentIndex(), 0)
        self.assertTrue(window.btn_back.isHidden(), "Back button should be hidden on Home Screen")
        
        # Switch to Barcode Entry
        window.switch_view(1, "Barcode Entry")
        self.assertEqual(window.view_stack.currentIndex(), 1)
        self.assertFalse(window.btn_back.isHidden(), "Back button should be visible in module view")
        
        # Click back button to return to home
        window.navigate_home()
        self.assertEqual(window.view_stack.currentIndex(), 0)
        self.assertTrue(window.btn_back.isHidden())
        
        window.close()
        
    def test_07_negative_settings_fallbacks(self):
        """Negative test: Non-existent key should return fallback default without error."""
        val = SettingsService.get_setting("non_existent_key_xyz", default="FALLBACK_VAL")
        self.assertEqual(val, "FALLBACK_VAL")

    def test_08_sensitive_log_redaction(self):
        """Negative/Security test: Ensure passwords are not written in plaintext to logs."""
        import logging
        from app.core.logger import get_logger, get_recent_logs
        
        logger = get_logger("IssueSlipApp.SecurityTest")
        logger.info("User login attempt with password secret12345")
        
        recent = "".join(get_recent_logs(10))
        self.assertNotIn("secret12345", recent, "Plaintext password must be redacted by SensitiveFilter")
        self.assertIn("[REDACTED_SENSITIVE_CONTENT]", recent)

    def test_09_database_transaction_rollback(self):
        """Error recovery test: Verify atomic transaction rollback on failure."""
        from app.core.database import get_db_connection
        
        with self.assertRaises(Exception):
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO app_settings (key, value) VALUES ('test_rollback_key', 'should_not_exist');")
                # Intentional error to trigger rollback
                cur.execute("INSERT INTO non_existent_table VALUES (1);")
                
        # Value must not have been committed
        val = SettingsService.get_setting("test_rollback_key", default=None)
        self.assertIsNone(val, "Transaction must rollback and not leave partial data")


if __name__ == "__main__":
    unittest.main()

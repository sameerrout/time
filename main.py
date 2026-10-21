import os
import sys
import ctypes
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from app.core.config import (
    APP_NAME, APP_VERSION, APP_ID,
    APP_ICON_PNG, APP_ICON_ICO,
    ensure_directories, check_storage_writable,
    LOG_FILE
)
from app.core.logger import setup_logging, get_logger
from app.core.database import initialize_database
from app.ui.theme import MODERN_LIGHT_QSS
from app.ui.main_window import MainWindow


def set_windows_app_id():
    """Ensure Windows taskbar displays the native application icon."""
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    """Global exception hook: prevent silent desktop crashes and log full traceback."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger = get_logger("IssueSlipApp.CrashHandler")
    formatted_trace = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    logger.critical(f"Uncaught Application Exception:\n{formatted_trace}")

    # Display safe native dialog to user if Qt application is still active
    app = QApplication.instance()
    if app:
        err_box = QMessageBox()
        err_box.setIcon(QMessageBox.Critical)
        err_box.setWindowTitle("Application Error")
        err_box.setText(f"An unexpected error occurred in {APP_NAME}.")
        err_box.setInformativeText(f"{exc_value}\n\nDetails have been logged to:\n{LOG_FILE}")
        err_box.setDetailedText(formatted_trace)
        err_box.exec()


def main():
    # 1. Set Windows Application Model ID for taskbar icon separation
    set_windows_app_id()

    # 2. Setup directory tree and logging
    ensure_directories()
    logger = setup_logging()
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}...")

    # 3. Verify storage writability
    writable, write_msg = check_storage_writable()
    if not writable:
        logger.warning(f"Storage writability check warning: {write_msg}")

    # 4. Initialize Local SQLite Database
    try:
        initialize_database()
        logger.info("Local database initialized and verified.")
    except Exception as exc:
        logger.critical(f"Fatal error initializing database: {exc}", exc_info=True)
        # Even before full UI, show a native message box
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Failed to initialize local database:\n\n{exc}\n\nCheck logs for details.",
                f"{APP_NAME} - Critical Startup Error",
                0x10  # MB_ICONERROR
            )
        sys.exit(1)

    # 5. Create PySide6 Application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Industrial Warehouse Systems")

    # Set Desktop Application Icon
    if APP_ICON_PNG.exists():
        app_icon = QIcon(str(APP_ICON_PNG))
        app.setWindowIcon(app_icon)
    elif APP_ICON_ICO.exists():
        app_icon = QIcon(str(APP_ICON_ICO))
        app.setWindowIcon(app_icon)

    # Apply Modern Light Desktop Stylesheet
    app.setStyleSheet(MODERN_LIGHT_QSS)

    # Attach global exception hook
    sys.excepthook = handle_uncaught_exception

    # 6. Show Main Window
    window = MainWindow()
    window.show()

    logger.info("Main application window displayed.")

    # Show warning dialog if drive is not writable
    if not writable:
        QMessageBox.warning(
            window,
            "Storage Warning",
            f"The current application location may be READ-ONLY:\n\n{write_msg}\n\n"
            "Please ensure the USB drive or folder has write permissions so records can be saved."
        )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

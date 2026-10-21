import sys
import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QStatusBar,
    QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap

from app.core.config import (
    APP_NAME, APP_VERSION, APP_ICON_PNG
)
from app.core.logger import get_logger
from app.server.http_server import start_server, stop_server, server_signals
from app.ui.dialogs.connect_phone_dialog import ConnectPhoneDialog
from app.services.settings_service import SettingsService
from app.ui.views.home_view import HomeView
from app.ui.views.barcode_entry_view import BarcodeEntryView
from app.ui.views.barcode_generator_view import BarcodeGeneratorView
from app.ui.views.stock_database_view import StockDatabaseView
from app.ui.views.purchased_material_view import PurchasedMaterialView
from app.ui.views.settings_view import SettingsView

logger = get_logger("IssueSlipApp.MainWindow")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} - Material Issue System")
        self.setMinimumSize(1080, 680)
        self.resize(1180, 740)

        # Application Icon
        if APP_ICON_PNG.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PNG)))

        # Start Local HTTPS Mobile PWA Server (Wi-Fi 8443)
        self.server = start_server(port=8443)
        server_signals.scan_received.connect(self._on_mobile_scan_received)
        server_signals.server_status.connect(self._on_server_status_changed)

        self.init_ui()
        self.setup_status_bar()
        self.setup_clock_timer()
        self.refresh_branding()

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ========================================================
        # 1. Clean Top Header Bar (No dark sidebar)
        # ========================================================
        header_bar = QFrame(self)
        header_bar.setObjectName("appHeaderBar")
        h_layout = QHBoxLayout(header_bar)
        h_layout.setContentsMargins(28, 12, 28, 12)
        h_layout.setSpacing(16)

        # Back Navigation Button (Hidden on Home Screen)
        self.btn_back = QPushButton("←  Back to Main Menu", header_bar)
        self.btn_back.setProperty("class", "btn-back")
        self.btn_back.setVisible(False)
        self.btn_back.clicked.connect(self.navigate_home)
        h_layout.addWidget(self.btn_back)

        # Brand & Facility Titles
        brand_box = QVBoxLayout()
        brand_box.setSpacing(2)
        self.lbl_company = QLabel("Apex Industrial Manufacturing", header_bar)
        self.lbl_company.setObjectName("companyTitleLabel")
        self.lbl_system = QLabel("Material Issue System", header_bar)
        self.lbl_system.setObjectName("systemNameLabel")
        brand_box.addWidget(self.lbl_company)
        brand_box.addWidget(self.lbl_system)
        h_layout.addLayout(brand_box)

        h_layout.addStretch()

        # Database Connection Status Pill
        self.lbl_db_badge = QLabel("● Database Ready", header_bar)
        self.lbl_db_badge.setObjectName("statusBadgeOnline")
        h_layout.addWidget(self.lbl_db_badge)

        # Connect Phone Button
        self.btn_connect_phone = QPushButton("📱 Connect Phone", header_bar)
        self.btn_connect_phone.setProperty("class", "header-btn")
        self.btn_connect_phone.setStyleSheet("""
            QPushButton {
                background-color: #047857;
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                padding: 6px 14px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #065F46;
            }
        """)
        self.btn_connect_phone.clicked.connect(self.show_connect_phone_dialog)
        h_layout.addWidget(self.btn_connect_phone)

        # Discreet Settings Gear Button
        self.btn_settings = QPushButton("⚙  Settings", header_bar)
        self.btn_settings.setProperty("class", "header-btn")
        self.btn_settings.clicked.connect(self.navigate_settings)
        h_layout.addWidget(self.btn_settings)

        root_layout.addWidget(header_bar)

        # ========================================================
        # 2. Main Stacked Views Area
        # ========================================================
        self.view_stack = QStackedWidget(self)

        # View 0: Home Screen (The 3 Primary Module Cards)
        self.home_view = HomeView(self)
        self.home_view.open_barcode_entry.connect(lambda: self.switch_view(1, "Issue Slip Creation"))
        self.home_view.open_barcode_generator.connect(lambda: self.switch_view(2, "QR Code Generator"))
        self.home_view.open_stock_database.connect(lambda: self.switch_view(3, "Stock Database"))
        self.home_view.open_purchased_material.connect(lambda: self.switch_view(4, "Purchased Material"))
        self.home_view.open_settings.connect(self.navigate_settings)
        self.home_view.open_connect_phone.connect(self.show_connect_phone_dialog)
        self.view_stack.addWidget(self.home_view)

        # View 1: Barcode Entry (Module 1)
        self.barcode_entry_view = BarcodeEntryView(self)
        self.view_stack.addWidget(self.barcode_entry_view)

        # View 2: Barcode Generator (Module 2)
        self.barcode_generator_view = BarcodeGeneratorView(self)
        self.view_stack.addWidget(self.barcode_generator_view)

        # View 3: Stock Database (Module 3)
        self.stock_database_view = StockDatabaseView(self)
        self.view_stack.addWidget(self.stock_database_view)

        # View 4: Purchased Material (Module 4)
        self.purchased_material_view = PurchasedMaterialView(self)
        self.purchased_material_view.stock_updated.connect(self.stock_database_view.refresh_table)
        self.view_stack.addWidget(self.purchased_material_view)

        # View 5: System Settings
        self.settings_view = SettingsView(self)
        self.settings_view.settings_saved.connect(self.on_settings_saved)
        self.view_stack.addWidget(self.settings_view)

        root_layout.addWidget(self.view_stack, 1)

    def setup_status_bar(self):
        status_bar = self.statusBar()
        status_bar.setSizeGripEnabled(False)

        self.lbl_status_left = QLabel("Local SQLite Database: Active")
        status_bar.addWidget(self.lbl_status_left)

        self.lbl_status_center = QLabel("Offline Standalone Edition")
        status_bar.addPermanentWidget(self.lbl_status_center)

        self.lbl_status_time = QLabel("")
        status_bar.addPermanentWidget(self.lbl_status_time)

    def setup_clock_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_clock)
        self.timer.start(1000)
        self.update_clock()

    def update_clock(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        self.lbl_status_time.setText(f"🕒 {now}")

    def refresh_branding(self):
        company = SettingsService.get_setting("company_name", "Apex Industrial Manufacturing")
        facility = SettingsService.get_setting("facility_name", "Plant 1 - Central Warehouse")
        self.lbl_company.setText(company)
        self.lbl_system.setText(f"Material Issue System  •  {facility}")
        self.home_view.refresh_header()

    def switch_view(self, index: int, title: str = ""):
        self.view_stack.setCurrentIndex(index)
        is_home = (index == 0)
        self.btn_back.setVisible(not is_home)
        if not is_home:
            self.lbl_system.setText(f"Material Issue System  →  {title}")
            if index == 1:
                self.barcode_entry_view.refresh_defaults()
            elif index == 2:
                self.barcode_generator_view.load_materials()
            elif index == 3:
                self.stock_database_view.refresh_table()
            elif index == 4:
                self.purchased_material_view.refresh_records()
        else:
            self.refresh_branding()

    def navigate_home(self):
        self.switch_view(0)

    def navigate_settings(self):
        self.switch_view(5, "System Settings")

    def on_settings_saved(self):
        self.refresh_branding()

    def show_connect_phone_dialog(self):
        dlg = ConnectPhoneDialog(self)
        dlg.exec()

    def _on_mobile_scan_received(self, event_data: dict):
        mode = str(event_data.get("mode", "")).upper()
        if mode == "ISSUE":
            self.barcode_entry_view.handle_phone_scan(event_data)
        elif mode == "RECEIVE":
            self.purchased_material_view.handle_phone_scan(event_data)

    def _on_server_status_changed(self, running: bool, url: str):
        if running:
            self.lbl_status_center.setText(f"📱 Wireless Scanner: {url}")
        else:
            self.lbl_status_center.setText("Offline Standalone Edition")

    def closeEvent(self, event):
        try:
            stop_server()
        except Exception:
            pass
        super().closeEvent(event)

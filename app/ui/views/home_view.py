from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QIcon

from app.core.config import ICONS_DIR
from app.services.settings_service import SettingsService


class ModuleCard(QFrame):
    """Large, interactive module card with clean icon, title, description, and action button."""
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, description: str, icon_filename: str, btn_label: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "module-card")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 26, 26, 26)
        layout.setSpacing(10)

        # Icon Container
        icon_path = ICONS_DIR / icon_filename
        lbl_icon = QLabel(self)
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            lbl_icon.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lbl_icon.setFixedSize(64, 64)
        layout.addWidget(lbl_icon)

        # Card Title
        lbl_title = QLabel(title, self)
        lbl_title.setObjectName("cardTitleLabel")
        layout.addWidget(lbl_title)

        # Card Subtitle / Purpose
        lbl_sub = QLabel(subtitle, self)
        lbl_sub.setStyleSheet("font-size: 12px; font-weight: 600; color: #2563eb;")
        layout.addWidget(lbl_sub)

        # Card Description
        lbl_desc = QLabel(description, self)
        lbl_desc.setObjectName("cardDescLabel")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        layout.addStretch()

        # Action Button
        self.btn_action = QPushButton(btn_label, self)
        self.btn_action.setProperty("class", "btn-card-action")
        self.btn_action.clicked.connect(self.clicked.emit)
        layout.addWidget(self.btn_action)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class HomeView(QWidget):
    open_barcode_entry = Signal()
    open_barcode_generator = Signal()
    open_stock_database = Signal()
    open_purchased_material = Signal()
    open_settings = Signal()
    open_connect_phone = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.refresh_header()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(36, 32, 36, 32)
        root_layout.setSpacing(24)

        # 1. Hero Introduction Header
        hero_box = QVBoxLayout()
        hero_box.setSpacing(6)

        lbl_hero_title = QLabel("Material Issue System", self)
        lbl_hero_title.setObjectName("heroTitleLabel")

        lbl_hero_sub = QLabel("Select an operation below to scan, generate barcodes, or manage warehouse inventory.", self)
        lbl_hero_sub.setObjectName("heroSubtitleLabel")

        hero_box.addWidget(lbl_hero_title)
        hero_box.addWidget(lbl_hero_sub)
        root_layout.addLayout(hero_box)

        # 2. Four Primary Module Cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(18)

        # Card 1: Issue Slip Creation
        card_entry = ModuleCard(
            title="1. Issue Slip Creation",
            subtitle="COMPANY TEMPLATE & QR SCAN",
            description="Scan 2D QR codes to populate the digital company issue slip, edit quantities, save drafts, and print A4 slips.",
            icon_filename="icon_scanner.png",
            btn_label="Open Issue Slip Form  →",
            parent=self
        )
        card_entry.clicked.connect(self.open_barcode_entry.emit)
        cards_layout.addWidget(card_entry)

        # Card 2: QR Code Generator
        card_generator = ModuleCard(
            title="2. QR Code Generator",
            subtitle="QR CODE & LABEL PRINTING",
            description="Create QR code labels encoding Material Name and Material Code, preview live label cards, and export printable PDF sheets.",
            icon_filename="icon_generator.png",
            btn_label="Open QR Code Generator  →",
            parent=self
        )
        card_generator.clicked.connect(self.open_barcode_generator.emit)
        cards_layout.addWidget(card_generator)

        # Card 3: Stock Database
        card_database = ModuleCard(
            title="3. Stock Database",
            subtitle="INVENTORY MASTER & LEDGER",
            description="Search the full material catalog, check current stock levels, perform adjustments, and import or export CSV records.",
            icon_filename="icon_database.png",
            btn_label="Open Stock Database  →",
            parent=self
        )
        card_database.clicked.connect(self.open_stock_database.emit)
        cards_layout.addWidget(card_database)

        # Card 4: Purchased Material
        card_purchase = ModuleCard(
            title="4. Purchased Material",
            subtitle="INWARD MATERIAL & PLANT ENTRY",
            description="Scan QR codes for materials entering the plant, record received stock, update physical inventory, and track prices.",
            icon_filename="icon_purchase.png",
            btn_label="Open Purchased Material  →",
            parent=self
        )
        card_purchase.clicked.connect(self.open_purchased_material.emit)
        cards_layout.addWidget(card_purchase)

        root_layout.addLayout(cards_layout, 1)

        # 3. Bottom Quick Info Bar
        bottom_bar = QHBoxLayout()
        self.lbl_facility_info = QLabel("Facility: Plant 1 - Central Warehouse", self)
        self.lbl_facility_info.setStyleSheet("color: #64748b; font-size: 13px; font-weight: 500;")
        bottom_bar.addWidget(self.lbl_facility_info)

        bottom_bar.addStretch()

        btn_phone = QPushButton("📱 Connect Phone Scanner", self)
        btn_phone.setStyleSheet("""
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
        btn_phone.clicked.connect(self.open_connect_phone.emit)
        bottom_bar.addWidget(btn_phone)

        btn_settings = QPushButton("⚙  System Settings", self)
        btn_settings.setProperty("class", "header-btn")
        btn_settings.clicked.connect(self.open_settings.emit)
        bottom_bar.addWidget(btn_settings)

        root_layout.addLayout(bottom_bar)

    def refresh_header(self):
        facility = SettingsService.get_setting("facility_name", "Plant 1 - Central Warehouse")
        self.lbl_facility_info.setText(f"Active Facility: {facility}")

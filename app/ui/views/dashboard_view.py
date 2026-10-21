from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QGridLayout, QMessageBox, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from app.core.config import get_drive_info, check_storage_writable, DATA_DIR, LOGS_DIR
from app.core.database import get_database_stats, check_database_integrity
from app.services.settings_service import SettingsService


class DashboardView(QWidget):
    navigate_to_settings = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.refresh_dashboard()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(18)

        # Scroll area to handle smaller laptop displays gracefully
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        # 1. Facility Header Banner
        self.banner_card = QFrame()
        self.banner_card.setProperty("class", "card-highlight")
        banner_layout = QHBoxLayout(self.banner_card)
        banner_layout.setContentsMargins(20, 16, 20, 16)

        banner_text_layout = QVBoxLayout()
        self.lbl_company = QLabel("Apex Industrial Manufacturing")
        self.lbl_company.setStyleSheet("font-size: 18px; font-weight: 700; color: #0f172a;")
        self.lbl_facility = QLabel("Facility: Plant 1 - Central Warehouse")
        self.lbl_facility.setStyleSheet("font-size: 13px; color: #475569;")
        banner_text_layout.addWidget(self.lbl_company)
        banner_text_layout.addWidget(self.lbl_facility)

        banner_layout.addLayout(banner_text_layout, 1)

        btn_settings = QPushButton("⚙️ System Settings")
        btn_settings.clicked.connect(self.navigate_to_settings.emit)
        banner_layout.addWidget(btn_settings)

        btn_refresh = QPushButton("🔄 Refresh Status")
        btn_refresh.clicked.connect(self.refresh_dashboard)
        banner_layout.addWidget(btn_refresh)

        layout.addWidget(self.banner_card)

        # 2. Key Status Grid Cards
        grid = QGridLayout()
        grid.setSpacing(16)

        # Card A: Portable Storage Status
        self.card_storage = self._create_card("💾 Portable Storage Environment", [
            ("Drive Type:", "drive_type_val"),
            ("Drive Location:", "drive_path_val"),
            ("Storage Mode:", "storage_mode_val"),
            ("Write Permission:", "write_perm_val")
        ])
        grid.addWidget(self.card_storage, 0, 0)

        # Card B: Database & Integrity
        self.card_db = self._create_card("🗄️ Local SQLite Engine", [
            ("Database Engine:", "db_engine_val"),
            ("Journal Mode:", "db_journal_val"),
            ("Database File Size:", "db_size_val"),
            ("Integrity Status:", "db_integrity_val")
        ])
        grid.addWidget(self.card_db, 0, 1)

        # Card C: Barcode Scanner Interface
        self.card_scanner = self._create_card("📡 Wireless Barcode Scanner", [
            ("Supported Hardware:", "Any 1D/2D USB/Bluetooth Scanner"),
            ("Operating Mode:", "HID Virtual Keyboard Mode"),
            ("Scanner Read Frequency:", "Up to 500 characters/second"),
            ("Hardware Status:", "READY FOR SCAN INPUT")
        ])
        grid.addWidget(self.card_scanner, 1, 0)

        # Card D: System Integrity Actions
        card_actions = QFrame()
        card_actions.setProperty("class", "card")
        act_layout = QVBoxLayout(card_actions)
        act_title = QLabel("🛡️ Reliability & Safety Tools")
        act_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 6px;")
        act_layout.addWidget(act_title)

        act_desc = QLabel("Run hardware integrity checks and verify database consistency before warehouse shift operations.")
        act_desc.setWordWrap(True)
        act_desc.setStyleSheet("color: #64748b; font-size: 12px; margin-bottom: 12px;")
        act_layout.addWidget(act_desc)

        btn_check_integrity = QPushButton("🔍 Run SQLite Integrity Check")
        btn_check_integrity.clicked.connect(self.run_integrity_check)
        act_layout.addWidget(btn_check_integrity)

        act_layout.addStretch()
        grid.addWidget(card_actions, 1, 1)

        layout.addLayout(grid)

        # 3. Module Development Roadmap Checklist
        roadmap_card = QFrame()
        roadmap_card.setProperty("class", "card")
        roadmap_layout = QVBoxLayout(roadmap_card)

        rm_title = QLabel("📋 Software Modules Architecture Roadmap")
        rm_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 8px;")
        roadmap_layout.addWidget(rm_title)

        modules = [
            ("Module 1: Desktop Application Foundation", "Active & Loaded (CHECKPOINT-01)", "#16a34a"),
            ("Module 2: Material Master & Barcode Generation", "Pending Checkpoint 1 Approval", "#94a3b8"),
            ("Module 3: Stock Management & Ledger", "Pending Checkpoint 2", "#94a3b8"),
            ("Module 4: Issue Slip Creation & Fast Scanning", "Pending Checkpoint 3", "#94a3b8"),
            ("Module 5: Issue Approval & Atomic Deduction", "Pending Checkpoint 4", "#94a3b8"),
            ("Module 6: Printable Issue Slip & PDF Generator", "Pending Checkpoint 5", "#94a3b8"),
            ("Module 7: Reports & CSV Export", "Pending Checkpoint 6", "#94a3b8"),
            ("Module 8: Local Users, Roles & Audit", "Pending Checkpoint 7", "#94a3b8"),
            ("Module 9: Portable USB Packaging & Launcher", "Pending Checkpoint 8", "#94a3b8"),
        ]

        for mod_name, mod_status, color in modules:
            row = QHBoxLayout()
            lbl_name = QLabel(f"• {mod_name}")
            lbl_name.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e293b;")
            lbl_status = QLabel(mod_status)
            lbl_status.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {color};")
            row.addWidget(lbl_name, 1)
            row.addWidget(lbl_status)
            roadmap_layout.addLayout(row)

        layout.addWidget(roadmap_card)
        layout.addStretch()

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

    def _create_card(self, title: str, rows: list[tuple[str, str]]) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        card_title = QLabel(title)
        card_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 6px;")
        card_layout.addWidget(card_title)

        for label_text, attr_name in rows:
            h_layout = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #64748b; font-size: 12px;")
            val = QLabel("...")
            val.setStyleSheet("color: #0f172a; font-size: 12px; font-weight: 600;")
            setattr(self, attr_name, val)
            h_layout.addWidget(lbl)
            h_layout.addStretch()
            h_layout.addWidget(val)
            card_layout.addLayout(h_layout)

        card_layout.addStretch()
        return card

    def refresh_dashboard(self):
        # Update Company / Facility
        company = SettingsService.get_setting("company_name", "Apex Industrial Manufacturing")
        facility = SettingsService.get_setting("facility_name", "Plant 1 - Central Warehouse")
        self.lbl_company.setText(company)
        self.lbl_facility.setText(f"Facility: {facility}")

        # Update Storage info
        drive_info = get_drive_info()
        writable, _ = check_storage_writable()
        self.drive_type_val.setText(drive_info["drive_type_desc"])
        self.drive_path_val.setText(drive_info["path"])
        self.storage_mode_val.setText("USB Pendrive (Portable)" if drive_info["is_removable"] else "Fixed Drive (Dev/Station)")
        self.write_perm_val.setText("✅ Writable (Read/Write OK)" if writable else "❌ READ-ONLY WARNING")
        if not writable:
            self.write_perm_val.setStyleSheet("color: #dc2626; font-weight: 700;")
        else:
            self.write_perm_val.setStyleSheet("color: #16a34a; font-weight: 700;")

        # Update DB stats
        db_stats = get_database_stats()
        self.db_engine_val.setText(f"SQLite 3.x (Schema v{db_stats['schema_version']})")
        self.db_journal_val.setText(f"{db_stats['journal_mode']} (High Performance)")
        self.db_size_val.setText(f"{db_stats['size_kb']} KB ({db_stats['table_count']} Tables)")

        ok, msg = check_database_integrity()
        self.db_integrity_val.setText("✅ Verified Clean (OK)" if ok else "⚠️ Warning")
        self.db_integrity_val.setStyleSheet("color: #16a34a; font-weight: 700;" if ok else "color: #dc2626; font-weight: 700;")

    def run_integrity_check(self):
        ok, msg = check_database_integrity()
        if ok:
            QMessageBox.information(self, "Database Integrity OK", f"Local SQLite database check succeeded:\n\n{msg}")
        else:
            QMessageBox.critical(self, "Database Warning", f"Integrity check issue detected:\n\n{msg}")
        self.refresh_dashboard()

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QCheckBox, QPushButton, QGroupBox, QFormLayout,
    QMessageBox, QPlainTextEdit, QScrollArea, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, Signal
from app.services.settings_service import SettingsService
from app.core.config import DB_FILE, LOG_FILE, BACKUPS_DIR
from app.core.logger import get_recent_logs, get_logger
from app.remote.tunnel_manager import get_tunnel_manager

logger = get_logger("IssueSlipApp.SettingsView")


class SettingsView(QWidget):
    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(18)

        # 1. Company & Facility Configuration
        grp_company = QGroupBox("🏢 Company & Warehouse Identification")
        form_company = QFormLayout(grp_company)
        form_company.setLabelAlignment(Qt.AlignLeft)
        form_company.setSpacing(12)

        self.txt_company = QLineEdit()
        self.txt_company.setPlaceholderText("e.g. Apex Industrial Manufacturing Ltd.")
        form_company.addRow("Company Legal Name:", self.txt_company)

        self.txt_facility = QLineEdit()
        self.txt_facility.setPlaceholderText("e.g. Plant 1 - Main Warehouse")
        form_company.addRow("Facility / Warehouse Code:", self.txt_facility)

        self.txt_storekeeper = QLineEdit()
        self.txt_storekeeper.setPlaceholderText("e.g. Storekeeper Shift In-charge")
        form_company.addRow("Default Storekeeper Title:", self.txt_storekeeper)

        self.txt_currency = QLineEdit()
        self.txt_currency.setPlaceholderText("e.g. ₹ or INR or EUR")
        self.txt_currency.setMaxLength(5)
        self.txt_currency.setFixedWidth(80)
        form_company.addRow("Currency Symbol:", self.txt_currency)

        layout.addWidget(grp_company)

        # 2. Issue Slip & Inventory Operational Rules
        grp_rules = QGroupBox("⚖️ Issue Slip & Stock Deduction Rules")
        v_rules = QVBoxLayout(grp_rules)
        v_rules.setSpacing(12)

        form_slip = QFormLayout()
        self.txt_prefix = QLineEdit()
        self.txt_prefix.setPlaceholderText("IS-")
        self.txt_prefix.setFixedWidth(120)
        form_slip.addRow("Issue Slip Number Prefix:", self.txt_prefix)
        v_rules.addLayout(form_slip)

        self.chk_approval = QCheckBox("Require Manager / Supervisor Approval before stock is finalized and deducted")
        self.chk_approval.setToolTip("When enabled, slips remain in DRAFT / PENDING_APPROVAL state until authorized.")
        v_rules.addWidget(self.chk_approval)

        self.chk_negative_stock = QCheckBox("Permit issuing materials even if available physical stock is insufficient (Negative Stock)")
        self.chk_negative_stock.setToolTip("Recommended: OFF. Turning this ON allows stock to drop below zero.")
        self.chk_negative_stock.setStyleSheet("color: #b91c1c; font-weight: 600;")
        v_rules.addWidget(self.chk_negative_stock)

        layout.addWidget(grp_rules)

        # 3. Internet Remote Phone Scanner Access
        grp_remote = QGroupBox("🌐 Internet Mobile Scanner Access (Phone over 4G/5G or Remote Wi-Fi)")
        v_remote = QVBoxLayout(grp_remote)
        v_remote.setSpacing(10)

        lbl_remote_desc = QLabel(
            "Allows mobile phone barcode scanning from anywhere outside the local plant Wi-Fi via an encrypted pipe.\n"
            "Zero data is stored in the cloud: all scans and materials stay on this computer."
        )
        lbl_remote_desc.setStyleSheet("color: #64748b; font-size: 12px;")
        lbl_remote_desc.setWordWrap(True)
        v_remote.addWidget(lbl_remote_desc)

        self.btn_group_remote = QButtonGroup(self)
        self.rad_remote_off = QRadioButton("Disabled — Local Wi-Fi Only (LAN 8443)")
        self.rad_remote_tunnel = QRadioButton("Built-in Cloudflare Tunnel (Automatic, zero configuration, encrypted)")
        self.rad_remote_custom = QRadioButton("Custom Public URL (Named tunnel, reverse proxy or Tailscale Funnel)")

        self.btn_group_remote.addButton(self.rad_remote_off)
        self.btn_group_remote.addButton(self.rad_remote_tunnel)
        self.btn_group_remote.addButton(self.rad_remote_custom)

        v_remote.addWidget(self.rad_remote_off)
        v_remote.addWidget(self.rad_remote_tunnel)
        v_remote.addWidget(self.rad_remote_custom)

        form_custom = QFormLayout()
        self.txt_custom_url = QLineEdit()
        self.txt_custom_url.setPlaceholderText("https://scanner.yourcompany.com")
        form_custom.addRow("Custom Public URL:", self.txt_custom_url)
        v_remote.addLayout(form_custom)

        self.rad_remote_custom.toggled.connect(self._toggle_custom_url_state)
        layout.addWidget(grp_remote)

        # 4. Department Master List
        grp_dept = QGroupBox("🏭 Factory Departments / Cost Centers")
        v_dept = QVBoxLayout(grp_dept)
        v_dept.setSpacing(8)

        lbl_dept_hint = QLabel("Enter recognized departments separated by commas (used in Issue Slip creation):")
        lbl_dept_hint.setStyleSheet("color: #64748b; font-size: 12px;")
        v_dept.addWidget(lbl_dept_hint)

        self.txt_departments = QLineEdit()
        self.txt_departments.setPlaceholderText("BM Qc, Pipe Qc, BM production, pipe production, admin HR, BM Dispatch, store")
        v_dept.addWidget(self.txt_departments)

        layout.addWidget(grp_dept)

        # 5. Storage & Diagnostics Information
        grp_diag = QGroupBox("🔍 Portable File Storage & System Diagnostics")
        v_diag = QVBoxLayout(grp_diag)

        db_path_lbl = QLabel(f"<b>Database File:</b> {DB_FILE}")
        db_path_lbl.setStyleSheet("color: #475569; font-size: 12px;")
        v_diag.addWidget(db_path_lbl)

        log_path_lbl = QLabel(f"<b>Log File:</b> {LOG_FILE}")
        log_path_lbl.setStyleSheet("color: #475569; font-size: 12px;")
        v_diag.addWidget(log_path_lbl)

        backup_path_lbl = QLabel(f"<b>Backup Directory:</b> {BACKUPS_DIR}")
        backup_path_lbl.setStyleSheet("color: #475569; font-size: 12px;")
        v_diag.addWidget(backup_path_lbl)

        h_log_actions = QHBoxLayout()
        btn_refresh_logs = QPushButton("📄 View Recent Log Entries")
        btn_refresh_logs.clicked.connect(self.view_recent_logs)
        h_log_actions.addWidget(btn_refresh_logs)
        h_log_actions.addStretch()
        v_diag.addLayout(h_log_actions)

        self.txt_log_display = QPlainTextEdit()
        self.txt_log_display.setReadOnly(True)
        self.txt_log_display.setFixedHeight(120)
        self.txt_log_display.setVisible(False)
        self.txt_log_display.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 11px; background-color: #0f172a; color: #38bdf8;")
        v_diag.addWidget(self.txt_log_display)

        layout.addWidget(grp_diag)

        # 6. Action Buttons Footer
        h_actions = QHBoxLayout()
        h_actions.addStretch()

        btn_reload = QPushButton("🔄 Reset / Reload")
        btn_reload.clicked.connect(self.load_settings)
        h_actions.addWidget(btn_reload)

        btn_save = QPushButton("💾 Save Application Settings")
        btn_save.setProperty("class", "btn-primary")
        btn_save.clicked.connect(self.save_settings)
        h_actions.addWidget(btn_save)

        layout.addLayout(h_actions)
        layout.addStretch()

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

    def _toggle_custom_url_state(self, checked: bool):
        self.txt_custom_url.setEnabled(checked)

    def load_settings(self):
        settings = SettingsService.get_all_settings()
        self.txt_company.setText(settings.get("company_name", "Apex Industrial Manufacturing"))
        self.txt_facility.setText(settings.get("facility_name", "Plant 1 - Central Warehouse"))
        self.txt_storekeeper.setText(settings.get("storekeeper_name", "Default Storekeeper"))
        self.txt_currency.setText(settings.get("currency_symbol", "₹"))
        self.txt_prefix.setText(settings.get("slip_prefix", "IS-"))
        self.chk_approval.setChecked(settings.get("require_approval", "0") == "1")
        self.chk_negative_stock.setChecked(settings.get("allow_negative_stock", "0") == "1")
        self.txt_departments.setText(settings.get("departments", "Production, Maintenance, Quality, Electrical, Tool Room, Logistics"))

        # Remote access mode
        mode = settings.get("internet_access_mode", "off").lower()
        if mode == "tunnel":
            self.rad_remote_tunnel.setChecked(True)
        elif mode == "custom":
            self.rad_remote_custom.setChecked(True)
        else:
            self.rad_remote_off.setChecked(True)
        self.txt_custom_url.setText(settings.get("custom_public_url", ""))
        self.txt_custom_url.setEnabled(self.rad_remote_custom.isChecked())

    def save_settings(self):
        company = self.txt_company.text().strip()
        facility = self.txt_facility.text().strip()
        prefix = self.txt_prefix.text().strip()

        if not company:
            QMessageBox.warning(self, "Validation Error", "Company legal name cannot be blank.")
            self.txt_company.setFocus()
            return

        if not facility:
            QMessageBox.warning(self, "Validation Error", "Facility / Warehouse identifier cannot be blank.")
            self.txt_facility.setFocus()
            return

        if not prefix:
            prefix = "IS-"

        if self.rad_remote_tunnel.isChecked():
            remote_mode = "tunnel"
        elif self.rad_remote_custom.isChecked():
            remote_mode = "custom"
        else:
            remote_mode = "off"

        data = {
            "company_name": company,
            "facility_name": facility,
            "storekeeper_name": self.txt_storekeeper.text().strip(),
            "currency_symbol": self.txt_currency.text().strip() or "₹",
            "slip_prefix": prefix,
            "require_approval": "1" if self.chk_approval.isChecked() else "0",
            "allow_negative_stock": "1" if self.chk_negative_stock.isChecked() else "0",
            "departments": self.txt_departments.text().strip(),
            "internet_access_mode": remote_mode,
            "custom_public_url": self.txt_custom_url.text().strip()
        }

        ok, msg = SettingsService.save_settings_dict(data)
        if ok:
            # Sync tunnel manager state with new settings
            tm = get_tunnel_manager()
            tm.set_mode(remote_mode, self.txt_custom_url.text().strip())
            if remote_mode in ("tunnel", "custom"):
                tm.start()
            else:
                tm.stop()

            QMessageBox.information(self, "Settings Saved", "Application settings have been stored to the local database.")
            self.settings_saved.emit()
        else:
            QMessageBox.critical(self, "Save Error", f"Could not save settings:\n\n{msg}")

    def view_recent_logs(self):
        lines = get_recent_logs(40)
        self.txt_log_display.setPlainText("".join(lines))
        self.txt_log_display.setVisible(True)

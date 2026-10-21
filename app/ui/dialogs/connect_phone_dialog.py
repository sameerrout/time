import io
import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon, QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog,
    QScrollArea, QWidget, QGroupBox, QTabWidget, QCheckBox
)

from app.core.logger import get_logger
from app.remote.tunnel_manager import get_tunnel_manager, tunnel_signals
from app.server.cert_manager import get_local_ip
from app.server.device_service import DeviceService
from app.server.http_server import get_server, server_signals
from app.services.barcode_service import BarcodeService
from app.services.material_service import MaterialService

logger = get_logger("IssueSlipApp.ConnectPhoneDialog")


class ConnectPhoneDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect Mobile Phone Scanner — TTL Scanner")
        self.setMinimumSize(820, 720)
        self.resize(880, 760)
        self.setStyleSheet("""
            QDialog {
                background-color: #F8FAFC;
            }
            QGroupBox {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 18px;
                font-weight: bold;
                font-size: 13px;
                color: #1E293B;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: #0F172A;
            }
            QLabel {
                color: #334155;
            }
            QPushButton {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            QPushButton:pressed {
                background-color: #1E40AF;
            }
            QPushButton#btnSecondary {
                background-color: #F1F5F9;
                color: #334155;
                border: 1px solid #CBD5E1;
            }
            QPushButton#btnSecondary:hover {
                background-color: #E2E8F0;
            }
            QPushButton#btnDanger {
                background-color: #EF4444;
                color: white;
            }
            QPushButton#btnDanger:hover {
                background-color: #DC2626;
            }
            QTabWidget::pane {
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                background-color: #FFFFFF;
                top: -1px;
            }
            QTabBar::tab {
                background: #E2E8F0;
                color: #475569;
                padding: 8px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: 600;
                font-size: 13px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                color: #0F172A;
                border: 1px solid #CBD5E1;
                border-bottom: 2px solid #2563EB;
            }
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                gridline-color: #F1F5F9;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #475569;
                padding: 6px;
                border: none;
                border-bottom: 2px solid #CBD5E1;
                font-weight: 600;
            }
        """)

        self.server = get_server()
        self.tunnel_manager = get_tunnel_manager()
        self.current_ip = get_local_ip()
        self.server_port = self.server.port if self.server else 8443
        self.pairing_code = DeviceService.get_active_pairing_code()

        self._build_ui()
        self._load_devices()
        self._update_qr_code()
        self._update_remote_qr_code()

        # Connect signals for live updates
        server_signals.device_paired.connect(self._on_device_event)
        server_signals.device_revoked.connect(self._on_device_event)
        tunnel_signals.status_changed.connect(self._on_tunnel_status_changed)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header Title Banner
        header = QFrame()
        header.setStyleSheet("background-color: #1E293B; border-radius: 8px; padding: 14px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 10, 12, 10)

        title_vbox = QVBoxLayout()
        lbl_title = QLabel("📱 TTL Mobile Scanner — Plant Phone Terminal")
        lbl_title.setStyleSheet("color: #FFFFFF; font-size: 17px; font-weight: bold;")
        lbl_sub = QLabel("Scan material QR codes directly using Android or iOS smartphone cameras on local Wi-Fi or Internet.")
        lbl_sub.setStyleSheet("color: #94A3B8; font-size: 12px;")
        title_vbox.addWidget(lbl_title)
        title_vbox.addWidget(lbl_sub)
        h_layout.addLayout(title_vbox)

        # Status badge
        self.lbl_server_status = QLabel("🟢 LAN Server Active")
        self.lbl_server_status.setStyleSheet("""
            background-color: #064E3B;
            color: #6EE7B7;
            padding: 6px 12px;
            border-radius: 12px;
            font-weight: bold;
            font-size: 12px;
        """)
        h_layout.addWidget(self.lbl_server_status, alignment=Qt.AlignRight | Qt.AlignVCenter)
        main_layout.addWidget(header)

        # Tabs for Local Wi-Fi vs Internet Access
        self.tabs = QTabWidget()
        self.tab_wifi = QWidget()
        self.tab_internet = QWidget()
        self._setup_wifi_tab()
        self._setup_internet_tab()
        self.tabs.addTab(self.tab_internet, "🌐 Internet (Phone Scanner)")
        self.tabs.addTab(self.tab_wifi, "📶 Local Wi-Fi (LAN Scanner)")
        main_layout.addWidget(self.tabs, stretch=1)

        # Paired Devices Table (Shared below tabs)
        dev_box = QGroupBox("Paired Mobile Devices & Security Management")
        dev_layout = QVBoxLayout(dev_box)
        dev_layout.setContentsMargins(14, 12, 14, 12)
        dev_layout.setSpacing(8)

        self.table_devices = QTableWidget()
        self.table_devices.setColumnCount(5)
        self.table_devices.setHorizontalHeaderLabels(["ID", "Device Name", "Paired Date", "Last Active", "Action"])
        self.table_devices.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_devices.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_devices.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_devices.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_devices.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_devices.setAlternatingRowColors(True)
        self.table_devices.setSelectionMode(QTableWidget.NoSelection)
        self.table_devices.setFixedHeight(140)
        dev_layout.addWidget(self.table_devices)
        main_layout.addWidget(dev_box)

        # Bottom Buttons
        bottom_h = QHBoxLayout()
        btn_close = QPushButton("Close")
        btn_close.setObjectName("btnSecondary")
        btn_close.clicked.connect(self.accept)
        bottom_h.addStretch(1)
        bottom_h.addWidget(btn_close)
        main_layout.addLayout(bottom_h)

    def _setup_internet_tab(self):
        layout = QVBoxLayout(self.tab_internet)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Internet Pairing Group
        grp = QGroupBox("Internet Scanner Connection (Over Mobile 4G/5G or Remote Wi-Fi)")
        grp_layout = QHBoxLayout(grp)
        grp_layout.setContentsMargins(16, 14, 16, 14)
        grp_layout.setSpacing(18)

        # Left Column: QR Code
        qr_vbox = QVBoxLayout()
        self.lbl_remote_qr = QLabel()
        self.lbl_remote_qr.setFixedSize(190, 190)
        self.lbl_remote_qr.setAlignment(Qt.AlignCenter)
        self.lbl_remote_qr.setStyleSheet("background-color: #FFFFFF; border: 2px solid #E2E8F0; border-radius: 8px;")
        qr_vbox.addWidget(self.lbl_remote_qr, alignment=Qt.AlignCenter)

        self.lbl_remote_qr_hint = QLabel("Scan inside TTL Scanner App")
        self.lbl_remote_qr_hint.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 500;")
        qr_vbox.addWidget(self.lbl_remote_qr_hint, alignment=Qt.AlignCenter)
        grp_layout.addLayout(qr_vbox)

        # Right Column: Tunnel status, URL, pairing code
        info_vbox = QVBoxLayout()
        info_vbox.setSpacing(8)

        # Status row
        h_stat = QHBoxLayout()
        lbl_stat_title = QLabel("Tunnel Status:")
        lbl_stat_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #475569;")
        self.lbl_tunnel_badge = QLabel("Checking...")
        self.lbl_tunnel_badge.setStyleSheet("font-weight: bold; font-size: 12px; padding: 3px 8px; border-radius: 4px; background-color: #E2E8F0; color: #334155;")
        h_stat.addWidget(lbl_stat_title)
        h_stat.addWidget(self.lbl_tunnel_badge)
        h_stat.addStretch()
        info_vbox.addLayout(h_stat)

        # Public URL
        lbl_url_title = QLabel("Public Internet Address:")
        lbl_url_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #475569;")
        self.lbl_remote_url = QLabel("Starting tunnel...")
        self.lbl_remote_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_remote_url.setStyleSheet("""
            background-color: #F1F5F9;
            color: #0F172A;
            padding: 6px 10px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
            font-weight: bold;
            border: 1px solid #CBD5E1;
        """)
        info_vbox.addWidget(lbl_url_title)
        info_vbox.addWidget(self.lbl_remote_url)

        # Pairing Code
        h_code = QHBoxLayout()
        v_code = QVBoxLayout()
        lbl_code_title = QLabel("One-Time Pairing Code (15 min):")
        lbl_code_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #475569;")
        self.lbl_remote_code = QLabel(self.pairing_code)
        self.lbl_remote_code.setStyleSheet("""
            background-color: #FEF3C7;
            color: #92400E;
            padding: 4px 14px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 18px;
            font-weight: bold;
            border: 1px solid #FCD34D;
        """)
        v_code.addWidget(lbl_code_title)
        v_code.addWidget(self.lbl_remote_code)
        h_code.addLayout(v_code)

        btn_refresh = QPushButton("🔄 Refresh Code")
        btn_refresh.setObjectName("btnSecondary")
        btn_refresh.clicked.connect(self._on_refresh_pairing_code)
        h_code.addWidget(btn_refresh, alignment=Qt.AlignBottom)
        info_vbox.addLayout(h_code)

        # Toggle for address-only QR update
        self.chk_include_code = QCheckBox("Include pairing code in QR (Uncheck if updating address only for existing phones)")
        self.chk_include_code.setChecked(True)
        self.chk_include_code.toggled.connect(self._update_remote_qr_code)
        info_vbox.addWidget(self.chk_include_code)

        # Restart notice note
        lbl_note = QLabel(
            "<b>Note:</b> After restarting the software, phones must scan the QR once to update the address (no need to pair again).<br>"
            "Zero data is stored in the cloud. All scans flow directly into this computer's local database."
        )
        lbl_note.setStyleSheet("font-size: 11px; color: #64748B; background: #F8FAFC; border: 1px dashed #CBD5E1; padding: 6px; border-radius: 4px;")
        lbl_note.setWordWrap(True)
        info_vbox.addWidget(lbl_note)

        grp_layout.addLayout(info_vbox, stretch=1)
        layout.addWidget(grp)
        self._refresh_tunnel_ui()

    def _setup_wifi_tab(self):
        scroll = QScrollArea(self.tab_wifi)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(12, 12, 12, 12)
        c_layout.setSpacing(12)

        # 1. Pairing & Connection Group
        pair_box = QGroupBox("1. Mobile Pairing & Quick Scan")
        pair_layout = QHBoxLayout(pair_box)
        pair_layout.setContentsMargins(16, 14, 16, 14)
        pair_layout.setSpacing(20)

        # Left Column: QR Code Display
        qr_container = QVBoxLayout()
        self.lbl_qr_image = QLabel()
        self.lbl_qr_image.setFixedSize(190, 190)
        self.lbl_qr_image.setAlignment(Qt.AlignCenter)
        self.lbl_qr_image.setStyleSheet("background-color: #FFFFFF; border: 2px solid #E2E8F0; border-radius: 8px;")
        qr_container.addWidget(self.lbl_qr_image, alignment=Qt.AlignCenter)

        lbl_qr_hint = QLabel("Scan to Open Scanner PWA")
        lbl_qr_hint.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 500;")
        qr_container.addWidget(lbl_qr_hint, alignment=Qt.AlignCenter)
        pair_layout.addLayout(qr_container)

        # Right Column: Instructions & Codes
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)

        server_url = f"https://{self.current_ip}:{self.server_port}"
        lbl_url_title = QLabel("Server Web Address (Local Wi-Fi):")
        lbl_url_title.setStyleSheet("font-weight: 600; font-size: 12px; color: #475569;")
        self.lbl_url = QLabel(server_url)
        self.lbl_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_url.setStyleSheet("""
            background-color: #F1F5F9;
            color: #0F172A;
            padding: 6px 12px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
            font-weight: bold;
            border: 1px solid #CBD5E1;
        """)
        info_layout.addWidget(lbl_url_title)
        info_layout.addWidget(self.lbl_url)

        code_h = QHBoxLayout()
        code_v = QVBoxLayout()
        lbl_code_title = QLabel("One-Time Pairing Code (Expires in 15m):")
        lbl_code_title.setStyleSheet("font-weight: 600; font-size: 12px; color: #475569;")

        self.lbl_code = QLabel(self.pairing_code)
        self.lbl_code.setStyleSheet("""
            background-color: #FEF3C7;
            color: #92400E;
            padding: 4px 16px;
            border-radius: 6px;
            font-family: 'Consolas', monospace;
            font-size: 18px;
            font-weight: bold;
            border: 1px solid #FCD34D;
        """)
        code_v.addWidget(lbl_code_title)
        code_v.addWidget(self.lbl_code)
        code_h.addLayout(code_v)

        btn_refresh_code = QPushButton("🔄 Refresh Code")
        btn_refresh_code.setObjectName("btnSecondary")
        btn_refresh_code.clicked.connect(self._on_refresh_pairing_code)
        code_h.addWidget(btn_refresh_code, alignment=Qt.AlignBottom)
        info_layout.addLayout(code_h)

        pair_layout.addLayout(info_layout, stretch=1)
        c_layout.addWidget(pair_box)

        # 2. Material Master Catalog Synchronization
        mat_box = QGroupBox("2. Offline Material Master Catalog")
        mat_layout = QHBoxLayout(mat_box)
        mat_layout.setContentsMargins(16, 10, 16, 10)

        mat_info = QVBoxLayout()
        self.lbl_mat_count = QLabel("Material Master: Checking database...")
        self.lbl_mat_count.setStyleSheet("font-weight: bold; color: #1E293B; font-size: 12px;")
        lbl_mat_hint = QLabel("Mobile phones download and cache all materials so scanning functions instantly offline.")
        lbl_mat_hint.setStyleSheet("font-size: 11px; color: #64748B;")
        mat_info.addWidget(self.lbl_mat_count)
        mat_info.addWidget(lbl_mat_hint)
        mat_layout.addLayout(mat_info, stretch=1)

        btn_import_mat = QPushButton("📥 Import Materials (Excel / PDF)")
        btn_import_mat.setObjectName("btnSecondary")
        btn_import_mat.clicked.connect(self._on_import_materials)
        mat_layout.addWidget(btn_import_mat)
        c_layout.addWidget(mat_box)

        scroll.setWidget(container)
        v = QVBoxLayout(self.tab_wifi)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(scroll)
        self._update_material_count()

    def _refresh_tunnel_ui(self):
        mode = self.tunnel_manager.get_mode()
        url = self.tunnel_manager.get_public_url()
        status = self.tunnel_manager.status

        if mode == "off":
            self.lbl_tunnel_badge.setText("Disabled (Turn on in Settings)")
            self.lbl_tunnel_badge.setStyleSheet("background-color: #F1F5F9; color: #64748B; font-weight: bold; padding: 3px 8px; border-radius: 4px;")
            self.lbl_remote_url.setText("Internet access is disabled in Settings")
        elif status == "online" and url:
            self.lbl_tunnel_badge.setText("🟢 Online (Encrypted)")
            self.lbl_tunnel_badge.setStyleSheet("background-color: #064E3B; color: #6EE7B7; font-weight: bold; padding: 3px 8px; border-radius: 4px;")
            self.lbl_remote_url.setText(url)
        elif status == "starting":
            self.lbl_tunnel_badge.setText("🟡 Connecting Tunnel...")
            self.lbl_tunnel_badge.setStyleSheet("background-color: #78350F; color: #FCD34D; font-weight: bold; padding: 3px 8px; border-radius: 4px;")
            self.lbl_remote_url.setText("Establishing secure Cloudflare tunnel...")
        else:
            self.lbl_tunnel_badge.setText("🔴 Offline")
            self.lbl_tunnel_badge.setStyleSheet("background-color: #7F1D1D; color: #FCA5A5; font-weight: bold; padding: 3px 8px; border-radius: 4px;")
            err = self.tunnel_manager.last_error or "Tunnel not connected"
            self.lbl_remote_url.setText(err)

        self._update_remote_qr_code()

    def _on_tunnel_status_changed(self, status: str, url: str, error: str):
        self._refresh_tunnel_ui()

    def _update_qr_code(self):
        server_url = f"https://{self.current_ip}:{self.server_port}/?code={self.pairing_code}"
        pil_img = BarcodeService.generate_pure_qr_image(server_url, box_size=5, border=2)
        if pil_img:
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue())
            self.lbl_qr_image.setPixmap(pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _update_remote_qr_code(self):
        if not hasattr(self, "lbl_remote_qr"):
            return
        url = self.tunnel_manager.get_public_url()
        if not url:
            self.lbl_remote_qr.setText("Turn on Internet Access\nin Settings to show QR")
            return

        code = self.pairing_code if (hasattr(self, "chk_include_code") and self.chk_include_code.isChecked()) else ""
        payload = self.tunnel_manager.get_qr_payload(pairing_code=code)
        json_str = json.dumps(payload, separators=(",", ":"))

        pil_img = BarcodeService.generate_pure_qr_image(json_str, box_size=5, border=2)
        if pil_img:
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue())
            self.lbl_remote_qr.setPixmap(pixmap.scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _on_refresh_pairing_code(self):
        self.pairing_code = DeviceService.generate_pairing_code(expiry_minutes=15)
        self.lbl_code.setText(self.pairing_code)
        if hasattr(self, "lbl_remote_code"):
            self.lbl_remote_code.setText(self.pairing_code)
        self._update_qr_code()
        self._update_remote_qr_code()

    def _update_material_count(self):
        all_mats = MaterialService.get_all(active_only=True)
        self.lbl_mat_count.setText(f"Material Master: {len(all_mats):,} active materials registered in SQLite (Plant 1304 HYDERABAD)")

    def _on_import_materials(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Materials Excel File (or Cancel to use Bundled Master)",
            "",
            "Excel Files (*.xlsx *.xls);;All Files (*)"
        )
        added, updated, errors = MaterialService.import_materials_excel_or_master(file_path if file_path else None)
        self._update_material_count()
        if errors and not (added or updated):
            QMessageBox.warning(self, "Import Warning", f"Issues occurred:\n" + "\n".join(errors[:5]))
        else:
            QMessageBox.information(
                self,
                "Material Master Updated",
                f"Successfully loaded materials:\n• {added} newly added\n• {updated} updated\nTotal active: {len(MaterialService.get_all()):,}"
            )

    def _load_devices(self):
        devices = DeviceService.list_devices()
        self.table_devices.setRowCount(len(devices))

        for row, dev in enumerate(devices):
            id_item = QTableWidgetItem(f"#{dev['id']}")
            id_item.setTextAlignment(Qt.AlignCenter)
            self.table_devices.setItem(row, 0, id_item)

            name_item = QTableWidgetItem(dev["name"])
            self.table_devices.setItem(row, 1, name_item)

            created_item = QTableWidgetItem(str(dev.get("created_at", ""))[:19])
            created_item.setTextAlignment(Qt.AlignCenter)
            self.table_devices.setItem(row, 2, created_item)

            last_seen_item = QTableWidgetItem(str(dev.get("last_seen", ""))[:19])
            last_seen_item.setTextAlignment(Qt.AlignCenter)
            self.table_devices.setItem(row, 3, last_seen_item)

            if dev.get("revoked", 0):
                lbl_rev = QLabel("Revoked")
                lbl_rev.setAlignment(Qt.AlignCenter)
                lbl_rev.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 11px;")
                self.table_devices.setCellWidget(row, 4, lbl_rev)
            else:
                btn_revoke = QPushButton("Revoke")
                btn_revoke.setObjectName("btnDanger")
                btn_revoke.setStyleSheet("background-color: #EF4444; color: white; padding: 4px 8px; font-size: 11px;")
                btn_revoke.clicked.connect(lambda checked=False, d_id=dev["id"], d_name=dev["name"]: self._on_revoke_device(d_id, d_name))
                self.table_devices.setCellWidget(row, 4, btn_revoke)

    def _on_revoke_device(self, device_id: int, device_name: str):
        reply = QMessageBox.question(
            self,
            "Confirm Revoke Device",
            f"Are you sure you want to revoke '{device_name}' (#{device_id})?\n\nThis phone will be disconnected immediately and cannot send any further scans.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            success, msg = DeviceService.revoke_device(device_id)
            if success:
                self._load_devices()
            else:
                QMessageBox.warning(self, "Revocation Failed", msg)

    def _on_device_event(self, _):
        self._load_devices()

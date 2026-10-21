import io
import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QIcon, QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QMessageBox, QWidget, QGroupBox, QApplication
)

from app.core.logger import get_logger
from app.server.cert_manager import get_local_ip
from app.server.device_service import DeviceService
from app.server.http_server import get_server, server_signals
from app.services.barcode_service import BarcodeService

logger = get_logger("IssueSlipApp.ConnectPhoneDialog")


class ConnectPhoneDialog(QDialog):
    """Clean, high-performance pairing dialog for GlobalScan (Play Store) & Mobile Scanners."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect Mobile Barcode Scanner (GlobalScan)")
        self.setMinimumSize(780, 580)
        self.resize(820, 620)
        self.setStyleSheet("""
            QDialog {
                background-color: #F8FAFC;
            }
            QGroupBox {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                margin-top: 14px;
                padding-top: 16px;
                font-weight: 700;
                font-size: 13px;
                color: #1E293B;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
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
                padding: 8px 18px;
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
            QLineEdit {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: #0F172A;
            }
            QLineEdit:focus {
                border-color: #2563EB;
            }
        """)

        self.lan_ip = get_local_ip()
        self.lan_port = 8443
        self.current_code = DeviceService.get_active_pairing_code()

        self.init_ui()
        self.refresh_pairing_qr()

        # Connect live scan signals
        server_signals.scan_received.connect(self._on_live_scan)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Header Banner
        header = QFrame(self)
        header.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 8, 10, 8)

        icon_label = QLabel("📱", header)
        icon_label.setFont(QFont("Segoe UI Emoji", 28))
        h_layout.addWidget(icon_label)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        lbl_title = QLabel("Connect Wireless Mobile Barcode Scanner", header)
        lbl_title.setStyleSheet("font-size: 17px; font-weight: 800; color: #0F172A;")
        lbl_sub = QLabel("Pair with 'GlobalScan: Barcode & QR to PC' from Play Store or scan via any phone browser.", header)
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B;")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        h_layout.addLayout(title_layout, 1)

        main_layout.addWidget(header)

        # Central Two-Column Area
        content_layout = QHBoxLayout()
        content_layout.setSpacing(18)

        # Left Column: QR Code & IP Box
        qr_group = QGroupBox("1. Scanner Connection QR Code", self)
        qr_layout = QVBoxLayout(qr_group)
        qr_layout.setContentsMargins(18, 16, 18, 16)
        qr_layout.setSpacing(12)
        qr_layout.setAlignment(Qt.AlignCenter)

        # QR Image Display (Maintained as self.lbl_qr_image for test compatibility)
        self.lbl_qr_image = QLabel(qr_group)
        self.lbl_qr_image.setFixedSize(240, 240)
        self.lbl_qr_image.setStyleSheet("""
            background-color: #FFFFFF;
            border: 2px solid #E2E8F0;
            border-radius: 10px;
            padding: 8px;
        """)
        self.lbl_qr_image.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(self.lbl_qr_image, 0, Qt.AlignCenter)

        # Address Display (Maintained as self.lbl_url for test compatibility)
        self.lbl_url = QLabel(f"https://{self.lan_ip}:{self.lan_port}", qr_group)
        self.lbl_url.setStyleSheet("""
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 13px;
            font-weight: 700;
            color: #1E293B;
            background-color: #F1F5F9;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            padding: 6px 12px;
        """)
        self.lbl_url.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(self.lbl_url)

        # Copy Address Button
        btn_copy = QPushButton("📋 Copy Server Address", qr_group)
        btn_copy.setObjectName("btnSecondary")
        btn_copy.clicked.connect(self._copy_address)
        qr_layout.addWidget(btn_copy)

        content_layout.addWidget(qr_group, 4)

        # Right Column: Instructions & Setup
        info_group = QGroupBox("2. Setup with Play Store or Phone Camera", self)
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(18, 16, 18, 16)
        info_layout.setSpacing(12)

        # Pairing Code Section (Maintained as self.lbl_code for test compatibility)
        code_box = QFrame(info_group)
        code_box.setStyleSheet("background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; padding: 10px;")
        code_layout = QHBoxLayout(code_box)
        code_layout.setContentsMargins(8, 6, 8, 6)

        code_text_layout = QVBoxLayout()
        code_text_layout.setSpacing(2)
        code_desc = QLabel("One-Time Security Pairing Code:", code_box)
        code_desc.setStyleSheet("font-size: 11px; font-weight: 600; color: #1E40AF;")
        self.lbl_code = QLabel(self.current_code, code_box)
        self.lbl_code.setStyleSheet("font-size: 22px; font-weight: 800; color: #1D4ED8; letter-spacing: 3px;")
        code_text_layout.addWidget(code_desc)
        code_text_layout.addWidget(self.lbl_code)
        code_layout.addLayout(code_text_layout, 1)

        btn_refresh_code = QPushButton("🔄 New Code", code_box)
        btn_refresh_code.setObjectName("btnSecondary")
        btn_refresh_code.clicked.connect(self._refresh_code)
        code_layout.addWidget(btn_refresh_code)

        info_layout.addWidget(code_box)

        # Clear Instruction Steps
        steps_widget = QWidget(info_group)
        steps_layout = QVBoxLayout(steps_widget)
        steps_layout.setContentsMargins(0, 4, 0, 4)
        steps_layout.setSpacing(10)

        step1 = QLabel(
            "<b>Option A: GlobalScan App (Play Store)</b><br>"
            "1. Install <b>'GlobalScan: Barcode & QR to PC'</b> (or <i>Barcode to PC</i>) from Google Play Store.<br>"
            "2. Open the app, select <b>Scan Server QR</b>, and point your camera at the QR code on the left.<br>"
            "3. Scans immediately type into Issue Slip Manager like a physical barcode gun!",
            steps_widget
        )
        step1.setWordWrap(True)
        step1.setStyleSheet("font-size: 12px; line-height: 1.4; color: #334155;")
        steps_layout.addWidget(step1)

        step2 = QLabel(
            "<b>Option B: Instant Camera Scanner (Zero App Install)</b><br>"
            "Open your smartphone Camera or QR app & scan the QR code. It opens the instant mobile scanner web app in your browser with zero download required.",
            steps_widget
        )
        step2.setWordWrap(True)
        step2.setStyleSheet("font-size: 12px; line-height: 1.4; color: #334155;")
        steps_layout.addWidget(step2)

        info_layout.addWidget(steps_widget)

        # Test Scanner Input Box
        test_frame = QFrame(info_group)
        test_frame.setStyleSheet("background-color: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 8px; padding: 10px;")
        tf_layout = QVBoxLayout(test_frame)
        tf_layout.setContentsMargins(6, 4, 6, 4)
        tf_layout.setSpacing(6)

        lbl_test = QLabel("🎯 Scanner Test Field (Scan here to test connection):", test_frame)
        lbl_test.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
        self.txt_test_scan = QLineEdit(test_frame)
        self.txt_test_scan.setPlaceholderText("Scan any barcode with your phone — result appears here...")
        self.lbl_test_result = QLabel("Status: Waiting for scan...", test_frame)
        self.lbl_test_result.setStyleSheet("font-size: 11px; color: #64748B;")

        tf_layout.addWidget(lbl_test)
        tf_layout.addWidget(self.txt_test_scan)
        tf_layout.addWidget(self.lbl_test_result)
        info_layout.addWidget(test_frame)

        info_layout.addStretch()
        content_layout.addWidget(info_group, 5)

        main_layout.addLayout(content_layout, 1)

        # Bottom Action Bar
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        btn_close = QPushButton("Done", self)
        btn_close.setMinimumWidth(100)
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)

        main_layout.addLayout(bottom_layout)

    def refresh_pairing_qr(self):
        """Generate high-contrast QR code encoding direct server address and pairing details."""
        server_url = f"https://{self.lan_ip}:{self.lan_port}"
        self.lbl_url.setText(server_url)

        # Format payload compatible with both standard camera browsers and GlobalScan/custom scanners
        qr_payload = f"{server_url}/#code={self.current_code}"

        try:
            import qrcode
            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(qr_payload)
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF").convert("RGBA")
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue(), "PNG")
            if not pixmap.isNull():
                self.lbl_qr_image.setPixmap(pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.lbl_qr_image.setText("QR Code Error")
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            self.lbl_qr_image.setText("QR Error")

    def _copy_address(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.lbl_url.text())
        self.lbl_test_result.setText("✅ Server address copied to clipboard!")
        self.lbl_test_result.setStyleSheet("font-size: 11px; color: #16A34A; font-weight: 600;")

    def _refresh_code(self):
        self.current_code = DeviceService.generate_pairing_code()
        self.lbl_code.setText(self.current_code)
        self.refresh_pairing_qr()
        self.lbl_test_result.setText("🔄 Generated fresh pairing code.")
        self.lbl_test_result.setStyleSheet("font-size: 11px; color: #2563EB;")

    def _on_live_scan(self, scan_data: dict):
        """Called when a wireless scan is received by the local server."""
        code = scan_data.get("material_code", "") or scan_data.get("barcode", "")
        mode = scan_data.get("mode", "SCAN")
        device = scan_data.get("device_name", "Phone Scanner")
        qty = scan_data.get("qty", 1)

        self.txt_test_scan.setText(code)
        self.lbl_test_result.setText(f"✅ Received from {device}: [{mode}] {code} (Qty: {qty})")
        self.lbl_test_result.setStyleSheet("font-size: 11px; color: #16A34A; font-weight: 700;")

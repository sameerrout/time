import os
import time
import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDoubleSpinBox, QComboBox, QMessageBox,
    QScrollArea, QAbstractItemView, QDateEdit, QFileDialog,
    QInputDialog
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog, QPrintDialog

from app.core.config import DATA_DIR, ICONS_DIR
from app.core.logger import get_logger
from app.services.material_service import MaterialService
from app.server.scan_service import ScanService
from app.services.issue_slip_service import IssueSlipService
from app.services.settings_service import SettingsService
from app.services.issue_slip_pdf_service import IssueSlipPdfService
from app.services.issue_slip_excel_service import IssueSlipExcelService

logger = get_logger("IssueSlipApp.IssueSlipDocumentView")


class BarcodeEntryView(QWidget):
    slip_finalized = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_slip_items: list[dict] = []
        self.last_scan_code: str = ""
        self.last_scan_time: float = 0.0
        self.is_finalized_slip: bool = False

        self.init_ui()
        self.refresh_defaults()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 12, 16, 12)
        root_layout.setSpacing(10)

        # ========================================================
        # 1. Top Control Bar (Operational Tools Above Document)
        # ========================================================
        control_card = QFrame(self)
        control_card.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }
        """)
        card_vbox = QVBoxLayout(control_card)
        card_vbox.setContentsMargins(14, 10, 14, 10)
        card_vbox.setSpacing(10)

        # Internal slip number tracking
        self.txt_slip_no = QLineEdit(self)
        self.txt_slip_no.setVisible(False)

        # Row 1: Action Controls & 2D QR Scanner Input
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        self.btn_new_slip = QPushButton("＋ New Slip", control_card)
        self.btn_new_slip.setFixedHeight(34)
        self.btn_new_slip.clicked.connect(self.start_new_slip)
        row1.addWidget(self.btn_new_slip)

        self.btn_retrieve = QPushButton("🔍 Retrieve", control_card)
        self.btn_retrieve.setFixedHeight(34)
        self.btn_retrieve.clicked.connect(lambda: self.retrieve_slip())
        row1.addWidget(self.btn_retrieve)

        # Vertical Divider
        divider = QFrame(control_card)
        divider.setFrameShape(QFrame.VLine)
        divider.setStyleSheet("color: #cbd5e1;")
        row1.addWidget(divider)

        # 2D QR Code Scanner Input
        lbl_qr = QLabel("📡 2D QR Scanner:", control_card)
        lbl_qr.setStyleSheet("font-size: 13px; font-weight: 700; color: #047857;")
        row1.addWidget(lbl_qr)

        self.txt_qr_scan = QLineEdit(control_card)
        self.txt_qr_scan.setFixedHeight(34)
        self.txt_qr_scan.setPlaceholderText("Scan 2D QR code (Material Name & Code) with wireless scanner...")
        self.txt_qr_scan.setStyleSheet("font-size: 13px; padding: 4px 10px; background: #ffffff;")
        self.txt_qr_scan.returnPressed.connect(self.on_qr_scanned)
        row1.addWidget(self.txt_qr_scan, 1)

        self.btn_scan_add = QPushButton("Scan / Add", control_card)
        self.btn_scan_add.setFixedHeight(34)
        self.btn_scan_add.clicked.connect(self.on_qr_scanned)
        row1.addWidget(self.btn_scan_add)

        # Phone Scanning Toggle
        self.btn_phone_toggle = QPushButton("📱 Phone scanning: ON", control_card)
        self.btn_phone_toggle.setFixedHeight(34)
        self.btn_phone_toggle.setCheckable(True)
        self.btn_phone_toggle.setChecked(True)
        self.btn_phone_toggle.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-weight: 700;
                font-size: 12px;
                padding: 4px 12px;
                border-radius: 6px;
            }
            QPushButton:!checked {
                background-color: #E2E8F0;
                color: #64748B;
            }
        """)
        self.btn_phone_toggle.toggled.connect(self._on_phone_toggle_changed)
        row1.addWidget(self.btn_phone_toggle)

        card_vbox.addLayout(row1)

        # Row 2: Action Buttons Row
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        self.btn_save_draft = QPushButton("💾 Save Draft", control_card)
        self.btn_save_draft.setFixedHeight(34)
        self.btn_save_draft.clicked.connect(self.save_draft)
        row2.addWidget(self.btn_save_draft)

        self.btn_print = QPushButton("🖨 Print / Preview", control_card)
        self.btn_print.setFixedHeight(34)
        self.btn_print.clicked.connect(self.print_preview)
        row2.addWidget(self.btn_print)

        self.btn_export_pdf = QPushButton("📄 Export PDF", control_card)
        self.btn_export_pdf.setFixedHeight(34)
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        row2.addWidget(self.btn_export_pdf)

        self.btn_export_excel = QPushButton("📊 Export Excel", control_card)
        self.btn_export_excel.setFixedHeight(34)
        self.btn_export_excel.clicked.connect(self.export_excel)
        row2.addWidget(self.btn_export_excel)

        row2.addStretch()

        self.lbl_item_counter = QLabel("0 Items on Slip", control_card)
        self.lbl_item_counter.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
        row2.addWidget(self.lbl_item_counter)

        self.btn_clear = QPushButton("✖ Clear Form", control_card)
        self.btn_clear.setFixedHeight(34)
        self.btn_clear.clicked.connect(self.clear_slip)
        row2.addWidget(self.btn_clear)

        self.btn_finalize = QPushButton("✔ Finalize Issue Slip", control_card)
        self.btn_finalize.setProperty("class", "btn-primary")
        self.btn_finalize.setFixedHeight(34)
        self.btn_finalize.setStyleSheet("""
            QPushButton {
                background-color: #1e3a8a;
                color: #ffffff;
                font-size: 13px;
                font-weight: 700;
                padding: 6px 18px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_finalize.clicked.connect(self.finalize_issue_slip)
        row2.addWidget(self.btn_finalize)

        card_vbox.addLayout(row2)

        # Inline Notification Banner (Success / Validation Alert)
        self.banner = QFrame(control_card)
        self.banner.setVisible(False)
        self.banner_layout = QHBoxLayout(self.banner)
        self.banner_layout.setContentsMargins(10, 6, 10, 6)
        self.lbl_banner_msg = QLabel("", self.banner)
        self.lbl_banner_msg.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.banner_layout.addWidget(self.lbl_banner_msg)
        card_vbox.addWidget(self.banner)

        root_layout.addWidget(control_card)

        # ========================================================
        # 2. Scrollable Viewport: Digital Company Issue Slip Template
        # ========================================================
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignHCenter)
        scroll.setStyleSheet("background-color: #94a3b8; border: none;")

        # Paper Container (A4 Portrait Appearance)
        self.paper = QFrame()
        self.paper.setObjectName("paperTemplate")
        self.paper.setFixedWidth(870)
        self.paper.setStyleSheet("""
            QFrame#paperTemplate {
                background-color: #ffffff;
                border: 1.5px solid #000000;
                color: #000000;
            }
            QLabel {
                color: #000000;
                font-family: Arial, Helvetica, sans-serif;
            }
            QLineEdit, QDateEdit, QComboBox {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #94a3b8;
                padding: 2px 4px;
                font-size: 12px;
                border-radius: 2px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1.5px solid #000000;
            }
        """)
        paper_vbox = QVBoxLayout(self.paper)
        paper_vbox.setContentsMargins(18, 16, 18, 16)
        paper_vbox.setSpacing(10)

        # ----------------------------------------------------
        # Document Header: TIME Logo, Company Info, Ref Box
        # ----------------------------------------------------
        top_header_row = QHBoxLayout()
        top_header_row.setSpacing(8)

        # Logo on Left
        self.lbl_logo = QLabel(self.paper)
        logo_path = ICONS_DIR / "company_logo.png"
        if logo_path.exists():
            pix = QPixmap(str(logo_path))
            self.lbl_logo.setPixmap(pix.scaled(130, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_logo.setText("<b>TIME</b>")
            self.lbl_logo.setStyleSheet("font-size: 26px; font-weight: 900;")
        self.lbl_logo.setFixedWidth(135)
        top_header_row.addWidget(self.lbl_logo)

        # Center Company Name and Plant Address
        center_info = QVBoxLayout()
        center_info.setSpacing(2)
        center_info.setAlignment(Qt.AlignCenter)

        self.lbl_comp_name = QLabel("TIME TECHNOPLAST LTD.", self.paper)
        self.lbl_comp_name.setStyleSheet("font-size: 19px; font-weight: 800; text-align: center; color: #000000;")
        self.lbl_comp_name.setAlignment(Qt.AlignCenter)
        center_info.addWidget(self.lbl_comp_name)

        self.lbl_comp_addr = QLabel(
            "Survey No. 787/3 & 4, (V) Kishtapur, Near Ravalkol Chaurastha,\n"
            "Shameerpet Road, Medchal Mdl. & Dist. Hyderabad - 501 401 T.S",
            self.paper
        )
        self.lbl_comp_addr.setStyleSheet("font-size: 11px; text-align: center; color: #000000;")
        self.lbl_comp_addr.setAlignment(Qt.AlignCenter)
        center_info.addWidget(self.lbl_comp_addr)
        top_header_row.addLayout(center_info, 1)

        # Top-Right Reference Box
        ref_frame = QFrame(self.paper)
        ref_frame.setFixedWidth(180)
        ref_frame.setStyleSheet("border: 1px solid #000000; padding: 4px; background: #ffffff;")
        ref_vbox = QVBoxLayout(ref_frame)
        ref_vbox.setContentsMargins(6, 4, 6, 4)
        ref_vbox.setSpacing(2)

        lbl_ref1 = QLabel("Ref. No. TTL-HYD/SPIF-09", ref_frame)
        lbl_ref1.setStyleSheet("font-size: 10px; font-weight: 700; border: none;")
        ref_vbox.addWidget(lbl_ref1)

        lbl_ref2 = QLabel("Rev & Date. 02/01.04.2024", ref_frame)
        lbl_ref2.setStyleSheet("font-size: 10px; font-weight: 700; border: none;")
        ref_vbox.addWidget(lbl_ref2)
        top_header_row.addWidget(ref_frame)

        paper_vbox.addLayout(top_header_row)

        # ----------------------------------------------------
        # Center Banner: ISSUE SLIP (Solid Black Box)
        # ----------------------------------------------------
        banner_frame = QFrame(self.paper)
        banner_frame.setFixedHeight(30)
        banner_frame.setStyleSheet("background-color: #000000; border: none;")
        banner_layout = QHBoxLayout(banner_frame)
        banner_layout.setContentsMargins(0, 0, 0, 0)
        lbl_banner_text = QLabel("ISSUE SLIP", banner_frame)
        lbl_banner_text.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 800; letter-spacing: 1px;")
        lbl_banner_text.setAlignment(Qt.AlignCenter)
        banner_layout.addWidget(lbl_banner_text)
        paper_vbox.addWidget(banner_frame)

        # ----------------------------------------------------
        # Header Fields Section (Two Columns)
        # ----------------------------------------------------
        meta_grid = QHBoxLayout()
        meta_grid.setSpacing(24)

        # Left Column Fields
        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        # 1. Department Name
        f_dept = QHBoxLayout()
        lbl_d = QLabel("Department Name :", self.paper)
        lbl_d.setFixedWidth(130)
        lbl_d.setStyleSheet("font-weight: 700; font-size: 12px;")
        self.combo_dept = QComboBox(self.paper)
        self.combo_dept.setEditable(True)
        self.combo_dept.setFixedHeight(26)
        f_dept.addWidget(lbl_d)
        f_dept.addWidget(self.combo_dept)
        left_col.addLayout(f_dept)

        # 2. Date
        f_date = QHBoxLayout()
        lbl_dt = QLabel("Date            :", self.paper)
        lbl_dt.setFixedWidth(130)
        lbl_dt.setStyleSheet("font-weight: 700; font-size: 12px;")
        self.dt_slip_date = QDateEdit(self.paper)
        self.dt_slip_date.setCalendarPopup(True)
        self.dt_slip_date.setDate(QDate.currentDate())
        self.dt_slip_date.setDisplayFormat("yyyy-MM-dd")
        self.dt_slip_date.setFixedHeight(26)
        f_date.addWidget(lbl_dt)
        f_date.addWidget(self.dt_slip_date)
        left_col.addLayout(f_date)

        # 3. G/L No
        f_gl = QHBoxLayout()
        lbl_gl = QLabel("G/L No          :", self.paper)
        lbl_gl.setFixedWidth(130)
        lbl_gl.setStyleSheet("font-weight: 700; font-size: 12px;")
        self.txt_gl_no = QLineEdit(self.paper)
        self.txt_gl_no.setFixedHeight(26)
        f_gl.addWidget(lbl_gl)
        f_gl.addWidget(self.txt_gl_no)
        left_col.addLayout(f_gl)

        # Internal Cost Center tracking fallback
        self.txt_cost_center = QLineEdit(self)
        self.txt_cost_center.setVisible(False)

        meta_grid.addLayout(left_col, 1)

        # Right Column Fields
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        # 1. Stores Posting No.
        f_spn = QHBoxLayout()
        lbl_spn = QLabel("Stores Posting No. :", self.paper)
        lbl_spn.setFixedWidth(135)
        lbl_spn.setStyleSheet("font-weight: 700; font-size: 12px;")
        self.txt_stores_posting_no = QLineEdit(self.paper)
        self.txt_stores_posting_no.setFixedHeight(26)
        f_spn.addWidget(lbl_spn)
        f_spn.addWidget(self.txt_stores_posting_no)
        right_col.addLayout(f_spn)

        # 2. Store Posting Date
        f_spd = QHBoxLayout()
        lbl_spd = QLabel("Store Posting Date :", self.paper)
        lbl_spd.setFixedWidth(135)
        lbl_spd.setStyleSheet("font-weight: 700; font-size: 12px;")
        self.dt_store_posting_date = QDateEdit(self.paper)
        self.dt_store_posting_date.setCalendarPopup(True)
        self.dt_store_posting_date.setDate(QDate.currentDate())
        self.dt_store_posting_date.setDisplayFormat("yyyy-MM-dd")
        self.dt_store_posting_date.setFixedHeight(26)
        f_spd.addWidget(lbl_spd)
        f_spd.addWidget(self.dt_store_posting_date)
        right_col.addLayout(f_spd)

        # 3. Reservation No.
        f_res = QHBoxLayout()
        lbl_res = QLabel("Reservation No.    :", self.paper)
        lbl_res.setFixedWidth(135)
        lbl_res.setStyleSheet("font-weight: 700; font-size: 12px;")
        self.txt_reservation_no = QLineEdit(self.paper)
        self.txt_reservation_no.setFixedHeight(26)
        f_res.addWidget(lbl_res)
        f_res.addWidget(self.txt_reservation_no)
        right_col.addLayout(f_res)

        # 4. Default Line Helpers: Purpose & Receiver Name
        f_defaults = QHBoxLayout()
        lbl_defs = QLabel("Default Purpose/Recv:", self.paper)
        lbl_defs.setFixedWidth(135)
        lbl_defs.setStyleSheet("font-weight: 700; font-size: 11px; color: #475569;")
        self.txt_default_purpose = QLineEdit(self.paper)
        self.txt_default_purpose.setPlaceholderText("Purpose...")
        self.txt_default_purpose.setFixedHeight(26)
        self.txt_default_receiver = QLineEdit(self.paper)
        self.txt_default_receiver.setPlaceholderText("Receiver...")
        self.txt_default_receiver.setFixedHeight(26)
        f_defaults.addWidget(lbl_defs)
        f_defaults.addWidget(self.txt_default_purpose)
        f_defaults.addWidget(self.txt_default_receiver)
        right_col.addLayout(f_defaults)

        meta_grid.addLayout(right_col, 1)
        paper_vbox.addLayout(meta_grid)

        # ----------------------------------------------------
        # Large Material Table (9 Columns Matching Template)
        # ----------------------------------------------------
        self.table = QTableWidget(self.paper)
        self.table.setColumnCount(10)  # 9 standard columns + 1 Delete Action column
        self.table.setHorizontalHeaderLabels([
            "Sr.\nNo.",
            "Description of\nthe Material",
            "Material Code\nNo.",
            "UOM",
            "Cost Center\nNo.",
            "Required\nQty.",
            "Issued\nQty.",
            "Purpose",
            "Receiver\nName",
            "Action"
        ])
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #ffffff;
                color: #000000;
                font-weight: 700;
                font-size: 11px;
                border: 1px solid #000000;
                padding: 3px 2px;
                text-align: center;
            }
        """)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #000000;
                gridline-color: #000000;
                font-size: 11px;
            }
            QTableWidget::item {
                border-bottom: 1px solid #000000;
                padding: 3px;
            }
        """)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(280)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Column widths matching paper proportions
        header = self.table.horizontalHeader()
        header.resizeSection(0, 38)   # Sr. No.
        header.setSectionResizeMode(1, QHeaderView.Stretch) # Description of the Material
        header.resizeSection(2, 98)   # Material Code No.
        header.resizeSection(3, 46)   # UOM
        header.resizeSection(4, 90)   # Cost Center No.
        header.resizeSection(5, 66)   # Required Qty.
        header.resizeSection(6, 66)   # Issued Qty.
        header.resizeSection(7, 100)  # Purpose
        header.resizeSection(8, 98)   # Receiver Name
        header.resizeSection(9, 46)   # Action (Del)

        paper_vbox.addWidget(self.table)

        # ----------------------------------------------------
        # Footer Signatures Section (3 Columns)
        # ----------------------------------------------------
        sig_box = QHBoxLayout()
        sig_box.setContentsMargins(10, 24, 10, 10)
        sig_box.setSpacing(24)

        # Column 1: Authorised by
        sig1 = QVBoxLayout()
        lbl_line1 = QLabel("____________________________________", self.paper)
        lbl_line1.setAlignment(Qt.AlignCenter)
        lbl_txt1 = QLabel("Authorised by", self.paper)
        lbl_txt1.setAlignment(Qt.AlignCenter)
        lbl_txt1.setStyleSheet("font-weight: 700; font-size: 12px;")
        sig1.addWidget(lbl_line1)
        sig1.addWidget(lbl_txt1)
        sig_box.addLayout(sig1)

        # Column 2: Store Keeper
        sig2 = QVBoxLayout()
        lbl_line2 = QLabel("____________________________________", self.paper)
        lbl_line2.setAlignment(Qt.AlignCenter)
        lbl_txt2 = QLabel("Store Keeper", self.paper)
        lbl_txt2.setAlignment(Qt.AlignCenter)
        lbl_txt2.setStyleSheet("font-weight: 700; font-size: 12px;")
        sig2.addWidget(lbl_line2)
        sig2.addWidget(lbl_txt2)
        sig_box.addLayout(sig2)

        # Column 3: Store (HOD)
        sig3 = QVBoxLayout()
        lbl_line3 = QLabel("____________________________________", self.paper)
        lbl_line3.setAlignment(Qt.AlignCenter)
        lbl_txt3 = QLabel("Store (HOD)", self.paper)
        lbl_txt3.setAlignment(Qt.AlignCenter)
        lbl_txt3.setStyleSheet("font-weight: 700; font-size: 12px;")
        sig3.addWidget(lbl_line3)
        sig3.addWidget(lbl_txt3)
        sig_box.addLayout(sig3)

        paper_vbox.addLayout(sig_box)

        scroll.setWidget(self.paper)
        root_layout.addWidget(scroll, 1)

    # ========================================================
    # Logic & State Management
    # ========================================================
    def refresh_defaults(self):
        """Reset the form to a fresh state with a new sequential slip number."""
        next_no = IssueSlipService.generate_next_slip_no()
        self.txt_slip_no.setText(next_no)
        self.is_finalized_slip = False

        # Load departments
        self.combo_dept.clear()
        depts = SettingsService.get_departments()
        if not depts:
            depts = ["BM Qc", "Pipe Qc", "BM production", "pipe production", "admin HR", "BM Dispatch", "store"]
        self.combo_dept.addItems(depts)

        # Clear fields
        self.dt_slip_date.setDate(QDate.currentDate())
        self.dt_store_posting_date.setDate(QDate.currentDate())
        self.txt_cost_center.clear()
        self.txt_gl_no.clear()
        self.txt_stores_posting_no.clear()
        self.txt_reservation_no.clear()
        self.txt_default_purpose.clear()
        self.txt_default_receiver.clear()

        self.current_slip_items.clear()
        self.render_items_table()
        self.hide_banner()
        self.txt_qr_scan.setFocus()

    def start_new_slip(self):
        """Button action for ＋ New Slip."""
        self.refresh_defaults()
        self.show_banner(f"Prepared New Issue Slip: {self.txt_slip_no.text()}", is_error=False)

    def show_banner(self, message: str, is_error: bool = False):
        if is_error:
            self.banner.setStyleSheet("background-color: #fee2e2; border: 1px solid #fca5a5; border-radius: 6px;")
            self.lbl_banner_msg.setStyleSheet("color: #b91c1c; font-size: 12px; font-weight: 600;")
        else:
            self.banner.setStyleSheet("background-color: #dcfce7; border: 1px solid #86efac; border-radius: 6px;")
            self.lbl_banner_msg.setStyleSheet("color: #15803d; font-size: 12px; font-weight: 600;")
        self.lbl_banner_msg.setText(message)
        self.banner.setVisible(True)

    def hide_banner(self):
        self.banner.setVisible(False)

    def _on_phone_toggle_changed(self, checked: bool):
        if checked:
            self.btn_phone_toggle.setText("📱 Phone scanning: ON")
            self.btn_phone_toggle.setStyleSheet("background-color: #059669; color: #ffffff; font-weight: 700; font-size: 12px; padding: 4px 12px; border-radius: 6px;")
            self.show_banner("📱 Phone scanning enabled. Scans from connected phones will feed this slip.")
        else:
            self.btn_phone_toggle.setText("📱 Phone scanning: OFF")
            self.btn_phone_toggle.setStyleSheet("background-color: #E2E8F0; color: #64748B; font-weight: 700; font-size: 12px; padding: 4px 12px; border-radius: 6px;")
            self.show_banner("Phone scanning disabled for this slip.")

    def handle_phone_scan(self, event_data: dict):
        """Handle incoming scan event from paired mobile phone in ISSUE mode."""
        event_id = str(event_data.get("event_id", "")).strip()

        # A scan the desktop cannot use must be reported as REJECTED (never silently dropped
        # while the database / phone believe it was applied).
        if not self.btn_phone_toggle.isChecked():
            logger.info("Ignored mobile issue scan because phone scanning is OFF.")
            ScanService.mark_event_rejected(event_id, "Phone scanning is OFF on the desktop issue slip.")
            return

        if self.is_finalized_slip:
            self.show_banner("Phone scan ignored: Current slip is already FINALIZED. Click 'New Slip' first.", is_error=True)
            ScanService.mark_event_rejected(event_id, "Desktop slip is already finalized.")
            return

        mat_code = str(event_data.get("material_code", "")).strip()
        mat_name = str(event_data.get("material_name", "")).strip()
        uom = str(event_data.get("uom", "EA")).strip()
        scanned_qty = float(event_data.get("qty", 1.0))
        req_qty = float(event_data.get("required_qty") or scanned_qty)
        purpose = str(event_data.get("purpose") or self.txt_default_purpose.text().strip() or "Plant Production")
        receiver = self.txt_default_receiver.text().strip() or "Staff"
        dev_name = str(event_data.get("device_name", "Mobile"))

        # Check if item with this code already exists in active slip
        existing_item = None
        for item in self.current_slip_items:
            if item.get("material_code", "").upper() == mat_code.upper():
                existing_item = item
                break

        if existing_item:
            existing_item["quantity_issued"] = round(existing_item["quantity_issued"] + scanned_qty, 2)
            if req_qty > existing_item.get("required_qty", 0.0):
                existing_item["required_qty"] = round(existing_item["required_qty"] + req_qty, 2)
            self.render_items_table()
            self.show_banner(f"📱 Phone ({dev_name}): Added {scanned_qty} to existing '{mat_name}' (Total: {existing_item['quantity_issued']} {uom}).")
        else:
            new_item = {
                "sr_no": len(self.current_slip_items) + 1,
                "material_id": event_data.get("material_id", 0),
                "material_code": mat_code,
                "material_name": mat_name,
                "unit": uom,
                "cost_center_no": "",
                "required_qty": req_qty,
                "quantity_issued": scanned_qty,
                "purpose": purpose,
                "receiver_name": receiver,
                "current_stock": float(event_data.get("current_stock", 0.0)),
                "device_name": dev_name
            }
            self.current_slip_items.append(new_item)
            self.render_items_table()
            self.show_banner(f"📱 Phone ({dev_name}): Appended row {len(self.current_slip_items)} — '{mat_name}' ({mat_code}) x {scanned_qty} {uom}.")

        # The scan is now really part of the slip draft
        ScanService.mark_event_applied(event_id)

    # ========================================================
    # 2D QR Code Scanning & Automatic Material Population
    # ========================================================
    def on_qr_scanned(self):
        raw_text = self.txt_qr_scan.text().strip()
        if not raw_text:
            self.show_banner("Please scan a 2D QR code or enter a material code.", is_error=True)
            self.txt_qr_scan.setFocus()
            return

        if self.is_finalized_slip:
            self.show_banner("Cannot add items to a FINALIZED issue slip. Click 'New Slip' to create another.", is_error=True)
            return

        # Parse QR format (Material Name, Material Code, and optional UOM)
        mat_name, mat_code, scanned_uom = self.parse_qr_text(raw_text)

        if not mat_code:
            self.show_banner("Invalid QR format. Could not extract Material Code.", is_error=True)
            self.txt_qr_scan.selectAll()
            return

        # Scanner Debounce: ignore burst duplicate scan if received within 1.5s
        now = time.time()
        if mat_code == self.last_scan_code and (now - self.last_scan_time) < 1.5:
            logger.info(f"Ignored rapid duplicate scanner pulse for '{mat_code}'")
            self.txt_qr_scan.clear()
            return

        self.last_scan_code = mat_code
        self.last_scan_time = now

        # Look up material in SQLite database
        material = MaterialService.get_by_code(mat_code)
        if not material:
            # Fallback check by barcode
            material = MaterialService.get_by_barcode(mat_code)

        if not material:
            self.show_banner(f"❌ Material Code '{mat_code}' not found in database. Item rejected.", is_error=True)
            self.txt_qr_scan.selectAll()
            return

        # Material verified in SQLite
        default_purpose = self.txt_default_purpose.text().strip() or "General Maintenance"
        default_receiver = self.txt_default_receiver.text().strip() or "Operator"

        # Append new item row
        new_item = {
            "sr_no": len(self.current_slip_items) + 1,
            "material_id": material["id"],
            "material_code": material["material_code"],
            "material_name": material["name"],
            "unit": scanned_uom or material["unit"],
            "cost_center_no": "",
            "required_qty": 1.0,
            "quantity_issued": 1.0,
            "purpose": default_purpose,
            "receiver_name": default_receiver,
            "current_stock": float(material["current_stock"])
        }

        self.current_slip_items.append(new_item)
        self.render_items_table()

        self.show_banner(f"✔ Added '{material['name']}' ({material['material_code']}) to row {len(self.current_slip_items)}.")
        self.txt_qr_scan.clear()
        self.txt_qr_scan.setFocus()

    def parse_qr_text(self, text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parses text scanned by wireless 2D QR scanners.
        Supports standard multi-line payload:
        Material Name: [name]
        Material Code: [code]
        UOM: [uom]
        """
        name = None
        code = None
        uom = None
        lines = text.strip().splitlines()
        for line in lines:
            line_str = line.strip()
            if line_str.lower().startswith("material name:"):
                name = line_str.split(":", 1)[1].strip()
            elif line_str.lower().startswith("material code:"):
                code = line_str.split(":", 1)[1].strip()
            elif line_str.lower().startswith("uom:") or line_str.lower().startswith("unit:"):
                uom = line_str.split(":", 1)[1].strip()

        # If not structured key-value lines, treat single token as material code
        if not code and len(lines) == 1:
            code = lines[0].strip()

        return name, code, uom

    # ========================================================
    # Material Table Rendering (Paper Form Grid)
    # ========================================================
    def render_items_table(self):
        # We render either the actual items or at least 8 blank paper-grid rows
        actual_count = len(self.current_slip_items)
        display_rows = max(actual_count, 8)
        self.table.setRowCount(display_rows)

        total_iss_qty = 0.0

        for r in range(display_rows):
            if r < actual_count:
                item = self.current_slip_items[r]
                item["sr_no"] = r + 1
                total_iss_qty += item["quantity_issued"]

                # 0. Sr. No.
                item_sr = QTableWidgetItem(str(item["sr_no"]))
                item_sr.setTextAlignment(Qt.AlignCenter)
                item_sr.setFlags(item_sr.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, 0, item_sr)

                # 1. Description of the Material
                item_desc = QTableWidgetItem(item["material_name"])
                item_desc.setFlags(item_desc.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, 1, item_desc)

                # 2. Material Code No.
                item_code = QTableWidgetItem(item["material_code"])
                item_code.setTextAlignment(Qt.AlignCenter)
                item_code.setFlags(item_code.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, 2, item_code)

                # 3. UOM
                item_uom = QTableWidgetItem(item["unit"])
                item_uom.setTextAlignment(Qt.AlignCenter)
                item_uom.setFlags(item_uom.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, 3, item_uom)

                # 4. Cost Center No. (Editable text)
                txt_cc = QLineEdit(item.get("cost_center_no", ""))
                txt_cc.setStyleSheet("background: #ffffff; border: none; font-size: 11px;")
                txt_cc.textChanged.connect(lambda text, idx=r: self.update_item_field(idx, "cost_center_no", text))
                self.table.setCellWidget(r, 4, txt_cc)

                # 5. Required Qty (Editable SpinBox)
                spin_req = QDoubleSpinBox()
                spin_req.setDecimals(1)
                spin_req.setRange(0.1, 999999.0)
                spin_req.setValue(item["required_qty"])
                spin_req.setStyleSheet("background: #ffffff; border: none; font-weight: 600;")
                spin_req.valueChanged.connect(lambda val, idx=r: self.update_item_qty(idx, "required_qty", val))
                self.table.setCellWidget(r, 5, spin_req)

                # 6. Issued Qty (Editable SpinBox)
                spin_iss = QDoubleSpinBox()
                spin_iss.setDecimals(1)
                spin_iss.setRange(0.1, 999999.0)
                spin_iss.setValue(item["quantity_issued"])
                spin_iss.setStyleSheet("background: #ffffff; border: none; font-weight: 700; color: #1e3a8a;")
                spin_iss.valueChanged.connect(lambda val, idx=r: self.update_item_qty(idx, "quantity_issued", val))
                self.table.setCellWidget(r, 6, spin_iss)

                # 7. Purpose (Editable text)
                txt_p = QLineEdit(item.get("purpose", ""))
                txt_p.setStyleSheet("background: #ffffff; border: none;")
                txt_p.textChanged.connect(lambda text, idx=r: self.update_item_field(idx, "purpose", text))
                self.table.setCellWidget(r, 7, txt_p)

                # 8. Receiver Name (Editable text)
                txt_rec = QLineEdit(item.get("receiver_name", ""))
                txt_rec.setStyleSheet("background: #ffffff; border: none;")
                txt_rec.textChanged.connect(lambda text, idx=r: self.update_item_field(idx, "receiver_name", text))
                self.table.setCellWidget(r, 8, txt_rec)

                # 9. Action (Remove row button)
                btn_del = QPushButton("✖")
                btn_del.setToolTip("Remove this row")
                btn_del.setStyleSheet("background-color: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; font-size: 11px;")
                btn_del.clicked.connect(lambda _, idx=r: self.remove_item_row(idx))
                self.table.setCellWidget(r, 9, btn_del)

            else:
                # Blank ruled paper lines
                for c in range(10):
                    blank_item = QTableWidgetItem("")
                    blank_item.setFlags(Qt.NoItemFlags)
                    self.table.setItem(r, c, blank_item)
                    self.table.removeCellWidget(r, c)

        self.lbl_item_counter.setText(f"{actual_count} Items on Slip  |  Total Issued: {total_iss_qty:.1f}")

    def update_item_qty(self, index: int, field: str, value: float):
        if 0 <= index < len(self.current_slip_items):
            self.current_slip_items[index][field] = float(value)

    def update_item_field(self, index: int, field: str, value: str):
        if 0 <= index < len(self.current_slip_items):
            self.current_slip_items[index][field] = value.strip()

    def remove_item_row(self, index: int):
        if self.is_finalized_slip:
            self.show_banner("Cannot remove items from a finalized slip.", is_error=True)
            return

        if 0 <= index < len(self.current_slip_items):
            removed = self.current_slip_items.pop(index)
            self.render_items_table()
            self.show_banner(f"Removed '{removed['material_name']}' from issue slip.")

    def clear_slip(self):
        if not self.current_slip_items:
            self.refresh_defaults()
            return

        reply = QMessageBox.question(
            self,
            "Clear Current Slip",
            "Are you sure you want to discard all items and start over?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.refresh_defaults()

    # ========================================================
    # Draft Saving & Retrieval
    # ========================================================
    def collect_slip_data(self) -> dict:
        return {
            "slip_no": self.txt_slip_no.text().strip(),
            "department": self.combo_dept.currentText().strip(),
            "slip_date": self.dt_slip_date.date().toString("yyyy-MM-dd"),
            "cost_center_no": self.txt_cost_center.text().strip(),
            "gl_no": self.txt_gl_no.text().strip(),
            "stores_posting_no": self.txt_stores_posting_no.text().strip(),
            "store_posting_date": self.dt_store_posting_date.date().toString("yyyy-MM-dd"),
            "reservation_no": self.txt_reservation_no.text().strip(),
            "receiver": self.txt_default_receiver.text().strip() or "General Store",
            "purpose": self.txt_default_purpose.text().strip() or "Standard Issue",
            "remarks": "",
            "created_by": SettingsService.get_setting("storekeeper_name", "Storekeeper")
        }

    def save_draft(self):
        """Save slip state as DRAFT in SQLite without stock deduction."""
        slip_data = self.collect_slip_data()

        ok, msg, slip_no = IssueSlipService.save_draft_slip(slip_data, self.current_slip_items)
        if ok:
            self.show_banner(f"✔ {msg}")
            QMessageBox.information(self, "Draft Saved", f"Issue Slip draft '{slip_no}' saved successfully.")
        else:
            self.show_banner(msg, is_error=True)
            QMessageBox.critical(self, "Save Draft Error", msg)

    def retrieve_slip(self, slip_no: str = ""):
        """Retrieve existing draft or finalized slip by its slip number."""
        target_no = slip_no.strip() if slip_no else ""
        if not target_no:
            if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                entered, ok = QInputDialog.getText(
                    self,
                    "Retrieve Issue Slip",
                    "Enter Issue Slip Number to retrieve (e.g. IS-20261020-0001):",
                    text=self.txt_slip_no.text()
                )
                if not ok or not entered.strip():
                    return
                target_no = entered.strip()
            else:
                target_no = self.txt_slip_no.text().strip()

        if not target_no:
            self.show_banner("Please enter an Issue Slip Number to retrieve.", is_error=True)
            return

        slip = IssueSlipService.get_issue_slip(target_no)
        if not slip:
            self.show_banner(f"No existing record found for Issue Slip Number: '{target_no}'.", is_error=True)
            return

        # Populate header fields
        self.txt_slip_no.setText(slip.get("slip_no", target_no))
        idx = self.combo_dept.findText(slip.get("department", ""))
        if idx >= 0:
            self.combo_dept.setCurrentIndex(idx)
        else:
            self.combo_dept.setEditText(slip.get("department", ""))

        if slip.get("slip_date"):
            qdate = QDate.fromString(slip["slip_date"], "yyyy-MM-dd")
            if qdate.isValid():
                self.dt_slip_date.setDate(qdate)

        if slip.get("store_posting_date"):
            qdate_p = QDate.fromString(slip["store_posting_date"], "yyyy-MM-dd")
            if qdate_p.isValid():
                self.dt_store_posting_date.setDate(qdate_p)

        self.txt_cost_center.setText(slip.get("cost_center_no", ""))
        self.txt_gl_no.setText(slip.get("gl_no", ""))
        self.txt_stores_posting_no.setText(slip.get("stores_posting_no", ""))
        self.txt_reservation_no.setText(slip.get("reservation_no", ""))
        self.txt_default_receiver.setText(slip.get("receiver", ""))
        self.txt_default_purpose.setText(slip.get("purpose", ""))

        # Populate items
        self.current_slip_items = []
        for itm in slip.get("items", []):
            self.current_slip_items.append({
                "sr_no": itm.get("sr_no", len(self.current_slip_items) + 1),
                "material_id": itm["material_id"],
                "material_code": itm["material_code"],
                "material_name": itm["material_name"],
                "unit": itm["unit"],
                "cost_center_no": itm.get("cost_center_no", ""),
                "required_qty": float(itm.get("required_qty", itm.get("quantity_issued", 1.0))),
                "quantity_issued": float(itm.get("quantity_issued", 1.0)),
                "purpose": itm.get("purpose", slip.get("purpose", "")),
                "receiver_name": itm.get("receiver_name", slip.get("receiver", "")),
                "current_stock": 0.0
            })

        self.is_finalized_slip = (slip.get("status") == "FINALIZED")
        self.render_items_table()

        if self.is_finalized_slip:
            self.show_banner(f"⚠ Retrieved FINALIZED Slip '{target_no}'. Stock has already been deducted. Record is read-only.", is_error=True)
            self.btn_finalize.setEnabled(False)
            self.btn_save_draft.setEnabled(False)
        else:
            self.show_banner(f"✔ Retrieved DRAFT Slip '{target_no}' with {len(self.current_slip_items)} items.")
            self.btn_finalize.setEnabled(True)
            self.btn_save_draft.setEnabled(True)

    # ========================================================
    # Stock Validation & Finalization
    # ========================================================
    def finalize_issue_slip(self):
        if not self.current_slip_items:
            self.show_banner("Cannot finalize an empty issue slip. Scan at least one material.", is_error=True)
            self.txt_qr_scan.setFocus()
            return

        slip_data = self.collect_slip_data()

        if not slip_data["department"]:
            self.show_banner("Department Name is required.", is_error=True)
            self.combo_dept.setFocus()
            return

        # Pre-validate quantities
        for idx, itm in enumerate(self.current_slip_items, start=1):
            if itm["quantity_issued"] <= 0:
                self.show_banner(f"Row {idx}: Issued quantity must be greater than zero.", is_error=True)
                return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Confirm Final Issue",
            f"Finalize Issue Slip '{slip_data['slip_no']}' with {len(self.current_slip_items)} items?\n\n"
            "This will permanently deduct physical inventory and record entries in the stock movement ledger.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        success, msg, slip_no = IssueSlipService.create_and_finalize_slip(slip_data, self.current_slip_items)

        if success:
            QMessageBox.information(
                self,
                "Issue Slip Finalized",
                f"✔ {msg}\n\nPhysical inventory has been deducted and logged to the immutable ledger."
            )
            self.is_finalized_slip = True
            self.show_banner(f"✔ Issue Slip {slip_no} completed and locked.")
            self.slip_finalized.emit(slip_no)
            self.btn_finalize.setEnabled(False)
            self.btn_save_draft.setEnabled(False)
        else:
            QMessageBox.critical(self, "Finalization Blocked", f"Could not finalize issue slip:\n\n{msg}")
            self.show_banner(msg, is_error=True)

    # ========================================================
    # Printing & PDF Export (Matching Paper Template)
    # ========================================================
    def export_pdf(self):
        """Export selectable-text A4 PDF matching the company paper template."""
        slip_data = self.collect_slip_data()
        default_filename = f"Issue_Slip_{slip_data['slip_no']}.pdf"

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Issue Slip PDF", str(DATA_DIR / default_filename), "PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            ok = IssueSlipPdfService.generate_issue_slip_pdf(slip_data, self.current_slip_items, path)
            if ok:
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    QMessageBox.information(
                        self, "PDF Exported", f"Company Issue Slip PDF exported successfully to:\n\n{path}"
                    )
                self.show_banner(f"✔ Exported PDF to: {Path(path).name}")
            else:
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    QMessageBox.critical(self, "Export Failed", "Failed to generate Issue Slip PDF.")

    def export_excel(self):
        """Export formatted Excel workbook (.xlsx) matching the company paper template."""
        slip_data = self.collect_slip_data()
        default_filename = f"Issue_Slip_{slip_data['slip_no']}.xlsx"

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Issue Slip Excel", str(DATA_DIR / default_filename), "Excel Workbooks (*.xlsx);;All Files (*)"
        )
        if path:
            ok = IssueSlipExcelService.generate_issue_slip_excel(slip_data, self.current_slip_items, path)
            if ok:
                self.show_banner(f"✔ Exported Issue Slip Excel to: {Path(path).name}")
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    QMessageBox.information(
                        self,
                        "Excel Export Successful",
                        f"Issue Slip Excel exported successfully:\n\n{path}"
                    )
            else:
                self.show_banner("Failed to export Excel workbook.", is_error=True)
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    QMessageBox.critical(self, "Export Failed", "Could not generate Excel workbook.")

    def print_preview(self):
        """Launch native Qt Print Preview Dialog for the issue slip."""
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageOrientation(QPrinter.Portrait)

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(f"Print Preview - Issue Slip {self.txt_slip_no.text()}")
        preview.paintRequested.connect(self.paint_print_document)
        preview.exec()

    def paint_print_document(self, printer: QPrinter):
        """Render vector graphics matching paper template to printer or PDF canvas."""
        # Temporary PDF render to print using IssueSlipPdfService or direct QPainter
        temp_pdf = str(DATA_DIR / "temp_print_preview.pdf")
        slip_data = self.collect_slip_data()
        IssueSlipPdfService.generate_issue_slip_pdf(slip_data, self.current_slip_items, temp_pdf)

        painter = QPainter(printer)
        # Render paper widget snapshot onto high-res printer canvas
        target_rect = printer.pageRect(QPrinter.DevicePixel).toRect()
        pix = self.paper.grab()
        scaled_pix = pix.scaled(target_rect.width(), target_rect.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap(0, 0, scaled_pix)
        painter.end()

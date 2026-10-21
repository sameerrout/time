import os
import time
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDoubleSpinBox, QComboBox, QMessageBox,
    QScrollArea, QAbstractItemView, QFileDialog, QFormLayout,
    QGroupBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from app.core.config import DATA_DIR
from app.core.logger import get_logger
from app.services.purchased_material_service import PurchasedMaterialService
from app.server.scan_service import ScanService
from app.services.settings_service import SettingsService

logger = get_logger("IssueSlipApp.PurchasedMaterialView")


class PurchasedMaterialView(QWidget):
    stock_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: list[dict] = []
        self.last_scan_code: str = ""
        self.last_scan_time: float = 0.0
        # Phone scan waiting for the user to press 'Receive Stock into Plant'
        self._pending_phone_event_id: str = ""
        self._pending_phone_code: str = ""

        self.init_ui()
        self.refresh_records()

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 18, 24, 18)
        root_layout.setSpacing(14)

        # ----------------------------------------------------
        # 1. Header Section
        # ----------------------------------------------------
        hdr_box = QVBoxLayout()
        hdr_box.setSpacing(2)
        lbl_title = QLabel("Purchased Material (Plant Inward Entry)", self)
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0f172a;")
        lbl_sub = QLabel("Scan incoming material QR codes entering the plant. Automatically updates physical stock, tracks prices, and maintains historical closing balances.", self)
        lbl_sub.setStyleSheet("font-size: 13px; color: #64748b;")
        hdr_box.addWidget(lbl_title)
        hdr_box.addWidget(lbl_sub)
        root_layout.addLayout(hdr_box)

        # ----------------------------------------------------
        # 2. Inward Entry Card (Scanner + Inputs)
        # ----------------------------------------------------
        entry_card = QFrame(self)
        entry_card.setProperty("class", "card")
        entry_layout = QVBoxLayout(entry_card)
        entry_layout.setContentsMargins(18, 14, 18, 14)
        entry_layout.setSpacing(12)

        # Scanner bar
        scan_row = QHBoxLayout()
        scan_row.setSpacing(10)
        lbl_qr = QLabel("📷 2D QR Scanner:", entry_card)
        lbl_qr.setStyleSheet("font-weight: 700; font-size: 13px; color: #1e3a8a;")
        scan_row.addWidget(lbl_qr)

        self.txt_qr_scan = QLineEdit(entry_card)
        self.txt_qr_scan.setFixedHeight(34)
        self.txt_qr_scan.setPlaceholderText("Scan 2D QR code (Material Name, Code, UOM) or type code and press Enter...")
        self.txt_qr_scan.setStyleSheet("font-size: 13px; padding: 4px 10px; background: #ffffff;")
        self.txt_qr_scan.returnPressed.connect(self.on_qr_scanned)
        scan_row.addWidget(self.txt_qr_scan, 1)

        self.btn_scan = QPushButton("Scan / Lookup", entry_card)
        self.btn_scan.setFixedHeight(34)
        self.btn_scan.clicked.connect(self.on_qr_scanned)
        scan_row.addWidget(self.btn_scan)

        # Auto-Receive Phone Scans Toggle
        self.btn_auto_receive = QPushButton("⚡ Auto-receive phone scans: OFF", entry_card)
        self.btn_auto_receive.setFixedHeight(34)
        self.btn_auto_receive.setCheckable(True)
        self.btn_auto_receive.setChecked(False)
        self.btn_auto_receive.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                font-weight: 700;
                font-size: 11px;
                padding: 4px 10px;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
            }
            QPushButton:checked {
                background-color: #059669;
                color: #ffffff;
                border: 1px solid #047857;
            }
        """)
        self.btn_auto_receive.toggled.connect(self._on_auto_receive_toggled)
        scan_row.addWidget(self.btn_auto_receive)

        entry_layout.addLayout(scan_row)

        # Inputs Grid
        inputs_row = QHBoxLayout()
        inputs_row.setSpacing(14)

        # Col 1: Material Code & Name
        c1 = QVBoxLayout()
        c1.setSpacing(3)
        lbl_c = QLabel("Material Code *:", entry_card)
        lbl_c.setStyleSheet("font-weight: 600; font-size: 11px;")
        self.txt_code = QLineEdit(entry_card)
        self.txt_code.setFixedHeight(30)
        self.txt_code.textChanged.connect(self.on_code_changed)
        c1.addWidget(lbl_c)
        c1.addWidget(self.txt_code)

        lbl_n = QLabel("Material Name *:", entry_card)
        lbl_n.setStyleSheet("font-weight: 600; font-size: 11px;")
        self.txt_name = QLineEdit(entry_card)
        self.txt_name.setFixedHeight(30)
        c1.addWidget(lbl_n)
        c1.addWidget(self.txt_name)
        inputs_row.addLayout(c1, 2)

        # Col 2: UOM & recived Qty
        c2 = QVBoxLayout()
        c2.setSpacing(3)
        lbl_u = QLabel("UOM:", entry_card)
        lbl_u.setStyleSheet("font-weight: 600; font-size: 11px;")
        self.txt_uom = QLineEdit(entry_card)
        self.txt_uom.setFixedHeight(30)
        self.txt_uom.setText("PCS")
        c2.addWidget(lbl_u)
        c2.addWidget(self.txt_uom)

        lbl_rec = QLabel("recived Qty *:", entry_card)
        lbl_rec.setStyleSheet("font-weight: 700; font-size: 11px; color: #15803d;")
        self.spin_received = QDoubleSpinBox(entry_card)
        self.spin_received.setFixedHeight(30)
        self.spin_received.setRange(0.1, 999999.0)
        self.spin_received.setDecimals(1)
        self.spin_received.setValue(1.0)
        self.spin_received.setStyleSheet("font-weight: 700; color: #15803d;")
        self.spin_received.valueChanged.connect(self.calculate_live_previews)
        c2.addWidget(lbl_rec)
        c2.addWidget(self.spin_received)
        inputs_row.addLayout(c2, 1)

        # Col 3: unit price & GST
        c3 = QVBoxLayout()
        c3.setSpacing(3)
        lbl_up = QLabel("unit price:", entry_card)
        lbl_up.setStyleSheet("font-weight: 600; font-size: 11px;")
        self.spin_unit_price = QDoubleSpinBox(entry_card)
        self.spin_unit_price.setFixedHeight(30)
        self.spin_unit_price.setRange(0.0, 999999.0)
        self.spin_unit_price.setDecimals(2)
        self.spin_unit_price.setPrefix("₹ ")
        self.spin_unit_price.setValue(0.0)
        self.spin_unit_price.valueChanged.connect(self.calculate_live_previews)
        c3.addWidget(lbl_up)
        c3.addWidget(self.spin_unit_price)

        lbl_gst = QLabel("GST (%):", entry_card)
        lbl_gst.setStyleSheet("font-weight: 600; font-size: 11px; color: #1e3a8a;")
        self.spin_gst = QDoubleSpinBox(entry_card)
        self.spin_gst.setFixedHeight(30)
        self.spin_gst.setRange(0.0, 100.0)
        self.spin_gst.setDecimals(1)
        self.spin_gst.setValue(18.0)
        self.spin_gst.setSuffix(" %")
        self.spin_gst.valueChanged.connect(self.calculate_live_previews)
        c3.addWidget(lbl_gst)
        c3.addWidget(self.spin_gst)
        inputs_row.addLayout(c3, 1)

        # Col 4: Total price & Commit Button
        c4 = QVBoxLayout()
        c4.setSpacing(3)
        lbl_tot = QLabel("Total price:", entry_card)
        lbl_tot.setStyleSheet("font-weight: 700; font-size: 11px; color: #0f172a;")
        self.lbl_total_val = QLabel("₹ 0.00", entry_card)
        self.lbl_total_val.setFixedHeight(30)
        self.lbl_total_val.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a; padding: 4px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px;")
        self.lbl_total_val.setAlignment(Qt.AlignCenter)
        c4.addWidget(lbl_tot)
        c4.addWidget(self.lbl_total_val)

        self.btn_receive = QPushButton("📥 Receive Stock into Plant", entry_card)
        self.btn_receive.setProperty("class", "btn-primary")
        self.btn_receive.setFixedHeight(32)
        self.btn_receive.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.btn_receive.clicked.connect(self.record_inward_entry)
        c4.addWidget(self.btn_receive)
        inputs_row.addLayout(c4, 1)

        entry_layout.addLayout(inputs_row)
        root_layout.addWidget(entry_card)

        # ----------------------------------------------------
        # 3. Notification Banner
        # ----------------------------------------------------
        self.banner = QFrame(self)
        self.banner.setVisible(False)
        self.banner_layout = QHBoxLayout(self.banner)
        self.banner_layout.setContentsMargins(12, 6, 12, 6)
        self.lbl_banner_msg = QLabel("", self.banner)
        self.lbl_banner_msg.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.banner_layout.addWidget(self.lbl_banner_msg)
        root_layout.addWidget(self.banner)

        # ----------------------------------------------------
        # 4. Toolbar & KPI Stats Bar
        # ----------------------------------------------------
        tool_row = QHBoxLayout()
        tool_row.setSpacing(12)

        self.txt_search = QLineEdit(self)
        self.txt_search.setPlaceholderText("🔍 Filter by Material Code, Name, or Receipt No...")
        self.txt_search.setFixedHeight(34)
        self.txt_search.setFixedWidth(280)
        self.txt_search.textChanged.connect(self.refresh_records)
        tool_row.addWidget(self.txt_search)

        self.btn_export_excel = QPushButton("📊 Export Excel", self)
        self.btn_export_excel.setFixedHeight(34)
        self.btn_export_excel.clicked.connect(self.export_excel)
        tool_row.addWidget(self.btn_export_excel)

        self.btn_export_pdf = QPushButton("📄 Export PDF", self)
        self.btn_export_pdf.setFixedHeight(34)
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        tool_row.addWidget(self.btn_export_pdf)

        self.btn_refresh = QPushButton("🔄 Refresh", self)
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.clicked.connect(self.refresh_records)
        tool_row.addWidget(self.btn_refresh)

        tool_row.addStretch()

        # KPI Counter Badges
        self.lbl_kpi_count = QLabel("Receipts: 0", self)
        self.lbl_kpi_count.setStyleSheet("background: #f1f5f9; padding: 6px 12px; border-radius: 6px; font-weight: 600; font-size: 12px;")
        tool_row.addWidget(self.lbl_kpi_count)

        self.lbl_kpi_qty = QLabel("Total Qty: 0.0", self)
        self.lbl_kpi_qty.setStyleSheet("background: #dcfce7; color: #166534; padding: 6px 12px; border-radius: 6px; font-weight: 700; font-size: 12px;")
        tool_row.addWidget(self.lbl_kpi_qty)

        self.lbl_kpi_val = QLabel("Total Value: ₹0.00", self)
        self.lbl_kpi_val.setStyleSheet("background: #eff6ff; color: #1e40af; padding: 6px 12px; border-radius: 6px; font-weight: 700; font-size: 12px;")
        tool_row.addWidget(self.lbl_kpi_val)

        root_layout.addLayout(tool_row)

        # ----------------------------------------------------
        # 5. The Main Inward Register Table (Exact Columns)
        # ----------------------------------------------------
        self.table = QTableWidget(self)
        self.table.setColumnCount(9)  # 8 specified columns + 1 Action column
        self.table.setHorizontalHeaderLabels([
            "S no",
            "material code",
            "material name",
            "uom",
            "recived Qty",
            "unit price",
            "GST",
            "Total price",
            "Action"
        ])
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #64748b;
                gridline-color: #94a3b8;
                font-size: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }
            QTableWidget::item {
                padding: 5px 8px;
                border-right: 1px solid #cbd5e1;
                border-bottom: 1px solid #cbd5e1;
            }
            QTableWidget::item:selected {
                background-color: #dbeafe;
                color: #0f172a;
            }
            QHeaderView::section:horizontal {
                background-color: #0e4377;
                color: #ffffff;
                font-weight: 700;
                font-size: 12px;
                border: 1px solid #09325a;
                padding: 6px 8px;
            }
            QHeaderView::section:vertical {
                background-color: #f8fafc;
                color: #64748b;
                font-size: 11px;
                font-weight: 600;
                border-right: 1px solid #cbd5e1;
                border-bottom: 1px solid #cbd5e1;
                padding: 0 6px;
            }
        """)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setFixedHeight(38)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Wider columns (Excel style)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.resizeSection(0, 65)   # S no
        h.resizeSection(1, 150)  # material code
        h.setSectionResizeMode(2, QHeaderView.Stretch)  # material name
        h.resizeSection(3, 85)   # uom
        h.resizeSection(4, 120)  # recived Qty
        h.resizeSection(5, 120)  # unit price
        h.resizeSection(6, 95)   # GST
        h.resizeSection(7, 135)  # Total price
        h.resizeSection(8, 65)   # Action

        root_layout.addWidget(self.table, 1)

    def _on_auto_receive_toggled(self, checked: bool):
        if checked:
            self.btn_auto_receive.setText("⚡ Auto-receive phone scans: ON")
            self.show_banner("⚡ Auto-receive enabled: Scans from phones will post immediately into the inward register.")
        else:
            self.btn_auto_receive.setText("⚡ Auto-receive phone scans: OFF")
            self.show_banner("Auto-receive disabled: Scans will fill the form fields for operator verification.")

    def handle_phone_scan(self, event_data: dict):
        """Handle incoming scan event from paired mobile phone in RECEIVE mode."""
        mat_code = str(event_data.get("material_code", "")).strip()
        mat_name = str(event_data.get("material_name", "")).strip()
        uom = str(event_data.get("uom", "PCS")).strip() or "PCS"
        rec_qty = float(event_data.get("qty", 1.0))
        unit_price = float(event_data.get("unit_price", 0.0))
        gst_percent = float(event_data.get("gst_pct", 18.0))
        dev_name = str(event_data.get("device_name", "Mobile"))
        event_id = str(event_data.get("event_id", "")).strip()

        # A newer scan overwrites the form, so an older not-yet-posted scan can no longer be used.
        if self._pending_phone_event_id:
            ScanService.mark_event_rejected(
                self._pending_phone_event_id, "Replaced by a newer scan before it was posted on the desktop.")
            self._pending_phone_event_id = ""
            self._pending_phone_code = ""

        # Fill the form fields (same as existing scanner box and fields)
        self.txt_code.setText(mat_code)
        if mat_name:
            self.txt_name.setText(mat_name)
        if uom:
            self.txt_uom.setText(uom)
        self.spin_received.setValue(rec_qty)
        self.spin_unit_price.setValue(unit_price)
        self.spin_gst.setValue(gst_percent)
        self.calculate_live_previews()

        if self.btn_auto_receive.isChecked():
            # Post directly into grid and update stock!
            data = {
                "material_code": mat_code,
                "material_name": mat_name or self.txt_name.text().strip(),
                "uom": uom or self.txt_uom.text().strip() or "PCS",
                "received_qty": rec_qty,
                "unit_price": unit_price,
                "gst_percent": gst_percent,
                "device_name": dev_name,
                "supplier": f"Phone: {dev_name}",
                "challan_no": "",
                "remarks": f"Auto-received from mobile terminal ({dev_name})"
            }
            ok, msg, rec_id = PurchasedMaterialService.record_inward_purchase(data)
            if ok:
                ScanService.mark_event_applied(event_id)
                self.show_banner(f"⚡ [Auto-Received] {rec_qty} {uom} for '{mat_name}' ({mat_code}) from {dev_name}. Stock updated!")
                self.stock_updated.emit()
                self.refresh_records()
                # Clear form fields for next entry
                self.txt_code.clear()
                self.txt_name.clear()
                self.spin_received.setValue(1.0)
                self.spin_unit_price.setValue(0.0)
                self.calculate_live_previews()
            else:
                ScanService.mark_event_rejected(event_id, f"Desktop could not post the inward entry: {msg}")
                self.show_banner(f"Failed to auto-receive scan: {msg}", is_error=True)
        else:
            # Stays 'pending' until the user posts it (see record_inward_entry)
            self._pending_phone_event_id = event_id
            self._pending_phone_code = mat_code
            self.show_banner(f"📱 Received scan from {dev_name}: '{mat_name}' ({mat_code}) x {rec_qty} {uom}. Click 'Receive Stock into Plant' to post.")
            self.btn_receive.setFocus()

    # ========================================================
    # Scanner & Inward Entry Logic
    # ========================================================
    def on_qr_scanned(self):
        raw_text = self.txt_qr_scan.text().strip()
        if not raw_text:
            return

        name, code, uom = self.parse_qr_text(raw_text)
        if not code:
            self.show_banner("Could not extract Material Code from QR scan.", is_error=True)
            return

        self.txt_code.setText(code)
        if name:
            self.txt_name.setText(name)
        if uom:
            self.txt_uom.setText(uom)

        # Fetch snapshot
        self.load_snapshot_for_code(code)
        self.txt_qr_scan.clear()
        self.spin_received.setFocus()
        self.spin_received.selectAll()

    def parse_qr_text(self, text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        name, code, uom = None, None, None
        lines = text.strip().splitlines()
        for line in lines:
            line_str = line.strip()
            if line_str.lower().startswith("material name:"):
                name = line_str.split(":", 1)[1].strip()
            elif line_str.lower().startswith("material code:"):
                code = line_str.split(":", 1)[1].strip()
            elif line_str.lower().startswith("uom:") or line_str.lower().startswith("unit:"):
                uom = line_str.split(":", 1)[1].strip()

        if not code and len(lines) == 1:
            code = lines[0].strip()

        return name, code, uom

    def on_code_changed(self, text: str):
        clean_code = text.strip()
        if clean_code:
            self.load_snapshot_for_code(clean_code)

    def load_snapshot_for_code(self, code: str):
        snapshot = PurchasedMaterialService.get_material_stock_snapshot(code)
        if snapshot.get("material_id"):
            if not self.txt_name.text().strip():
                self.txt_name.setText(snapshot["material_name"])
            self.txt_uom.setText(snapshot["uom"])
            if snapshot["unit_price"] > 0 and self.spin_unit_price.value() == 0.0:
                self.spin_unit_price.setValue(snapshot["unit_price"])
        self.calculate_live_previews()

    def calculate_live_previews(self):
        rec = self.spin_received.value()
        up = self.spin_unit_price.value()
        gst_p = self.spin_gst.value()

        subtotal = rec * up
        gst_amount = subtotal * (gst_p / 100.0)
        tot = subtotal + gst_amount
        currency = SettingsService.get_setting("currency_symbol", "₹")
        self.lbl_total_val.setText(f"{currency} {tot:,.2f}")

    def record_inward_entry(self):
        code = self.txt_code.text().strip()
        name = self.txt_name.text().strip()
        uom = self.txt_uom.text().strip() or "PCS"
        rec_qty = self.spin_received.value()
        unit_price = self.spin_unit_price.value()
        gst_percent = self.spin_gst.value()

        if not code:
            self.show_banner("Material Code is required.", is_error=True)
            self.txt_code.setFocus()
            return
        if not name:
            self.show_banner("Material Name is required.", is_error=True)
            self.txt_name.setFocus()
            return
        if rec_qty <= 0:
            self.show_banner("Received Qty must be greater than zero.", is_error=True)
            self.spin_received.setFocus()
            return

        data = {
            "material_code": code,
            "material_name": name,
            "uom": uom,
            "received_qty": rec_qty,
            "unit_price": unit_price,
            "gst_percent": gst_percent,
            "supplier": "",
            "challan_no": "",
            "remarks": "Plant Inward Entry"
        }

        ok, msg, rec_id = PurchasedMaterialService.record_inward_purchase(data)
        if ok:
            # If this entry came from a phone scan, confirm that scan as really applied
            if self._pending_phone_event_id and code.strip().upper() == self._pending_phone_code.strip().upper():
                ScanService.mark_event_applied(self._pending_phone_event_id)
                self._pending_phone_event_id = ""
                self._pending_phone_code = ""
            self.show_banner(f"✔ Received {rec_qty} {uom} for '{name}' ({code}). Stock updated successfully!")
            self.stock_updated.emit()
            self.refresh_records()
            # Clear inputs for next scan
            self.txt_code.clear()
            self.txt_name.clear()
            self.spin_received.setValue(1.0)
            self.spin_unit_price.setValue(0.0)
            self.spin_gst.setValue(18.0)
            self.calculate_live_previews()
            self.txt_qr_scan.setFocus()
        else:
            self.show_banner(msg, is_error=True)

    def delete_record(self, record_id: int):
        reply = QMessageBox.question(
            self,
            "Confirm Reversal",
            "Are you sure you want to revert this inward purchase entry?\n\n"
            "This will reverse the added physical stock and log a reversal entry in the stock ledger.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ok, msg = PurchasedMaterialService.delete_record(record_id)
            if ok:
                self.show_banner(f"✔ {msg}")
                self.stock_updated.emit()
                self.refresh_records()
            else:
                self.show_banner(msg, is_error=True)

    # ========================================================
    # Table Rendering & KPIs
    # ========================================================
    def refresh_records(self):
        query = self.txt_search.text().strip()
        self.records = PurchasedMaterialService.get_all_records(query)
        self.render_table()

    def render_table(self):
        min_rows = 20
        num_records = len(self.records)
        total_rows = max(min_rows, num_records)
        self.table.setRowCount(total_rows)

        total_qty = 0.0
        total_val = 0.0
        currency = SettingsService.get_setting("currency_symbol", "₹")

        for r_idx in range(total_rows):
            if r_idx < num_records:
                rec = self.records[r_idx]
                s_no = r_idx + 1
                code = rec["material_code"]
                name = rec["material_name"]
                uom = rec["uom"]
                rec_qty = float(rec.get("received_qty", rec.get("received_stock", 0.0)))
                up = float(rec.get("unit_price", 0.0))
                gst_p = float(rec.get("gst_percent", 18.0))
                tot = float(rec.get("total_price", 0.0))

                total_qty += rec_qty
                total_val += tot

                # 0. S no
                item_sno = QTableWidgetItem(str(s_no))
                item_sno.setTextAlignment(Qt.AlignCenter)
                item_sno.setFlags(item_sno.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 0, item_sno)

                # 1. material code
                item_c = QTableWidgetItem(code)
                item_c.setTextAlignment(Qt.AlignCenter)
                item_c.setFlags(item_c.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 1, item_c)

                # 2. material name
                dev_name = rec.get("device_name", "")
                if dev_name:
                    item_n = QTableWidgetItem(f"📱 {name}")
                    item_n.setToolTip(f"Scanned from phone: {dev_name}")
                else:
                    item_n = QTableWidgetItem(name)
                item_n.setFlags(item_n.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 2, item_n)

                # 3. uom
                item_u = QTableWidgetItem(uom)
                item_u.setTextAlignment(Qt.AlignCenter)
                item_u.setFlags(item_u.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 3, item_u)

                # 4. recived Qty
                item_rec = QTableWidgetItem(f"{rec_qty:.1f}")
                item_rec.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item_rec.setForeground(QColor("#15803d"))
                item_rec.setFont(QFont("Arial", 9, QFont.Bold))
                item_rec.setFlags(item_rec.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 4, item_rec)

                # 5. unit price
                item_up = QTableWidgetItem(f"{currency} {up:.2f}")
                item_up.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item_up.setFlags(item_up.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 5, item_up)

                # 6. GST
                item_gst = QTableWidgetItem(f"{gst_p:.0f}%")
                item_gst.setTextAlignment(Qt.AlignCenter)
                item_gst.setFlags(item_gst.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 6, item_gst)

                # 7. Total price
                item_tot = QTableWidgetItem(f"{currency} {tot:,.2f}")
                item_tot.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item_tot.setFont(QFont("Arial", 9, QFont.Bold))
                item_tot.setForeground(QColor("#0f172a"))
                item_tot.setFlags(item_tot.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r_idx, 7, item_tot)

                # 8. Action (Delete)
                btn_del = QPushButton("✖")
                btn_del.setToolTip("Revert this inward receipt")
                btn_del.setStyleSheet("QPushButton { color: #dc2626; font-weight: bold; border: none; background: transparent; } QPushButton:hover { color: #991b1b; }")
                btn_del.clicked.connect(lambda _, rec_id=rec["id"]: self.delete_record(rec_id))
                self.table.setCellWidget(r_idx, 8, btn_del)
            else:
                for c in range(9):
                    blank_item = QTableWidgetItem("")
                    blank_item.setFlags(Qt.NoItemFlags)
                    self.table.setItem(r_idx, c, blank_item)
                self.table.removeCellWidget(r_idx, 8)

        # Update KPI Badges
        self.lbl_kpi_count.setText(f"Receipts: {len(self.records)}")
        self.lbl_kpi_qty.setText(f"Total Qty: {total_qty:,.1f}")
        self.lbl_kpi_val.setText(f"Total Value: {currency} {total_val:,.2f}")

    # ========================================================
    # Exports
    # ========================================================
    def export_excel(self):
        if not self.records:
            self.show_banner("No records available to export.", is_error=True)
            return

        default_name = f"Purchased_Materials_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Purchased Materials to Excel", str(DATA_DIR / default_name), "Excel Workbooks (*.xlsx);;All Files (*)"
        )
        if path:
            ok = PurchasedMaterialService.export_excel(self.records, path)
            if ok:
                self.show_banner(f"✔ Exported {len(self.records)} records to Excel: {Path(path).name}")
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    QMessageBox.information(self, "Export Successful", f"Excel exported successfully:\n\n{path}")
            else:
                self.show_banner("Failed to export Excel.", is_error=True)

    def export_pdf(self):
        if not self.records:
            self.show_banner("No records available to export.", is_error=True)
            return

        default_name = f"Purchased_Materials_{time.strftime('%Y%m%d_%H%M%S')}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Purchased Materials to PDF", str(DATA_DIR / default_name), "PDF Documents (*.pdf);;All Files (*)"
        )
        if path:
            ok = PurchasedMaterialService.export_pdf(self.records, path)
            if ok:
                self.show_banner(f"✔ Exported {len(self.records)} records to PDF: {Path(path).name}")
                if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                    QMessageBox.information(self, "Export Successful", f"PDF exported successfully:\n\n{path}")
            else:
                self.show_banner("Failed to export PDF.", is_error=True)

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

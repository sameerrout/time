import os
from pathlib import Path
from typing import Optional, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QComboBox, QSpinBox, QFileDialog, QMessageBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, QSizeF
from PySide6.QtGui import QPixmap, QImage, QPainter, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from app.services.barcode_service import BarcodeService
from app.core.config import DATA_DIR
from app.core.logger import get_logger

logger = get_logger("IssueSlipApp.StickerPrintDialog")


class StickerPrintDialog(QDialog):
    def __init__(self, items: List[dict], parent=None):
        super().__init__(parent)
        self.items = items if items else []
        self.current_label_img = None
        self.init_ui()
        self.update_preview()

    def init_ui(self):
        self.setWindowTitle("Sticker Printer Ready — Thermal Label Printing")
        self.resize(760, 520)
        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; }
            QLabel { color: #0f172a; }
            QFrame.card {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            QPushButton.btn-primary {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton.btn-primary:hover { background-color: #1d4ed8; }
            QPushButton.btn-success {
                background-color: #16a34a;
                color: #ffffff;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton.btn-success:hover { background-color: #15803d; }
            QPushButton.btn-secondary {
                background-color: #ffffff;
                color: #334155;
                font-weight: 600;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton.btn-secondary:hover { background-color: #f1f5f9; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header_box = QVBoxLayout()
        header_box.setSpacing(2)
        lbl_title = QLabel("🖨️ Sticker Printer Studio", self)
        lbl_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #0f172a;")
        lbl_sub = QLabel(
            f"Ready for Thermal Sticker Printers (TSC, Zebra, TVS, Godrej, Citizen) • {len(self.items)} item(s) selected",
            self
        )
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748b;")
        header_box.addWidget(lbl_title)
        header_box.addWidget(lbl_sub)
        layout.addLayout(header_box)

        # Body: Left (Preview), Right (Printer Settings)
        body = QHBoxLayout()
        body.setSpacing(18)

        # Left Card: Live Preview
        left_card = QFrame(self)
        left_card.setProperty("class", "card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(10)

        lbl_pv_title = QLabel("Live Thermal Sticker Preview", left_card)
        lbl_pv_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0f172a;")
        left_layout.addWidget(lbl_pv_title)

        self.preview_frame = QFrame(left_card)
        self.preview_frame.setStyleSheet("background-color: #f1f5f9; border: 2px dashed #cbd5e1; border-radius: 8px;")
        pv_vbox = QVBoxLayout(self.preview_frame)
        pv_vbox.setAlignment(Qt.AlignCenter)

        self.lbl_preview = QLabel(self.preview_frame)
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setMinimumSize(360, 200)
        pv_vbox.addWidget(self.lbl_preview)
        left_layout.addWidget(self.preview_frame, 1)

        body.addWidget(left_card, 1)

        # Right Card: Settings & Actions
        right_card = QFrame(self)
        right_card.setProperty("class", "card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(12)

        lbl_set_title = QLabel("Sticker Configuration", right_card)
        lbl_set_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0f172a;")
        right_layout.addWidget(lbl_set_title)

        # Selected items summary
        if len(self.items) == 1:
            it = self.items[0]
            summary_txt = f"<b>Code:</b> {it.get('material_code', '')}<br><b>Name:</b> {it.get('material_name', '')}<br><b>UOM:</b> {it.get('uom', '')}"
        else:
            first_codes = ", ".join([x.get("material_code", "") for x in self.items[:3]])
            if len(self.items) > 3:
                first_codes += f" ... (+{len(self.items)-3} more)"
            summary_txt = f"<b>Batch Print:</b> {len(self.items)} stickers selected<br><span style='color:#64748b;'>{first_codes}</span>"

        lbl_info = QLabel(summary_txt, right_card)
        lbl_info.setStyleSheet("font-size: 12px; color: #334155; line-height: 140%;")
        lbl_info.setWordWrap(True)
        right_layout.addWidget(lbl_info)

        # Label Size Selector
        lbl_size = QLabel("Sticker Label Size:", right_card)
        lbl_size.setStyleSheet("font-size: 12px; font-weight: 600; margin-top: 6px;")
        right_layout.addWidget(lbl_size)

        self.cmb_size = QComboBox(right_card)
        self.cmb_size.setFixedHeight(36)
        self.cmb_size.addItems([
            "50 mm x 25 mm (2\" x 1\" - Standard Thermal Sticker)",
            "50 mm x 50 mm (2\" x 2\" - Square Thermal Label)",
            "75 mm x 50 mm (3\" x 2\" - Box / Bin Sticker)",
            "100 mm x 50 mm (4\" x 2\" - Pallet / Warehouse Sticker)",
            "A4 Sticker Sheet (24 Labels per Page, 3x8 Grid)"
        ])
        self.cmb_size.currentIndexChanged.connect(self.update_preview)
        right_layout.addWidget(self.cmb_size)

        # Copies Selector
        lbl_cp = QLabel("Copies per Sticker:", right_card)
        lbl_cp.setStyleSheet("font-size: 12px; font-weight: 600; margin-top: 4px;")
        right_layout.addWidget(lbl_cp)

        self.spin_copies = QSpinBox(right_card)
        self.spin_copies.setRange(1, 999)
        self.spin_copies.setValue(1)
        self.spin_copies.setFixedHeight(36)
        right_layout.addWidget(self.spin_copies)

        right_layout.addStretch()

        # Primary Print Button (Direct to thermal sticker printer)
        self.btn_print_direct = QPushButton("🖨️ Print to Sticker Printer", right_card)
        self.btn_print_direct.setProperty("class", "btn-primary")
        self.btn_print_direct.setFixedHeight(40)
        self.btn_print_direct.clicked.connect(self.print_direct)
        right_layout.addWidget(self.btn_print_direct)

        # Secondary Actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_export_pdf = QPushButton("📄 Export PDF", right_card)
        self.btn_export_pdf.setProperty("class", "btn-secondary")
        self.btn_export_pdf.setFixedHeight(36)
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        btn_row.addWidget(self.btn_export_pdf)

        self.btn_save_png = QPushButton("💾 Save PNG", right_card)
        self.btn_save_png.setProperty("class", "btn-secondary")
        self.btn_save_png.setFixedHeight(36)
        self.btn_save_png.clicked.connect(self.save_png)
        btn_row.addWidget(self.btn_save_png)

        right_layout.addLayout(btn_row)

        body.addWidget(right_card)
        layout.addLayout(body, 1)

        # Bottom Bar: Close
        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        btn_close = QPushButton("Close", self)
        btn_close.setProperty("class", "btn-secondary")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)
        layout.addLayout(bottom_bar)

    def get_selected_size_code(self) -> str:
        idx = self.cmb_size.currentIndex()
        mapping = {
            0: "50x25",
            1: "50x50",
            2: "75x50",
            3: "100x50",
            4: "a4_sheet"
        }
        return mapping.get(idx, "50x25")

    def update_preview(self):
        if not self.items:
            self.lbl_preview.setText("No item selected for preview.")
            return

        size_code = self.get_selected_size_code()
        sample_item = self.items[0]
        code = sample_item.get("material_code", "")
        name = sample_item.get("material_name", "")
        uom = sample_item.get("uom", "EA")

        label_size_arg = "50x25" if size_code == "a4_sheet" else size_code
        img = BarcodeService.generate_thermal_sticker_image(
            material_code=code,
            material_name=name,
            uom=uom,
            label_size=label_size_arg
        )

        if img:
            self.current_label_img = img
            bytes_data = img.tobytes("raw", "RGBA")
            qimg = QImage(bytes_data, img.size[0], img.size[1], QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(qimg)
            self.lbl_preview.setPixmap(pix.scaled(360, 210, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_preview.setText("Could not generate preview.")

    def print_direct(self):
        """Send labels directly to the selected Windows / Thermal Sticker Printer."""
        if not self.items:
            QMessageBox.warning(self, "No Items", "No items selected to print.")
            return

        printer = QPrinter(QPrinter.HighResolution)
        size_code = self.get_selected_size_code()

        # Set page size corresponding to thermal sticker
        dims = {
            "50x25": (50, 25),
            "50x50": (50, 50),
            "75x50": (75, 50),
            "100x50": (100, 50),
        }
        if size_code in dims:
            pw, ph = dims[size_code]
            printer.setPageSize(QPageSize(QSizeF(pw, ph), QPageSize.Millimeter))
        else:
            printer.setPageSize(QPageSize(QPageSize.A4))

        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            dialog = QPrintDialog(printer, self)
            dialog.setWindowTitle("Select Sticker Printer")
            if dialog.exec() != QPrintDialog.Accepted:
                return

        copies = self.spin_copies.value()
        try:
            painter = QPainter(printer)
            first_page = True

            for item in self.items:
                code = item.get("material_code", "")
                name = item.get("material_name", "")
                uom = item.get("uom", "EA")

                lbl_size_arg = "50x25" if size_code == "a4_sheet" else size_code
                pil_img = BarcodeService.generate_thermal_sticker_image(code, name, uom=uom, label_size=lbl_size_arg)
                if not pil_img:
                    continue

                bytes_data = pil_img.tobytes("raw", "RGBA")
                qimg = QImage(bytes_data, pil_img.size[0], pil_img.size[1], QImage.Format_RGBA8888)
                pix = QPixmap.fromImage(qimg)

                for _ in range(copies):
                    if not first_page:
                        printer.newPage()
                    first_page = False

                    rect = printer.pageRect(QPrinter.DevicePixel)
                    painter.drawPixmap(rect.toRect(), pix)

            painter.end()
            QMessageBox.information(
                self,
                "Printing Sent",
                f"Successfully sent {len(self.items) * copies} sticker(s) to the printer!"
            )
        except Exception as exc:
            logger.error(f"Error printing stickers: {exc}")
            QMessageBox.critical(self, "Print Error", f"Failed to print stickers: {exc}")

    def export_pdf(self):
        """Export printable PDF formatted for thermal printer or A4 sheets."""
        if not self.items:
            return

        size_code = self.get_selected_size_code()
        sample_code = self.items[0].get("material_code", "catalog")
        default_name = f"stickers_{sample_code}_{size_code}.pdf"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Printable Sticker PDF",
            str(DATA_DIR / default_name),
            "PDF Documents (*.pdf);;All Files (*)"
        )
        if path:
            copies = self.spin_copies.value()
            ok = BarcodeService.export_sticker_printer_pdf(
                path,
                self.items,
                label_size=size_code,
                copies_per_item=copies
            )
            if ok:
                QMessageBox.information(
                    self,
                    "PDF Export Successful",
                    f"Printable sticker PDF exported successfully to:\n\n{path}\n\nReady for sticker printer printing."
                )
            else:
                QMessageBox.critical(self, "Export Failed", "Could not export sticker PDF.")

    def save_png(self):
        """Save the rendered sticker image to PNG."""
        if not self.current_label_img or not self.items:
            return

        code = self.items[0].get("material_code", "label")
        size_code = self.get_selected_size_code()
        default_name = f"sticker_{code}_{size_code}.png"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Sticker PNG Image",
            str(DATA_DIR / default_name),
            "PNG Images (*.png);;All Files (*)"
        )
        if path:
            try:
                self.current_label_img.save(path, format="PNG")
                QMessageBox.information(self, "Saved Successfully", f"Sticker image saved to:\n\n{path}")
            except Exception as exc:
                QMessageBox.critical(self, "Save Error", f"Could not save sticker image: {exc}")

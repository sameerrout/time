import os
from pathlib import Path
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QSpinBox,
    QFileDialog, QMessageBox, QSizePolicy, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QStyledItemDelegate, QStyle
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage, QFont, QPainter

from app.services.barcode_service import BarcodeService
from app.ui.dialogs.sticker_print_dialog import StickerPrintDialog
from app.core.config import DATA_DIR
from app.core.logger import get_logger

logger = get_logger("IssueSlipApp.QRCodeGeneratorView")


class QRCodeDelegate(QStyledItemDelegate):
    """High-performance delegate to render crisp QR codes on-demand during vertical scrolling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap_cache = {}

    def paint(self, painter: QPainter, option, index):
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        code = index.data(Qt.UserRole)
        if code:
            if code not in self.pixmap_cache:
                qr_img = BarcodeService.generate_pure_qr_image(code, box_size=3, border=1)
                if qr_img:
                    bytes_data = qr_img.tobytes("raw", "RGBA")
                    qimg = QImage(bytes_data, qr_img.size[0], qr_img.size[1], QImage.Format_RGBA8888)
                    self.pixmap_cache[code] = QPixmap.fromImage(qimg)
                else:
                    self.pixmap_cache[code] = None

            pix = self.pixmap_cache.get(code)
            if pix:
                target_w, target_h = 54, 54
                x = option.rect.x() + (option.rect.width() - target_w) // 2
                y = option.rect.y() + (option.rect.height() - target_h) // 2
                painter.drawPixmap(x, y, target_w, target_h, pix)

        painter.restore()


class BarcodeGeneratorView(QWidget):
    qr_generated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.materials_cache: list[dict] = []
        self.current_preview_image = None
        self.active_code = ""
        self.active_name = ""
        self.active_uom = ""

        # Catalog State (all items shown via vertical scrolling)
        self.all_catalog_items: list[dict] = []
        self.filtered_catalog_items: list[dict] = []

        self.init_ui()
        self.load_materials()
        self.load_catalog_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 20, 30, 20)
        main_layout.setSpacing(14)

        # 1. Header with Title on Left, and Control Panel on the RIGHT (in the red-circled spot)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)

        # Left: Title and description
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.lbl_title = QLabel("QR Code Generator & Label Studio", self)
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0f172a;")
        self.lbl_sub = QLabel("Enter Material Name and Material Code, then generate and export QR code labels.", self)
        self.lbl_sub.setStyleSheet("font-size: 13px; color: #64748b;")
        title_box.addWidget(self.lbl_title)
        title_box.addWidget(self.lbl_sub)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # RIGHT SPOT (EXACT SPOT CIRCLED IN USER'S SCREENSHOT):
        # Action Toolbar featuring Catalog, Sticker Printer, and Excel Export
        self.header_toolbar = QFrame(self)
        self.header_toolbar.setStyleSheet("""
            QFrame {
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }
        """)
        toolbar_layout = QHBoxLayout(self.header_toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setSpacing(8)

        # Button 1: Mode Switcher / Catalog Viewer
        self.btn_toggle_mode = QPushButton("📋 Plant QR Catalog (1,734 Items)", self.header_toolbar)
        self.btn_toggle_mode.setStyleSheet("""
            QPushButton {
                background-color: #1e3a8a;
                color: #ffffff;
                font-size: 13px;
                font-weight: 600;
                padding: 6px 14px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_toggle_mode.setFixedHeight(34)
        self.btn_toggle_mode.clicked.connect(self.toggle_view_mode)
        toolbar_layout.addWidget(self.btn_toggle_mode)

        # Button 2: Sticker Printer Ready
        self.btn_header_sticker = QPushButton("🖨️ Sticker Printer", self.header_toolbar)
        self.btn_header_sticker.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #ffffff;
                font-size: 13px;
                font-weight: 600;
                padding: 6px 12px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #047857;
            }
        """)
        self.btn_header_sticker.setFixedHeight(34)
        self.btn_header_sticker.clicked.connect(self.open_sticker_printer_dialog)
        toolbar_layout.addWidget(self.btn_header_sticker)

        # Button 3: Export Excel with QR
        self.btn_header_excel = QPushButton("📊 Export Excel", self.header_toolbar)
        self.btn_header_excel.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                font-size: 13px;
                font-weight: 600;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid #94a3b8;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
            }
        """)
        self.btn_header_excel.setFixedHeight(34)
        self.btn_header_excel.clicked.connect(self.export_catalog_excel)
        toolbar_layout.addWidget(self.btn_header_excel)

        header_layout.addWidget(self.header_toolbar)
        main_layout.addLayout(header_layout)

        # Validation Banner
        self.banner = QFrame(self)
        self.banner.setVisible(False)
        self.banner.setStyleSheet("background-color: #fee2e2; border: 1px solid #fca5a5; border-radius: 8px;")
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(14, 8, 14, 8)
        self.lbl_banner = QLabel("", self.banner)
        self.lbl_banner.setStyleSheet("color: #b91c1c; font-size: 13px; font-weight: 600;")
        banner_layout.addWidget(self.lbl_banner)
        main_layout.addWidget(self.banner)

        # Stacked Widget for:
        # Index 0: Single QR Code Studio
        # Index 1: Full Plant QR Catalog & Sticker Printing Table (matching Excel reference)
        self.stacked_widget = QStackedWidget(self)
        main_layout.addWidget(self.stacked_widget, 1)

        # Build Page 0: Single Studio
        self.page_single = self.build_single_studio_page()
        self.stacked_widget.addWidget(self.page_single)

        # Build Page 1: Plant QR Catalog Table
        self.page_catalog = self.build_catalog_page()
        self.stacked_widget.addWidget(self.page_catalog)

    def build_single_studio_page(self) -> QWidget:
        container = QWidget()
        body_layout = QHBoxLayout(container)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(24)

        # Left Column: Configuration Form
        left_card = QFrame(container)
        left_card.setProperty("class", "card")
        left_card.setMinimumWidth(380)
        form_layout = QVBoxLayout(left_card)
        form_layout.setContentsMargins(22, 22, 22, 22)
        form_layout.setSpacing(14)

        lbl_form_title = QLabel("QR Code Details", left_card)
        lbl_form_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 2px;")
        form_layout.addWidget(lbl_form_title)

        # 1. Clear label outside input: "Material Name"
        lbl_name = QLabel("Material Name", left_card)
        lbl_name.setStyleSheet("font-size: 13px; font-weight: 600; color: #0f172a;")
        form_layout.addWidget(lbl_name)

        self.txt_mat_name = QLineEdit(left_card)
        self.txt_mat_name.setText("")
        self.txt_mat_name.setPlaceholderText("")
        self.txt_mat_name.setFixedHeight(38)
        form_layout.addWidget(self.txt_mat_name)

        # 2. Clear label outside input: "Material Code"
        lbl_code = QLabel("Material Code", left_card)
        lbl_code.setStyleSheet("font-size: 13px; font-weight: 600; color: #0f172a;")
        form_layout.addWidget(lbl_code)

        self.txt_mat_code = QLineEdit(left_card)
        self.txt_mat_code.setText("")
        self.txt_mat_code.setPlaceholderText("")
        self.txt_mat_code.setFixedHeight(38)
        form_layout.addWidget(self.txt_mat_code)

        # 3. Clear label outside input: "UOM"
        lbl_uom = QLabel("UOM", left_card)
        lbl_uom.setStyleSheet("font-size: 13px; font-weight: 600; color: #0f172a;")
        form_layout.addWidget(lbl_uom)

        self.txt_uom = QLineEdit(left_card)
        self.txt_uom.setText("")
        self.txt_uom.setPlaceholderText("")
        self.txt_uom.setFixedHeight(38)
        form_layout.addWidget(self.txt_uom)

        # Primary Action Button: Generate QR Code
        self.btn_generate_qr = QPushButton("Generate QR Code", left_card)
        self.btn_generate_qr.setProperty("class", "btn-primary")
        self.btn_generate_qr.setFixedHeight(40)
        self.btn_generate_qr.clicked.connect(self.generate_qr_code)
        form_layout.addWidget(self.btn_generate_qr)

        form_layout.addStretch()
        body_layout.addWidget(left_card)

        # Right Column: Live Label Preview & Export Actions
        right_card = QFrame(container)
        right_card.setProperty("class", "card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(22, 22, 22, 22)
        right_layout.setSpacing(14)

        lbl_preview_title = QLabel("Live QR Label Preview", right_card)
        lbl_preview_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0f172a;")
        right_layout.addWidget(lbl_preview_title)

        # Preview Canvas Container
        self.preview_frame = QFrame(right_card)
        self.preview_frame.setStyleSheet("background-color: #f1f5f9; border: 2px dashed #cbd5e1; border-radius: 10px;")
        preview_vbox = QVBoxLayout(self.preview_frame)
        preview_vbox.setAlignment(Qt.AlignCenter)

        self.lbl_preview_image = QLabel(self.preview_frame)
        self.lbl_preview_image.setAlignment(Qt.AlignCenter)
        self.lbl_preview_image.setMinimumSize(480, 280)
        self.lbl_preview_image.setText("Enter Material Name, Material Code, and UOM on the left,\nthen click 'Generate QR Code'.")
        self.lbl_preview_image.setStyleSheet("color: #64748b; font-size: 13px; font-weight: 500; text-align: center;")
        preview_vbox.addWidget(self.lbl_preview_image)
        right_layout.addWidget(self.preview_frame, 1)

        # Action Buttons Row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(12)

        self.btn_save_png = QPushButton("💾 Save Image (PNG)", right_card)
        self.btn_save_png.setFixedHeight(38)
        self.btn_save_png.setEnabled(False)
        self.btn_save_png.clicked.connect(self.export_image)
        actions_row.addWidget(self.btn_save_png)

        lbl_copies = QLabel("Copies:", right_card)
        lbl_copies.setStyleSheet("font-size: 12px; font-weight: 600;")
        actions_row.addWidget(lbl_copies)

        self.spin_copies = QSpinBox(right_card)
        self.spin_copies.setRange(1, 48)
        self.spin_copies.setValue(12)
        self.spin_copies.setFixedHeight(38)
        actions_row.addWidget(self.spin_copies)

        self.btn_export_pdf = QPushButton("📄 Export Printable PDF", right_card)
        self.btn_export_pdf.setProperty("class", "btn-primary")
        self.btn_export_pdf.setFixedHeight(38)
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_pdf.clicked.connect(self.export_pdf_sheet)
        actions_row.addWidget(self.btn_export_pdf)

        right_layout.addLayout(actions_row)
        body_layout.addWidget(right_card, 1)
        return container

    def build_catalog_page(self) -> QWidget:
        """
        Builds the Full Plant QR Catalog & Sticker Printing Table matching the reference Excel image:
        Columns: S no | Material Code | Material Name | UOM | QR Code | Actions
        Displays all materials directly with vertical scrolling (no pagination footer).
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Top Bar: Search and Quick Actions
        top_bar = QFrame(container)
        top_bar.setProperty("class", "card")
        tb_layout = QHBoxLayout(top_bar)
        tb_layout.setContentsMargins(14, 10, 14, 10)
        tb_layout.setSpacing(12)

        # Search box
        self.txt_search = QLineEdit(top_bar)
        self.txt_search.setPlaceholderText("🔍 Search across 1,734 materials (Code, Name, or UOM)...")
        self.txt_search.setFixedHeight(36)
        self.txt_search.setMinimumWidth(340)
        self.txt_search.textChanged.connect(self.filter_catalog)
        tb_layout.addWidget(self.txt_search)

        self.lbl_catalog_status = QLabel("Showing 1,734 / 1,734 materials", top_bar)
        self.lbl_catalog_status.setStyleSheet("font-size: 13px; font-weight: 600; color: #475569;")
        tb_layout.addWidget(self.lbl_catalog_status)

        tb_layout.addStretch()

        # Batch Export Printable PDF
        btn_batch_pdf = QPushButton("📄 Export All Stickers PDF", top_bar)
        btn_batch_pdf.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: 600;
                padding: 7px 14px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        btn_batch_pdf.setFixedHeight(36)
        btn_batch_pdf.clicked.connect(self.export_catalog_pdf)
        tb_layout.addWidget(btn_batch_pdf)

        layout.addWidget(top_bar)

        # Main Table: S no | Material Code | Material Name | UOM | QR Code | Actions
        self.table_catalog = QTableWidget(container)
        self.table_catalog.setColumnCount(6)
        self.table_catalog.setHorizontalHeaderLabels([
            "S no", "Material Code", "Material Name", "UOM", "QR Code", "Actions"
        ])
        self.table_catalog.verticalHeader().setVisible(False)
        self.table_catalog.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_catalog.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_catalog.setShowGrid(True)
        self.table_catalog.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table_catalog.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table_catalog.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                gridline-color: #cbd5e1;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                font-size: 13px;
                selection-background-color: #e0e7ff;
                selection-color: #0f172a;
            }
            QHeaderView::section {
                background-color: #1B365D;
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                padding: 8px 10px;
                border: 1px solid #0f2444;
            }
        """)

        # Set QR Code Delegate on column 4
        self.table_catalog.setItemDelegateForColumn(4, QRCodeDelegate(self.table_catalog))

        # Column sizing
        header = self.table_catalog.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table_catalog.setColumnWidth(0, 65)

        header.setSectionResizeMode(1, QHeaderView.Interactive)
        self.table_catalog.setColumnWidth(1, 220)

        header.setSectionResizeMode(2, QHeaderView.Stretch)

        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table_catalog.setColumnWidth(3, 85)

        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table_catalog.setColumnWidth(4, 100)

        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table_catalog.setColumnWidth(5, 185)

        layout.addWidget(self.table_catalog, 1)
        return container

    def toggle_view_mode(self):
        """Switch smoothly between Single Studio and Plant QR Catalog Table."""
        curr_idx = self.stacked_widget.currentIndex()
        if curr_idx == 0:
            self.stacked_widget.setCurrentIndex(1)
            self.lbl_title.setText("Plant QR Code Catalog & Sticker Printing Studio")
            self.lbl_sub.setText("1,734 plant materials catalog • Ready for instant thermal sticker printing and Excel export.")
            self.btn_toggle_mode.setText("⚡ Back to Single Studio")
            self.btn_toggle_mode.setStyleSheet("""
                QPushButton {
                    background-color: #475569;
                    color: #ffffff;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 6px 14px;
                    border-radius: 6px;
                    border: none;
                }
                QPushButton:hover { background-color: #334155; }
            """)
        else:
            self.stacked_widget.setCurrentIndex(0)
            self.lbl_title.setText("QR Code Generator & Label Studio")
            self.lbl_sub.setText("Enter Material Name and Material Code, then generate and export QR code labels.")
            self.btn_toggle_mode.setText("📋 Plant QR Catalog (1,734 Items)")
            self.btn_toggle_mode.setStyleSheet("""
                QPushButton {
                    background-color: #1e3a8a;
                    color: #ffffff;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 6px 14px;
                    border-radius: 6px;
                    border: none;
                }
                QPushButton:hover { background-color: #1d4ed8; }
            """)

    def load_catalog_data(self):
        """Load all materials from the plant catalog JSON."""
        self.all_catalog_items = BarcodeService.get_plant_catalog()
        self.filtered_catalog_items = list(self.all_catalog_items)
        self.render_catalog_table()

    def filter_catalog(self, query: str):
        """Live search across Material Code, Material Name, and UOM."""
        q = query.strip().lower()
        if not q:
            self.filtered_catalog_items = list(self.all_catalog_items)
        else:
            self.filtered_catalog_items = [
                it for it in self.all_catalog_items
                if q in it.get("material_code", "").lower()
                or q in it.get("material_name", "").lower()
                or q in it.get("uom", "").lower()
            ]
        self.render_catalog_table()

    def render_catalog_table(self):
        """Populate all materials with S no (1, 2, 3...) into the table for vertical scrolling."""
        total = len(self.filtered_catalog_items)
        self.lbl_catalog_status.setText(f"Showing {total} / {len(self.all_catalog_items)} materials")

        self.table_catalog.setRowCount(total)

        for row_idx, item in enumerate(self.filtered_catalog_items):
            code = str(item.get("material_code", ""))
            name = str(item.get("material_name", ""))
            uom = str(item.get("uom", ""))

            self.table_catalog.setRowHeight(row_idx, 68)

            # Col 0: S no (1, 2, 3, 4, ...)
            it_sno = QTableWidgetItem(str(row_idx + 1))
            it_sno.setTextAlignment(Qt.AlignCenter)
            it_sno.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.table_catalog.setItem(row_idx, 0, it_sno)

            # Col 1: Material Code (Bold)
            it_code = QTableWidgetItem(code)
            it_code.setFont(QFont("Segoe UI", 10, QFont.Bold))
            it_code.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table_catalog.setItem(row_idx, 1, it_code)

            # Col 2: Material Name
            it_name = QTableWidgetItem(name)
            it_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table_catalog.setItem(row_idx, 2, it_name)

            # Col 3: UOM
            it_uom = QTableWidgetItem(uom)
            it_uom.setTextAlignment(Qt.AlignCenter)
            self.table_catalog.setItem(row_idx, 3, it_uom)

            # Col 4: QR Code (Drawn on-demand by QRCodeDelegate)
            it_qr = QTableWidgetItem()
            it_qr.setData(Qt.UserRole, code)
            it_qr.setTextAlignment(Qt.AlignCenter)
            self.table_catalog.setItem(row_idx, 4, it_qr)

            # Col 5: Actions
            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            btn_print = QPushButton("🖨️ Print Sticker", act_widget)
            btn_print.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 600;
                    border: none;
                    border-radius: 4px;
                    padding: 5px 8px;
                }
                QPushButton:hover { background-color: #047857; }
            """)
            btn_print.clicked.connect(lambda _, it=item: self.open_sticker_printer_dialog([it]))
            act_layout.addWidget(btn_print)

            btn_load = QPushButton("⚡ Studio", act_widget)
            btn_load.setStyleSheet("""
                QPushButton {
                    background-color: #f1f5f9;
                    color: #0f172a;
                    font-size: 11px;
                    font-weight: 600;
                    border: 1px solid #cbd5e1;
                    border-radius: 4px;
                    padding: 5px 8px;
                }
                QPushButton:hover { background-color: #e2e8f0; }
            """)
            btn_load.clicked.connect(lambda _, it=item: self.load_item_into_studio(it))
            act_layout.addWidget(btn_load)

            self.table_catalog.setCellWidget(row_idx, 5, act_widget)

    def load_item_into_studio(self, item: dict):
        """Populates single studio with chosen item and generates label preview."""
        self.txt_mat_code.setText(item.get("material_code", ""))
        self.txt_mat_name.setText(item.get("material_name", ""))
        self.txt_uom.setText(item.get("uom", ""))
        self.stacked_widget.setCurrentIndex(0)
        self.lbl_title.setText("QR Code Generator & Label Studio")
        self.lbl_sub.setText("Enter Material Name and Material Code, then generate and export QR code labels.")
        self.btn_toggle_mode.setText("📋 Plant QR Catalog (1,734 Items)")
        self.generate_qr_code()

    def get_selected_or_current_items(self) -> List[dict]:
        """Returns active item from single studio, or selected table row item, or all filtered items."""
        selected_rows = self.table_catalog.selectionModel().selectedRows() if hasattr(self, "table_catalog") and self.table_catalog.selectionModel() else []
        if selected_rows:
            items = []
            for m in selected_rows:
                r = m.row()
                if r < len(self.filtered_catalog_items):
                    items.append(self.filtered_catalog_items[r])
            if items:
                return items

        # If in single studio and active code is set
        if self.active_code:
            return [{
                "material_code": self.active_code,
                "material_name": self.active_name,
                "uom": self.active_uom
            }]

        if self.filtered_catalog_items:
            return [self.filtered_catalog_items[0]]
        return []

    def open_sticker_printer_dialog(self, items: Optional[List[dict]] = None):
        """Open the dedicated sticker printer dialog."""
        target_items = items if items is not None else self.get_selected_or_current_items()
        if not target_items:
            QMessageBox.information(
                self,
                "Select Material",
                "Please select a material or generate a QR code first."
            )
            return

        dialog = StickerPrintDialog(target_items, self)
        dialog.exec()

    def export_catalog_excel(self):
        """Export the full catalog with embedded QR images to Excel matching the reference image."""
        items_to_export = self.filtered_catalog_items if self.filtered_catalog_items else self.all_catalog_items

        default_name = "Plant_QR_Catalog_Full.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Plant QR Catalog to Excel",
            str(DATA_DIR / default_name),
            "Excel Workbooks (*.xlsx);;All Files (*)"
        )
        if path:
            ok = BarcodeService.export_catalog_to_excel(path, items_to_export)
            if ok:
                QMessageBox.information(
                    self,
                    "Excel Export Successful",
                    f"Successfully exported {len(items_to_export)} materials with embedded QR codes to:\n\n{path}\n\nReady for opening in Excel or printing sticker labels."
                )
            else:
                QMessageBox.critical(self, "Export Failed", "Could not export catalog to Excel.")

    def export_catalog_pdf(self):
        """Export printable PDF sticker sheets for all or selected materials."""
        items = self.filtered_catalog_items if self.filtered_catalog_items else self.all_catalog_items
        if not items:
            return

        dialog = StickerPrintDialog(items, self)
        dialog.export_pdf()

    def load_materials(self):
        """
        Reset form inputs to empty strings on open/switch.
        Ensure no material is preselected and no sample data is loaded.
        """
        self.txt_mat_name.setText("")
        self.txt_mat_code.setText("")
        self.txt_uom.setText("")
        self.current_preview_image = None
        self.active_code = ""
        self.active_name = ""
        self.active_uom = ""
        if hasattr(self, "lbl_preview_image"):
            self.lbl_preview_image.clear()
            self.lbl_preview_image.setText("Enter Material Name, Material Code, and UOM on the left,\nthen click 'Generate QR Code'.")
        if hasattr(self, "btn_save_png"):
            self.btn_save_png.setEnabled(False)
            self.btn_export_pdf.setEnabled(False)
        if hasattr(self, "banner"):
            self.banner.setVisible(False)

    def show_validation_message(self, message: str):
        self.lbl_banner.setText(f"⚠ {message}")
        self.banner.setVisible(True)
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            QMessageBox.warning(self, "Validation Error", message)

    def generate_qr_code(self):
        """
        Validate inputs and generate the QR code encoding material fields.
        """
        name = self.txt_mat_name.text().strip()
        code = self.txt_mat_code.text().strip()
        uom = self.txt_uom.text().strip()

        # Validation checks
        if not name and not code:
            self.show_validation_message("Please enter both Material Name and Material Code.")
            self.txt_mat_name.setFocus()
            return

        if not name:
            self.show_validation_message("Material Name is required. Please enter a Material Name.")
            self.txt_mat_name.setFocus()
            return

        if not code:
            self.show_validation_message("Material Code is required. Please enter a Material Code.")
            self.txt_mat_code.setFocus()
            return

        self.banner.setVisible(False)

        # Generate QR label preview card
        img = BarcodeService.generate_qr_label_preview(material_name=name, material_code=code, uom=uom)
        if img:
            self.current_preview_image = img
            self.active_name = name
            self.active_code = code
            self.active_uom = uom

            bytes_data = img.tobytes("raw", "RGBA")
            qimg = QImage(bytes_data, img.size[0], img.size[1], QImage.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimg)
            self.lbl_preview_image.setPixmap(pixmap.scaled(480, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            self.btn_save_png.setEnabled(True)
            self.btn_export_pdf.setEnabled(True)
            self.qr_generated.emit()
        else:
            self.show_validation_message("Failed to generate QR code.")

    def export_image(self):
        if not self.active_code or not self.active_name:
            self.show_validation_message("Please generate a QR code first.")
            return

        default_filename = f"qr_{self.active_code}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save QR Code Label Image", str(DATA_DIR / default_filename), "PNG Images (*.png);;All Files (*)"
        )
        if path:
            ok = BarcodeService.save_qr_label_as_image(path, self.active_name, self.active_code, uom=self.active_uom)
            if ok:
                QMessageBox.information(self, "Export Successful", f"QR Code label saved successfully to:\n\n{path}")
            else:
                QMessageBox.critical(self, "Export Failed", "Could not save QR label image.")

    def export_pdf_sheet(self):
        if not self.active_code or not self.active_name:
            self.show_validation_message("Please generate a QR code first.")
            return

        default_filename = f"qr_labels_{self.active_code}_sheet.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Printable QR PDF Sheet", str(DATA_DIR / default_filename), "PDF Documents (*.pdf);;All Files (*)"
        )
        if path:
            copies = self.spin_copies.value()
            ok = BarcodeService.export_pdf_qr_sheet(path, self.active_name, self.active_code, copies=copies, uom=self.active_uom)
            if ok:
                QMessageBox.information(
                    self,
                    "PDF Export Successful",
                    f"Printable PDF sheet with {copies} QR labels exported to:\n\n{path}\n\nReady for A4 sticker sheet printing."
                )
            else:
                QMessageBox.critical(self, "PDF Export Failed", "Could not export PDF label sheet.")

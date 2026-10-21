from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialog, QFormLayout, QComboBox, QDoubleSpinBox,
    QMessageBox, QFileDialog, QAbstractItemView, QSplitter
)
from PySide6.QtCore import Qt, Signal

from app.services.material_service import MaterialService
from app.services.settings_service import SettingsService
from app.core.config import DATA_DIR
from app.core.logger import get_logger

logger = get_logger("IssueSlipApp.StockDatabaseView")


class MaterialEditDialog(QDialog):
    """Dialog to create or edit material records."""
    def __init__(self, material=None, parent=None):
        super().__init__(parent)
        self.material = material
        self.setWindowTitle("Edit Material" if material else "Add New Warehouse Material")
        self.setMinimumWidth(420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.txt_code = QLineEdit(self)
        self.txt_code.setPlaceholderText("e.g. MAT-201")
        if self.material:
            self.txt_code.setText(self.material["material_code"])
            self.txt_code.setReadOnly(True)
            self.txt_code.setStyleSheet("background-color: #f1f5f9; color: #64748b;")
        form.addRow("Material Code *:", self.txt_code)

        self.txt_name = QLineEdit(self)
        self.txt_name.setPlaceholderText("e.g. Ball Bearing 6205-2RS")
        if self.material:
            self.txt_name.setText(self.material["name"])
        form.addRow("Material Name *:", self.txt_name)

        self.txt_category = QLineEdit(self)
        self.txt_category.setPlaceholderText("e.g. Spare Parts, Safety PPE, Hardware")
        self.txt_category.setText(self.material["category"] if self.material else "General")
        form.addRow("Category:", self.txt_category)

        self.combo_unit = QComboBox(self)
        self.combo_unit.addItems(["PCS", "KG", "MTR", "LITRE", "BOX", "PAIR", "SET", "ROLL"])
        if self.material:
            self.combo_unit.setCurrentText(self.material["unit"])
        form.addRow("Unit of Measure:", self.combo_unit)

        self.txt_barcode = QLineEdit(self)
        self.txt_barcode.setPlaceholderText("e.g. BAR-201")
        if self.material:
            self.txt_barcode.setText(self.material["barcode"])
        form.addRow("Barcode *:", self.txt_barcode)

        self.spin_opening = QDoubleSpinBox(self)
        self.spin_opening.setRange(0, 9999999.0)
        self.spin_opening.setDecimals(1)
        self.spin_opening.setValue(float(self.material.get("opening_stock", 0.0)) if self.material else 0.0)
        form.addRow("Opening Stock:", self.spin_opening)

        currency = SettingsService.get_setting("currency_symbol", "₹")
        self.spin_unit_price = QDoubleSpinBox(self)
        self.spin_unit_price.setRange(0, 9999999.99)
        self.spin_unit_price.setDecimals(2)
        self.spin_unit_price.setPrefix(f"{currency} ")
        self.spin_unit_price.setValue(float(self.material.get("unit_price", 0.0)) if self.material else 0.0)
        form.addRow("Unit Price:", self.spin_unit_price)

        self.spin_min = QDoubleSpinBox(self)
        self.spin_min.setRange(0, 999999)
        self.spin_min.setValue(self.material["min_stock"] if self.material else 5.0)
        form.addRow("Minimum Alert Stock:", self.spin_min)

        layout.addLayout(form)

        # Buttons
        h_btn = QHBoxLayout()
        h_btn.addStretch()
        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        h_btn.addWidget(btn_cancel)

        btn_save = QPushButton("Save Material", self)
        btn_save.setProperty("class", "btn-primary")
        btn_save.clicked.connect(self.save)
        h_btn.addWidget(btn_save)
        layout.addLayout(h_btn)

    def save(self):
        code = self.txt_code.text().strip()
        name = self.txt_name.text().strip()
        barcode = self.txt_barcode.text().strip()
        cat = self.txt_category.text().strip() or "General"
        unit = self.combo_unit.currentText()
        opening = self.spin_opening.value()
        unit_price = self.spin_unit_price.value()
        min_stock = self.spin_min.value()

        if not code or not name or not barcode:
            QMessageBox.warning(self, "Validation Error", "Material Code, Name, and Barcode are required.")
            return

        if self.material:
            ok, msg = MaterialService.update_material(
                self.material["id"], name, cat, unit, barcode, min_stock,
                unit_price=unit_price, opening_stock=opening
            )
        else:
            ok, msg, _ = MaterialService.add_material(
                code, name, cat, unit, barcode,
                opening_stock=opening, min_stock=min_stock, unit_price=unit_price
            )

        if ok:
            self.accept()
        else:
            QMessageBox.critical(self, "Save Error", msg)


class StockAdjustmentDialog(QDialog):
    """Controlled dialog for manual inventory stock adjustments with mandatory audit reason."""
    def __init__(self, material, parent=None):
        super().__init__(parent)
        self.material = material
        self.setWindowTitle(f"Stock Adjustment - {material['material_code']}")
        self.setMinimumWidth(400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        lbl_header = QLabel(f"<b>Material:</b> {self.material['name']} ({self.material['material_code']})<br>"
                            f"<b>Current Stock:</b> {self.material['current_stock']} {self.material['unit']}")
        lbl_header.setStyleSheet("font-size: 13px; color: #1e293b; background-color: #f1f5f9; padding: 10px; border-radius: 6px;")
        layout.addWidget(lbl_header)

        form = QFormLayout()
        self.combo_type = QComboBox(self)
        self.combo_type.addItems(["ADD (Receipt / Found Stock)", "SUBTRACT (Damage / Scrap)", "SET (Physical Stocktake Count)"])
        form.addRow("Adjustment Action:", self.combo_type)

        self.spin_qty = QDoubleSpinBox(self)
        self.spin_qty.setRange(0.1, 999999.0)
        self.spin_qty.setValue(1.0)
        form.addRow("Quantity:", self.spin_qty)

        self.txt_reason = QLineEdit(self)
        self.txt_reason.setPlaceholderText("Mandatory reason (e.g. Physical audit reconciliation, Damaged on floor)")
        form.addRow("Documented Reason *:", self.txt_reason)
        layout.addLayout(form)

        h_btn = QHBoxLayout()
        h_btn.addStretch()
        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        h_btn.addWidget(btn_cancel)

        btn_apply = QPushButton("Apply Stock Adjustment", self)
        btn_apply.setProperty("class", "btn-primary")
        btn_apply.clicked.connect(self.apply_adjustment)
        h_btn.addWidget(btn_apply)
        layout.addLayout(h_btn)

    def apply_adjustment(self):
        reason = self.txt_reason.text().strip()
        if not reason:
            QMessageBox.warning(self, "Reason Required", "Please enter a reason for adjusting inventory stock.")
            self.txt_reason.setFocus()
            return

        action_idx = self.combo_type.currentIndex()
        action_type = "ADD" if action_idx == 0 else ("SUBTRACT" if action_idx == 1 else "SET")
        qty = self.spin_qty.value()
        user = SettingsService.get_setting("storekeeper_name", "Storekeeper")

        ok, msg = MaterialService.adjust_stock(self.material["id"], action_type, qty, reason, user_name=user)
        if ok:
            QMessageBox.information(self, "Adjustment Recorded", f"✔ {msg}")
            self.accept()
        else:
            QMessageBox.critical(self, "Adjustment Error", f"❌ {msg}")


class StockDatabaseView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.materials: list[dict] = []
        self.selected_material: dict | None = None
        self.init_ui()
        self.refresh_table()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 24, 30, 24)
        main_layout.setSpacing(16)

        # 1. Header & Actions Bar
        header_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        lbl_title = QLabel("Stock Database & Inventory Master", self)
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0f172a;")
        lbl_sub = QLabel("Search inventory, add materials, perform stock adjustments, and view movement history.", self)
        lbl_sub.setStyleSheet("font-size: 13px; color: #64748b;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        header_row.addLayout(title_box, 1)

        self.btn_export_excel = QPushButton("📊 Export Excel", self)
        self.btn_export_excel.setFixedHeight(34)
        self.btn_export_excel.clicked.connect(self.export_excel)
        header_row.addWidget(self.btn_export_excel)

        main_layout.addLayout(header_row)

        # 2. Search Toolbar
        search_card = QFrame(self)
        search_card.setProperty("class", "card")
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(14, 10, 14, 10)
        search_layout.setSpacing(12)

        lbl_search = QLabel("🔍 Instant Search:", search_card)
        lbl_search.setStyleSheet("font-weight: 600; color: #334155;")
        search_layout.addWidget(lbl_search)

        self.txt_search = QLineEdit(search_card)
        self.txt_search.setPlaceholderText("Filter by Material Code, Name, Category, or Barcode as you type...")
        self.txt_search.textChanged.connect(self.filter_table)
        search_layout.addWidget(self.txt_search, 1)

        btn_clear_search = QPushButton("✖ Clear", search_card)
        btn_clear_search.clicked.connect(lambda: self.txt_search.clear())
        search_layout.addWidget(btn_clear_search)

        main_layout.addWidget(search_card)

        # 3. Main Materials Table (Full Width, Excel Styled)
        self.table = QTableWidget(self)
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "S no",
            "material code",
            "material name",
            "uom",
            "opening stock",
            "recived stock",
            "issued stock",
            "closing stock",
            "unit price",
            "total price"
        ])

        # Excel Spreadsheet Styling: Dark Navy Header & Crisp Cell Gridlines
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

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 65)   # S no
        self.table.setColumnWidth(1, 150)  # material code
        # material name (col 2): stretches to fill screen width
        self.table.setColumnWidth(3, 85)   # uom
        self.table.setColumnWidth(4, 120)  # opening stock
        self.table.setColumnWidth(5, 120)  # recived stock
        self.table.setColumnWidth(6, 120)  # issued stock
        self.table.setColumnWidth(7, 125)  # closing stock
        self.table.setColumnWidth(8, 120)  # unit price
        self.table.setColumnWidth(9, 135)  # total price

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        self.table.cellDoubleClicked.connect(self.on_table_double_clicked)
        main_layout.addWidget(self.table, 1)

        self.lbl_table_count = QLabel("0 materials registered", self)
        self.lbl_table_count.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 500;")
        main_layout.addWidget(self.lbl_table_count)

    def refresh_table(self):
        self.materials = MaterialService.get_all_summary("", active_only=False)
        self.filter_table()

    def filter_table(self):
        query = self.txt_search.text().strip().lower()
        filtered = [
            m for m in self.materials
            if query in m["material_code"].lower()
            or query in m["name"].lower()
            or query in m.get("category", "").lower()
            or query in m.get("barcode", "").lower()
        ]

        min_rows = 20
        num_items = len(filtered)
        total_rows = max(min_rows, num_items)
        self.table.setRowCount(total_rows)
        currency = SettingsService.get_setting("currency_symbol", "₹")
        for row_idx in range(total_rows):
            if row_idx < num_items:
                mat = filtered[row_idx]
                # 0. S no
                item_sno = QTableWidgetItem(str(row_idx + 1))
                item_sno.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, 0, item_sno)

                # 1. material code
                item_code = QTableWidgetItem(mat["material_code"])
                item_code.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, 1, item_code)

                # 2. material name
                item_name = QTableWidgetItem(mat["name"])
                self.table.setItem(row_idx, 2, item_name)

                # 3. uom
                item_uom = QTableWidgetItem(mat["unit"])
                item_uom.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, 3, item_uom)

                # 4. opening stock
                op_val = float(mat.get('opening_stock', 0.0))
                op_str = str(int(op_val)) if op_val.is_integer() else f"{op_val:.4f}".rstrip("0").rstrip(".")
                item_opening = QTableWidgetItem(op_str)
                item_opening.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, 4, item_opening)

                # 5. recived stock
                rec_val = float(mat.get('received_stock', 0.0))
                rec_str = str(int(rec_val)) if rec_val.is_integer() else f"{rec_val:.4f}".rstrip("0").rstrip(".")
                item_rec = QTableWidgetItem(rec_str)
                item_rec.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, 5, item_rec)

                # 6. issued stock
                iss_val = float(mat.get('issued_stock', 0.0))
                iss_str = str(int(iss_val)) if iss_val.is_integer() else f"{iss_val:.4f}".rstrip("0").rstrip(".")
                item_iss = QTableWidgetItem(iss_str)
                item_iss.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, 6, item_iss)

                # 7. closing stock
                stock = float(mat.get("closing_stock", mat.get("current_stock", 0.0)))
                min_stock = float(mat.get("min_stock", 0.0))
                clo_str = str(int(stock)) if stock.is_integer() else f"{stock:.4f}".rstrip("0").rstrip(".")
                item_closing = QTableWidgetItem(clo_str)
                item_closing.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if stock <= 0:
                    item_closing.setForeground(Qt.red)
                elif stock <= min_stock:
                    item_closing.setForeground(Qt.darkYellow)
                self.table.setItem(row_idx, 7, item_closing)

                # 8. unit price
                unit_price = float(mat.get("unit_price", 0.0))
                item_unit_p = QTableWidgetItem(f"{currency} {unit_price:.2f}")
                item_unit_p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, 8, item_unit_p)

                # 9. total price
                tot_price = float(mat.get("total_price", stock * unit_price))
                item_tot_p = QTableWidgetItem(f"{currency} {tot_price:,.2f}")
                item_tot_p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, 9, item_tot_p)
            else:
                for c in range(10):
                    blank_item = QTableWidgetItem("")
                    blank_item.setFlags(Qt.NoItemFlags)
                    self.table.setItem(row_idx, c, blank_item)

        self.lbl_table_count.setText(f"Showing {len(filtered)} of {len(self.materials)} materials")

    def on_row_selected(self):
        selected_rows = self.table.selectedItems()
        if not selected_rows:
            self.selected_material = None
            return

        row = selected_rows[0].row()
        code_item = self.table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        mat = MaterialService.get_by_code(code)
        if mat:
            self.selected_material = mat

    def on_table_double_clicked(self, row, col):
        code_item = self.table.item(row, 1)
        if code_item:
            mat = MaterialService.get_by_code(code_item.text().strip())
            if mat:
                self.open_edit_dialog(mat)

    def open_selected_edit(self):
        if self.selected_material:
            self.open_edit_dialog(self.selected_material)

    def open_add_dialog(self):
        dialog = MaterialEditDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_table()

    def open_edit_dialog(self, mat: dict):
        dialog = MaterialEditDialog(material=mat, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_table()

    def open_adjust_dialog(self):
        if not self.selected_material:
            return
        dialog = StockAdjustmentDialog(self.selected_material, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_table()
            self.on_row_selected()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Materials to CSV", str(DATA_DIR / "materials_inventory.csv"), "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            ok, msg = MaterialService.export_to_csv(path)
            if ok:
                QMessageBox.information(self, "Export Succeeded", f"✔ {msg}")
            else:
                QMessageBox.critical(self, "Export Failed", msg)

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Materials to Excel", str(DATA_DIR / "materials_inventory.xlsx"), "Excel Files (*.xlsx);;All Files (*)"
        )
        if path:
            ok, msg = MaterialService.export_to_excel(path)
            if ok:
                QMessageBox.information(self, "Excel Export", f"✔ {msg}")
            else:
                QMessageBox.critical(self, "Excel Export Failed", msg)

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Materials from CSV", str(DATA_DIR), "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            added, updated, errors = MaterialService.import_from_csv(path)
            err_text = "\n".join(errors[:5]) + ("..." if len(errors) > 5 else "") if errors else "None"
            QMessageBox.information(
                self,
                "Import Complete",
                f"CSV Import Summary:\n\n• Added New Materials: {added}\n• Updated Existing: {updated}\n• Errors: {len(errors)}\n\nDetails:\n{err_text}"
            )
            self.refresh_table()

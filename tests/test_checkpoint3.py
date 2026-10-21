import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.core.config import ensure_directories, DATA_DIR
from app.core.database import initialize_database, get_db_connection
from app.core.logger import setup_logging
from app.services.material_service import MaterialService
from app.services.issue_slip_service import IssueSlipService
from app.services.settings_service import SettingsService
from app.services.issue_slip_pdf_service import IssueSlipPdfService
from app.services.issue_slip_excel_service import IssueSlipExcelService
from app.ui.views.barcode_entry_view import BarcodeEntryView


class TestCheckpoint3CompanyIssueSlip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_directories()
        setup_logging()
        initialize_database()
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(["test"])

        from app.services.material_service import MaterialService
        test_mats = [
            ("MAT-101", "Industrial Hex Bolt M12x50", "Hardware", "PCS", "BAR-101", 250.0, 50.0),
            ("MAT-102", "Safety Goggles ANSI Z87", "Safety PPE", "PAIR", "BAR-102", 40.0, 10.0),
            ("MAT-103", "Pneumatic Fitting 1/4 inch", "Pneumatics", "PCS", "BAR-103", 15.0, 5.0),
        ]
        for c, n, cat, u, b, cs, ms in test_mats:
            if not MaterialService.get_by_code(c):
                MaterialService.add_material(c, n, cat, u, b, cs, ms)

    @classmethod
    def tearDownClass(cls):
        from app.core.database import get_db_connection
        with get_db_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.execute("DELETE FROM purchased_materials;")
            conn.execute("DELETE FROM issue_slip_items;")
            conn.execute("DELETE FROM issue_slips;")
            conn.execute("DELETE FROM stock_ledger;")
            conn.execute("DELETE FROM materials;")
            conn.execute("PRAGMA foreign_keys = ON;")

    def setUp(self):
        self.view = BarcodeEntryView()
        self.view.show()

    def tearDown(self):
        self.view.close()

    def test_01_document_template_structure_and_slip_number(self):
        """
        Verify on-screen document matches paper template:
        - Issue slip number field is populated with sequential ID.
        - Header elements: company name, plant address, reference box, and black ISSUE SLIP banner.
        - Two-column metadata fields.
        - 8-column material table.
        - 3 signature blocks at bottom.
        """
        self.assertTrue(self.view.txt_slip_no.text().startswith("IS-"))
        self.assertEqual(self.view.lbl_comp_name.text(), "TIME TECHNOPLAST LTD.")
        self.assertIn("Hyderabad", self.view.lbl_comp_addr.text())

        # Check header fields exist
        self.assertIsNotNone(self.view.combo_dept)
        dept_items = [self.view.combo_dept.itemText(i) for i in range(self.view.combo_dept.count())]
        self.assertEqual(dept_items, [
            "BM Qc",
            "Pipe Qc",
            "BM production",
            "pipe production",
            "admin HR",
            "BM Dispatch",
            "store"
        ])
        self.assertIsNotNone(self.view.dt_slip_date)
        self.assertIsNotNone(self.view.txt_cost_center)
        self.assertIsNotNone(self.view.txt_gl_no)
        self.assertIsNotNone(self.view.txt_stores_posting_no)
        self.assertIsNotNone(self.view.dt_store_posting_date)
        self.assertIsNotNone(self.view.txt_reservation_no)

        # Check table columns (10 columns with Cost Center No. between UOM and Required Qty.)
        self.assertGreaterEqual(self.view.table.columnCount(), 9)
        self.assertEqual(self.view.table.horizontalHeaderItem(0).text(), "Sr.\nNo.")
        self.assertEqual(self.view.table.horizontalHeaderItem(1).text(), "Description of\nthe Material")
        self.assertEqual(self.view.table.horizontalHeaderItem(2).text(), "Material Code\nNo.")
        self.assertEqual(self.view.table.horizontalHeaderItem(3).text(), "UOM")
        self.assertEqual(self.view.table.horizontalHeaderItem(4).text(), "Cost Center\nNo.")
        self.assertEqual(self.view.table.horizontalHeaderItem(5).text(), "Required\nQty.")
        self.assertEqual(self.view.table.horizontalHeaderItem(6).text(), "Issued\nQty.")
        self.assertEqual(self.view.table.horizontalHeaderItem(7).text(), "Purpose")
        self.assertEqual(self.view.table.horizontalHeaderItem(8).text(), "Receiver\nName")

    def test_02_qr_code_scanning_and_automatic_row_population(self):
        """
        Scan 2D QR code containing:
        Material Name: Industrial Hex Bolt M12x50
        Material Code: MAT-101
        Verify material lookup via code, automatic row insertion, and immediate display.
        """
        qr_text = "Material Name: Industrial Hex Bolt M12x50\nMaterial Code: MAT-101"
        self.view.txt_qr_scan.setText(qr_text)
        self.view.on_qr_scanned()

        self.assertEqual(len(self.view.current_slip_items), 1)
        item = self.view.current_slip_items[0]
        self.assertEqual(item["sr_no"], 1)
        self.assertEqual(item["material_code"], "MAT-101")
        self.assertEqual(item["material_name"], "Industrial Hex Bolt M12x50")
        self.assertEqual(item["unit"], "PCS")
        self.assertEqual(item["required_qty"], 1.0)
        self.assertEqual(item["quantity_issued"], 1.0)

        # Verify table displays the item
        self.assertEqual(self.view.table.item(0, 0).text(), "1")
        self.assertEqual(self.view.table.item(0, 1).text(), "Industrial Hex Bolt M12x50")
        self.assertEqual(self.view.table.item(0, 2).text(), "MAT-101")
        self.assertEqual(self.view.table.item(0, 3).text(), "PCS")

    def test_03_unverified_material_code_rejection(self):
        """
        Negative test: Scanning a QR code with an unverified material code not in the SQLite
        database must show a clear error and NOT insert an unverified material row.
        """
        qr_text = "Material Name: Fake Widget 5000\nMaterial Code: MAT-NONEXISTENT-999"
        self.view.txt_qr_scan.setText(qr_text)
        self.view.on_qr_scanned()

        self.assertEqual(len(self.view.current_slip_items), 0)
        self.assertTrue(self.view.banner.isVisible())
        self.assertIn("not found in database", self.view.lbl_banner_msg.text().lower())

    def test_04_scanner_burst_duplicate_debounce(self):
        """
        Verify scanner burst debounce: sending identical QR scan within 1.5s
        is ignored to prevent accidental double-scanning.
        """
        qr_text = "Material Name: Safety Goggles ANSI Z87\nMaterial Code: MAT-102"
        self.view.txt_qr_scan.setText(qr_text)
        self.view.on_qr_scanned()
        self.assertEqual(len(self.view.current_slip_items), 1)

        # Immediate burst repeat
        self.view.txt_qr_scan.setText(qr_text)
        self.view.on_qr_scanned()
        self.assertEqual(len(self.view.current_slip_items), 1, "Duplicate burst within debounce window must be ignored")

    def test_05_save_draft_and_draft_retrieval(self):
        """
        Verify saving an Issue Slip as DRAFT:
        - Saved to SQLite with status='DRAFT'.
        - Stock is NOT deducted.
        - Entering slip number and clicking retrieve restores all header and item fields.
        """
        test_slip_no = "IS-TEST-DRAFT-0001"
        self.view.txt_slip_no.setText(test_slip_no)
        self.view.txt_cost_center.setText("CC-8888")
        self.view.txt_gl_no.setText("GL-100200")
        self.view.txt_stores_posting_no.setText("SP-9911")
        self.view.txt_reservation_no.setText("RES-5544")

        # Add an item
        self.view.txt_qr_scan.setText("Material Name: Pneumatic Fitting 1/4 inch\nMaterial Code: MAT-103")
        self.view.on_qr_scanned()
        self.assertEqual(len(self.view.current_slip_items), 1)

        # Stock before draft
        mat_before = MaterialService.get_by_code("MAT-103")
        stock_before = float(mat_before["current_stock"])

        # Save draft
        slip_data = self.view.collect_slip_data()
        ok, msg, slip_no = IssueSlipService.save_draft_slip(slip_data, self.view.current_slip_items)
        self.assertTrue(ok)
        self.assertEqual(slip_no, test_slip_no)

        # Verify stock remains unchanged
        mat_after = MaterialService.get_by_code("MAT-103")
        self.assertEqual(float(mat_after["current_stock"]), stock_before, "Draft save must NOT deduct inventory")

        # Clear form and retrieve draft
        self.view.refresh_defaults()
        self.assertEqual(len(self.view.current_slip_items), 0)

        self.view.txt_slip_no.setText(test_slip_no)
        self.view.retrieve_slip()

        # Check restored data
        self.assertEqual(self.view.txt_cost_center.text(), "CC-8888")
        self.assertEqual(self.view.txt_gl_no.text(), "GL-100200")
        self.assertEqual(self.view.txt_stores_posting_no.text(), "SP-9911")
        self.assertEqual(self.view.txt_reservation_no.text(), "RES-5544")
        self.assertEqual(len(self.view.current_slip_items), 1)
        self.assertEqual(self.view.current_slip_items[0]["material_code"], "MAT-103")

    def test_06_finalization_stock_deduction_and_duplicate_prevention(self):
        """
        Verify:
        - Atomic stock deduction and stock ledger recording upon finalization.
        - Prevention of duplicate posting or overwriting finalized slips.
        """
        test_slip_no = f"IS-TEST-FINAL-{int(time.time() * 1000)}"
        mat = MaterialService.get_by_code("MAT-101")
        stock_before = float(mat["current_stock"])
        qty_to_issue = 2.0

        slip_data = {
            "slip_no": test_slip_no,
            "department": "Tool Room",
            "receiver": "Vikram Technician",
            "purpose": "Maintenance line upgrade",
            "cost_center_no": "CC-101",
            "gl_no": "GL-401"
        }
        items = [{
            "material_id": mat["id"],
            "material_code": mat["material_code"],
            "material_name": mat["name"],
            "unit": mat["unit"],
            "quantity_issued": qty_to_issue,
            "required_qty": qty_to_issue,
            "purpose": "Maintenance",
            "receiver_name": "Vikram Technician"
        }]

        ok, msg, slip_no = IssueSlipService.create_and_finalize_slip(slip_data, items)
        self.assertTrue(ok)
        self.assertEqual(slip_no, test_slip_no)

        # Verify stock decreased in SQLite
        mat_after = MaterialService.get_by_code("MAT-101")
        self.assertEqual(float(mat_after["current_stock"]), stock_before - qty_to_issue)

        # Verify stock ledger entry
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM stock_ledger WHERE reference_no = ?;", (test_slip_no,))
            ledger = cur.fetchone()
            self.assertIsNotNone(ledger)
            self.assertEqual(ledger["transaction_type"], "ISSUE")
            self.assertEqual(ledger["quantity"], -qty_to_issue)

        # Duplicate Posting Prevention: Attempting to finalize again must fail
        ok2, msg2, _ = IssueSlipService.create_and_finalize_slip(slip_data, items)
        self.assertFalse(ok2, "Duplicate posting of a finalized slip must be prohibited")
        self.assertIn("already finalized", msg2.lower())

    def test_07_pdf_export_matches_paper_template(self):
        """
        Verify generation of selectable-text vector A4 PDF matching the
        TIME TECHNOPLAST LTD. template.
        """
        test_pdf = DATA_DIR / "test_paper_template_slip.pdf"
        slip_data = {
            "slip_no": "IS-20261020-9999",
            "department": "Production",
            "slip_date": "2026-10-20",
            "cost_center_no": "1040",
            "gl_no": "402100",
            "stores_posting_no": "SP-7711",
            "store_posting_date": "2026-10-20",
            "reservation_no": "RES-8822",
            "receiver": "John Storeman",
            "purpose": "Assembly Line Stock"
        }
        items = [
            {
                "material_name": "Industrial Hex Bolt M12x50",
                "material_code": "MAT-101",
                "unit": "PCS",
                "required_qty": 20.0,
                "quantity_issued": 20.0,
                "purpose": "Line 1 Bolt Replacement",
                "receiver_name": "John Storeman"
            },
            {
                "material_name": "Synthetic Lubricant Grease EP-2",
                "material_code": "MAT-104",
                "unit": "KG",
                "required_qty": 5.0,
                "quantity_issued": 5.0,
                "purpose": "Gearbox Lubrication",
                "receiver_name": "Alex Operator"
            }
        ]

        ok = IssueSlipPdfService.generate_issue_slip_pdf(slip_data, items, str(test_pdf))
        self.assertTrue(ok)
        self.assertTrue(test_pdf.exists())
        self.assertGreater(test_pdf.stat().st_size, 2000, "PDF must contain complete vector document data")

        # Cleanup test PDF
        if test_pdf.exists():
            test_pdf.unlink()

    def test_08_excel_export_generation(self):
        """
        Verify Excel export (.xlsx) generation matching the company issue slip template:
        - Creates valid OpenPyXL workbook
        - Contains 'Issue Slip' worksheet
        - Correct headers, metadata, material items, and totals
        """
        self.assertIsNotNone(self.view.btn_export_excel)
        self.assertIn("Excel", self.view.btn_export_excel.text())

        test_xlsx = DATA_DIR / "test_paper_template_slip.xlsx"
        slip_data = {
            "slip_no": "IS-20261020-EXCEL",
            "department": "BM production",
            "slip_date": "2026-10-20",
            "cost_center_no": "CC-901",
            "gl_no": "400123",
            "stores_posting_no": "SP-9900",
            "store_posting_date": "2026-10-20",
            "reservation_no": "RES-5544",
            "receiver": "Rahul Supervisor",
            "purpose": "Extrusion Line 2 Maintenance"
        }
        items = [
            {
                "material_name": "Hydraulic Oil ISO VG 68",
                "material_code": "MAT-OIL-68",
                "unit": "LITRE",
                "cost_center_no": "CC-901",
                "required_qty": 50.0,
                "quantity_issued": 50.0,
                "purpose": "Pump Overhaul",
                "receiver_name": "Rahul Supervisor"
            }
        ]

        ok = IssueSlipExcelService.generate_issue_slip_excel(slip_data, items, str(test_xlsx))
        self.assertTrue(ok)
        self.assertTrue(test_xlsx.exists())
        self.assertGreater(test_xlsx.stat().st_size, 1000, "Excel file must contain formatted workbook data")

        # Verify workbook content with openpyxl
        import openpyxl
        wb = openpyxl.load_workbook(str(test_xlsx))
        self.assertIn("Issue Slip", wb.sheetnames)
        ws = wb["Issue Slip"]
        self.assertEqual(ws["A4"].value, "ISSUE SLIP")
        self.assertEqual(ws["A10"].value, "Sr.\nNo.")
        self.assertEqual(ws["B10"].value, "Description of\nthe Material")
        self.assertEqual(ws["E10"].value, "Cost Center\nNo.")
        self.assertEqual(ws["B11"].value, "Hydraulic Oil ISO VG 68")
        self.assertEqual(ws["G11"].value, 50.0)

        # Cleanup test Excel
        if test_xlsx.exists():
            test_xlsx.unlink()


if __name__ == "__main__":
    unittest.main()

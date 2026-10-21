import os
import sys
import unittest
from pathlib import Path
from PIL import Image
import zxingcpp

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.core.config import ensure_directories, DATA_DIR
from app.core.database import initialize_database
from app.core.logger import setup_logging
from app.services.material_service import MaterialService
from app.services.barcode_service import BarcodeService
from app.ui.views.barcode_generator_view import BarcodeGeneratorView


class TestCheckpoint4QRCodeGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_directories()
        setup_logging()
        initialize_database()
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(["test"])

    def setUp(self):
        self.view = BarcodeGeneratorView()
        self.view.show()

    def tearDown(self):
        self.view.close()

    def test_01_qr_code_image_generation(self):
        """Positive test: Generate QR code image with standard defaults in memory."""
        payload = "Material Name: Test Item\nMaterial Code: MAT-TEST-001"
        img = BarcodeService.generate_qr_code_image(payload)
        self.assertIsNotNone(img)
        self.assertGreater(img.size[0], 100)
        self.assertGreater(img.size[1], 100)

        # Optical decoding via zxingcpp
        res = zxingcpp.read_barcode(img)
        self.assertIsNotNone(res)
        self.assertEqual(res.format, zxingcpp.BarcodeFormat.QRCode)
        self.assertEqual(res.text, payload)

    def test_02_qr_label_preview_card_generation(self):
        """Positive test: Generate factory warehouse QR label card with branding."""
        label_img = BarcodeService.generate_qr_label_preview(
            material_name="Industrial Hex Bolt M12x50",
            material_code="MAT-101",
            company_name="Apex Manufacturing"
        )
        self.assertIsNotNone(label_img)
        self.assertEqual(label_img.size[0], 480)
        self.assertEqual(label_img.size[1], 280)

        # Optical decoding from composite card must yield exactly two fields
        res = zxingcpp.read_barcode(label_img)
        self.assertIsNotNone(res)
        self.assertEqual(res.format, zxingcpp.BarcodeFormat.QRCode)
        expected_payload = "Material Name: Industrial Hex Bolt M12x50\nMaterial Code: MAT-101"
        self.assertEqual(res.text, expected_payload)

    def test_03_qr_save_label_as_image_and_pdf(self):
        """Verify QR label saving to PNG image and multi-label printable PDF sheet."""
        test_png = DATA_DIR / "test_qr_label_export.png"
        test_pdf = DATA_DIR / "test_qr_label_sheet.pdf"

        # Export PNG
        ok_png = BarcodeService.save_qr_label_as_image(str(test_png), "Hex Bolt", "MAT-101")
        self.assertTrue(ok_png)
        self.assertTrue(test_png.exists())
        self.assertGreater(test_png.stat().st_size, 1000)

        # Test optical decoding from saved PNG file
        saved_img = Image.open(str(test_png))
        res = zxingcpp.read_barcode(saved_img)
        self.assertIsNotNone(res)
        self.assertEqual(res.text, "Material Name: Hex Bolt\nMaterial Code: MAT-101")

        # Export PDF sheet (6 copies)
        ok_pdf = BarcodeService.export_pdf_qr_sheet(str(test_pdf), "Hex Bolt", "MAT-101", copies=6)
        self.assertTrue(ok_pdf)
        self.assertTrue(test_pdf.exists())
        self.assertGreater(test_pdf.stat().st_size, 1000)

        # Cleanup test files
        if test_png.exists():
            test_png.unlink()
        if test_pdf.exists():
            test_pdf.unlink()

    def test_04_ui_initial_state_empty_and_no_placeholders(self):
        """
        Verify:
        1. Material Name input field is empty string on form open.
        2. Material Code input field is empty string on form open.
        3. No placeholder examples inside either input field.
        4. No automatic material selection or sample data loaded.
        5. Export buttons disabled until generated.
        """
        self.assertEqual(self.view.txt_mat_name.text(), "")
        self.assertEqual(self.view.txt_mat_code.text(), "")
        self.assertEqual(self.view.txt_uom.text(), "")
        self.assertEqual(self.view.txt_mat_name.placeholderText(), "")
        self.assertEqual(self.view.txt_mat_code.placeholderText(), "")
        self.assertEqual(self.view.txt_uom.placeholderText(), "")
        self.assertIsNone(self.view.current_preview_image)
        self.assertFalse(self.view.btn_save_png.isEnabled())
        self.assertFalse(self.view.btn_export_pdf.isEnabled())

    def test_05_ui_validation_when_fields_empty(self):
        """
        Verify validation message is shown if either or both fields are empty,
        and QR code is NOT generated.
        """
        # Both empty
        self.view.txt_mat_name.setText("")
        self.view.txt_mat_code.setText("")
        self.view.generate_qr_code()
        self.assertTrue(self.view.banner.isVisible())
        self.assertIn("both", self.view.lbl_banner.text().lower())
        self.assertIsNone(self.view.current_preview_image)

        # Only Material Name provided
        self.view.txt_mat_name.setText("Precision Drill Bit")
        self.view.txt_mat_code.setText("")
        self.view.generate_qr_code()
        self.assertTrue(self.view.banner.isVisible())
        self.assertIn("material code is required", self.view.lbl_banner.text().lower())
        self.assertIsNone(self.view.current_preview_image)

        # Only Material Code provided
        self.view.txt_mat_name.setText("")
        self.view.txt_mat_code.setText("MAT-555")
        self.view.generate_qr_code()
        self.assertTrue(self.view.banner.isVisible())
        self.assertIn("material name is required", self.view.lbl_banner.text().lower())
        self.assertIsNone(self.view.current_preview_image)

    def test_06_ui_generate_qr_code_on_button_click_and_payload_accuracy(self):
        """
        Verify QR code generates only after entering both values and clicking
        the Generate QR Code button, encoding exactly two fields.
        """
        mat_name = "Pneumatic Solenoid Valve 24V"
        mat_code = "MAT-SOL-24V"

        self.view.txt_mat_name.setText(mat_name)
        self.view.txt_mat_code.setText(mat_code)

        # Still None before button clicked
        self.assertIsNone(self.view.current_preview_image)

        # Click Generate QR Code
        self.view.btn_generate_qr.click()

        # Verified generated
        self.assertIsNotNone(self.view.current_preview_image)
        self.assertFalse(self.view.banner.isVisible())
        self.assertTrue(self.view.btn_save_png.isEnabled())
        self.assertTrue(self.view.btn_export_pdf.isEnabled())

        # Decode generated preview image using optical decoder
        res = zxingcpp.read_barcode(self.view.current_preview_image)
        self.assertIsNotNone(res)
        self.assertEqual(res.format, zxingcpp.BarcodeFormat.QRCode)

        # Exactly two fields encoded
        expected_text = f"Material Name: {mat_name}\nMaterial Code: {mat_code}"
        self.assertEqual(res.text, expected_text)
        lines = res.text.strip().split("\n")
        self.assertEqual(len(lines), 2, "QR code must encode exactly two fields: Material Name and Material Code")
        self.assertTrue(lines[0].startswith("Material Name: "))
        self.assertTrue(lines[1].startswith("Material Code: "))

    def test_07_preserved_code128_barcode_functionality(self):
        """Ensure Code 128 barcode generation and decoding remains fully preserved."""
        code128_img = BarcodeService.generate_barcode_image("BAR-999-PRESERVED")
        self.assertIsNotNone(code128_img)
        res = zxingcpp.read_barcode(code128_img)
        self.assertIsNotNone(res)
        self.assertEqual(res.format, zxingcpp.BarcodeFormat.Code128)
        self.assertEqual(res.text, "BAR-999-PRESERVED")

    def test_08_qr_code_generation_with_uom(self):
        """Verify QR code generation, label card rendering, and optical decoding when UOM is provided."""
        mat_name = "Brass Fitting 1/2 Inch"
        mat_code = "MAT-BRS-50"
        uom = "PCS"

        self.view.txt_mat_name.setText(mat_name)
        self.view.txt_mat_code.setText(mat_code)
        self.view.txt_uom.setText(uom)

        self.view.btn_generate_qr.click()

        self.assertIsNotNone(self.view.current_preview_image)
        res = zxingcpp.read_barcode(self.view.current_preview_image)
        self.assertIsNotNone(res)
        expected_text = f"Material Name: {mat_name}\nMaterial Code: {mat_code}\nUOM: {uom}"
        self.assertEqual(res.text, expected_text)


if __name__ == "__main__":
    unittest.main()

import io
import os
import json
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

import zxingcpp
import qrcode
import qrcode.constants
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.drawing.image import Image as XLImage

from app.core.config import DATA_DIR, BASE_DIR
from app.core.database import get_db_connection
from app.core.logger import get_logger
from app.services.settings_service import SettingsService

logger = get_logger("IssueSlipApp.BarcodeService")


class BarcodeService:
    _catalog_cache: Optional[list[dict]] = None
    @staticmethod
    def generate_barcode_image(barcode_text: str, format_name: str = "code128") -> Optional[Image.Image]:
        """
        Generate pure barcode bars image using Code 128 with native pixel-exact module width,
        adequate quiet zones, and no overlapping text.
        """
        clean_text = barcode_text.strip()
        if not clean_text:
            return None

        try:
            bc_class = barcode.get_barcode_class(format_name)
            writer = ImageWriter()
            # 254 DPI: 1 inch = 25.4 mm = 254 px -> exactly 10 pixels per millimeter
            writer.dpi = 254

            # Module width: 0.20mm = exactly 2.0px/module, 0.30mm = exactly 3.0px/module
            # This eliminates scaling rounding errors and blurred antialiasing
            mod_w = 0.20 if len(clean_text) > 10 else 0.30

            bc = bc_class(clean_text, writer=writer)
            fp = io.BytesIO()
            bc.write(fp, options={
                "write_text": False,
                "module_height": 10.0,
                "module_width": mod_w,
                "quiet_zone": 5.0
            })
            fp.seek(0)
            return Image.open(fp).convert("RGBA")
        except Exception as exc:
            logger.error(f"Failed to generate barcode for '{clean_text}': {exc}")
            return None

    @classmethod
    def generate_label_preview(
        cls,
        material_code: str,
        material_name: str,
        barcode_text: str,
        company_name: str = ""
    ) -> Optional[Image.Image]:
        """
        Render a factory warehouse label card with company header, material details,
        cleanly separated barcode bars, and centered human-readable text below the bars.
        All elements fit inside the card borders without clipping.
        """
        clean_bc = barcode_text.strip()
        if not clean_bc:
            return None

        if not company_name:
            company_name = SettingsService.get_setting("company_name", "Apex Industrial Manufacturing")

        barcode_img = cls.generate_barcode_image(clean_bc)
        if not barcode_img:
            return None

        bw, bh = barcode_img.size

        # Card dimensions: fixed height 280, width accommodates barcode with 50px side margin
        card_w = max(480, bw + 50)
        card_h = 280

        card = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 255))
        draw = ImageDraw.Draw(card)

        # 1. Complete card border (unclipped with 2px padding from outer boundary)
        draw.rounded_rectangle([2, 2, card_w - 3, card_h - 3], radius=10, outline="#94a3b8", width=2)

        # 2. Header banner (Company name)
        draw.rounded_rectangle([2, 2, card_w - 3, 38], radius=8, fill="#1e293b")
        draw.text((16, 11), company_name.upper(), fill="#f8fafc")

        # 3. Material Code and Description
        draw.text((16, 48), f"ITEM CODE: {material_code}", fill="#0f172a")
        display_name = material_name[:42] + "..." if len(material_name) > 42 else material_name
        draw.text((16, 68), display_name, fill="#475569")

        # 4. Subtle separator line above barcode
        draw.line([(14, 92), (card_w - 14, 92)], fill="#e2e8f0", width=1)

        # 5. Barcode bars (centered horizontally with adequate quiet zones)
        bc_x = (card_w - bw) // 2
        bc_y = 102
        card.paste(barcode_img, (bc_x, bc_y), barcode_img)

        # 6. Human-readable barcode value positioned below the bars with 10px clear white space gap
        text_y = bc_y + bh + 10
        bbox = draw.textbbox((0, 0), clean_bc)
        tw = bbox[2] - bbox[0]
        text_x = (card_w - tw) // 2
        draw.text((text_x, text_y), clean_bc, fill="#0f172a")

        return card

    @classmethod
    def generate_qr_code_image(
        cls,
        material_name: str,
        material_code: str = "",
        uom: str = ""
    ) -> Optional[Image.Image]:
        """
        Generate a QR code encoding material fields.
        Uses standard default QR settings: version auto-fit, error_correction=M, box_size=8, border=4.
        """
        if material_code:
            name = material_name.strip()
            code = material_code.strip()
            unit = uom.strip()
            if not name or not code:
                return None
            if unit:
                payload = f"Material Name: {name}\nMaterial Code: {code}\nUOM: {unit}"
            else:
                payload = f"Material Name: {name}\nMaterial Code: {code}"
        else:
            payload = material_name.strip()
            if not payload:
                return None

        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=4
            )
            qr.add_data(payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            return img.convert("RGBA")
        except Exception as exc:
            logger.error(f"Failed to generate QR code: {exc}")
            return None

    @classmethod
    def generate_qr_label_preview(
        cls,
        material_name: str,
        material_code: str,
        company_name: str = "",
        uom: str = ""
    ) -> Optional[Image.Image]:
        """
        Render a factory warehouse label card featuring company name,
        Material Name, Material Code, UOM, and a centered QR code encoding fields.
        All elements fit inside the card borders without clipping.
        """
        name = material_name.strip()
        code = material_code.strip()
        unit = uom.strip()
        if not name or not code:
            return None

        if not company_name:
            company_name = SettingsService.get_setting("company_name", "Apex Industrial Manufacturing")

        qr_img = cls.generate_qr_code_image(name, code, uom=unit)
        if not qr_img:
            return None

        card_w, card_h = 480, 280
        card = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 255))
        draw = ImageDraw.Draw(card)

        # 1. Complete card border (unclipped)
        draw.rounded_rectangle([2, 2, card_w - 3, card_h - 3], radius=10, outline="#94a3b8", width=2)

        # 2. Header banner (Company name)
        draw.rounded_rectangle([2, 2, card_w - 3, 38], radius=8, fill="#1e293b")
        draw.text((16, 11), company_name.upper(), fill="#f8fafc")

        # 3. Material Code, UOM, and Name labels
        code_text = f"Material Code: {code}"
        if unit:
            code_text += f"    |    UOM: {unit}"
        draw.text((16, 48), code_text, fill="#0f172a")
        display_name = name[:42] + "..." if len(name) > 42 else name
        draw.text((16, 68), f"Material Name: {display_name}", fill="#475569")

        # 4. Subtle separator line
        draw.line([(14, 92), (card_w - 14, 92)], fill="#e2e8f0", width=1)

        # 5. QR Code image centered with quiet zones
        target_size = 144
        scaled_qr = qr_img.resize((target_size, target_size), Image.Resampling.NEAREST)
        qx = (card_w - target_size) // 2
        qy = 104
        card.paste(scaled_qr, (qx, qy), scaled_qr)

        return card

    @classmethod
    def save_qr_label_as_image(cls, target_path: str, material_name: str, material_code: str, uom: str = "") -> bool:
        """Save a generated QR label to a PNG image file."""
        try:
            img = cls.generate_qr_label_preview(material_name, material_code, uom=uom)
            if img:
                img.save(target_path)
                logger.info(f"Saved QR label image to: {target_path}")
                return True
        except Exception as exc:
            logger.error(f"Error saving QR label image: {exc}")
        return False

    @classmethod
    def export_pdf_qr_sheet(
        cls,
        target_path: str,
        material_name: str,
        material_code: str,
        copies: int = 12,
        uom: str = ""
    ) -> bool:
        """Export printable A4 PDF sheet containing multiple QR labels."""
        temp_img_path = Path(target_path).parent / f"temp_qr_{material_code}.png"
        try:
            label_img = cls.generate_qr_label_preview(material_name, material_code, uom=uom)
            if not label_img:
                return False
            label_img.save(str(temp_img_path), format="PNG")

            pdf = canvas.Canvas(target_path, pagesize=A4)
            page_w, page_h = A4

            cols = 3
            rows = 6
            lbl_w = 62 * mm
            aspect = label_img.size[1] / float(label_img.size[0])
            lbl_h = lbl_w * aspect

            margin_x = (page_w - (cols * lbl_w)) / (cols + 1)
            margin_y = (page_h - (rows * lbl_h)) / (rows + 1)

            copies_left = copies
            while copies_left > 0:
                for r in range(rows - 1, -1, -1):
                    for c in range(cols):
                        if copies_left <= 0:
                            break
                        x = margin_x + c * (lbl_w + margin_x)
                        y = margin_y + r * (lbl_h + margin_y)
                        pdf.drawImage(str(temp_img_path), x, y, width=lbl_w, height=lbl_h)
                        copies_left -= 1
                if copies_left > 0:
                    pdf.showPage()

            pdf.save()
            logger.info(f"Exported printable QR PDF sheet ({copies} labels) to: {target_path}")
            return True
        except Exception as exc:
            logger.error(f"Failed to export QR PDF: {exc}")
            return False
        finally:
            if temp_img_path.exists():
                try:
                    temp_img_path.unlink()
                except Exception:
                    pass

    @classmethod
    def decode_label_image(cls, image: Image.Image) -> Optional[str]:
        """Decode barcode from a generated image using zxing-cpp."""
        try:
            result = zxingcpp.read_barcode(image)
            if result and result.text:
                return result.text
        except Exception as exc:
            logger.error(f"Error decoding barcode image: {exc}")
        return None

    @classmethod
    def save_label_as_image(cls, target_path: str, material_code: str, material_name: str, barcode_text: str) -> bool:
        """Save a generated label to a PNG/JPEG file."""
        try:
            img = cls.generate_label_preview(material_code, material_name, barcode_text)
            if img:
                img.save(target_path)
                logger.info(f"Saved barcode label image to: {target_path}")
                return True
        except Exception as exc:
            logger.error(f"Error saving label image: {exc}")
        return False

    @classmethod
    def export_pdf_label_sheet(
        cls,
        target_path: str,
        material_code: str,
        material_name: str,
        barcode_text: str,
        copies: int = 12
    ) -> bool:
        """
        Generate a multi-label printable A4 sheet using ReportLab,
        preserving exact aspect ratio and margins.
        """
        temp_img_path = Path(target_path).parent / f"temp_lbl_{barcode_text}.png"
        try:
            label_img = cls.generate_label_preview(material_code, material_name, barcode_text)
            if not label_img:
                return False
            label_img.save(str(temp_img_path), format="PNG")

            pdf = canvas.Canvas(target_path, pagesize=A4)
            page_w, page_h = A4

            cols = 3
            rows = 6
            lbl_w = 62 * mm
            # Maintain label aspect ratio (card_h / card_w)
            aspect = label_img.size[1] / float(label_img.size[0])
            lbl_h = lbl_w * aspect

            margin_x = (page_w - (cols * lbl_w)) / (cols + 1)
            margin_y = (page_h - (rows * lbl_h)) / (rows + 1)

            copies_left = copies
            while copies_left > 0:
                for r in range(rows - 1, -1, -1):
                    for c in range(cols):
                        if copies_left <= 0:
                            break
                        x = margin_x + c * (lbl_w + margin_x)
                        y = margin_y + r * (lbl_h + margin_y)
                        pdf.drawImage(str(temp_img_path), x, y, width=lbl_w, height=lbl_h)
                        copies_left -= 1
                if copies_left > 0:
                    pdf.showPage()

            pdf.save()
            logger.info(f"Exported printable PDF sheet ({copies} labels) to: {target_path}")
            return True
        except Exception as exc:
            logger.error(f"Failed to export barcode PDF: {exc}")
            return False
        finally:
            if temp_img_path.exists():
                try:
                    temp_img_path.unlink()
                except Exception:
                    pass

    @staticmethod
    def assign_barcode_to_material(material_id: int, new_barcode: str) -> tuple[bool, str]:
        """Validate uniqueness and update the barcode on an existing material."""
        clean_barcode = new_barcode.strip()
        if not clean_barcode:
            return False, "Barcode text cannot be empty."

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, material_code FROM materials
                    WHERE barcode = ? AND id != ? COLLATE NOCASE;
                """, (clean_barcode, material_id))
                conflict = cursor.fetchone()
                if conflict:
                    return False, f"Barcode '{clean_barcode}' is already assigned to material '{conflict['material_code']}'."

                cursor.execute("""
                    UPDATE materials
                    SET barcode = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                """, (clean_barcode, material_id))
                return True, f"Barcode '{clean_barcode}' assigned successfully."
        except Exception as exc:
            return False, f"Database error: {exc}"

    @classmethod
    def get_plant_catalog(cls, force_reload: bool = False) -> list[dict]:
        """
        Load all factory materials with Material Code, Material Name, UOM and QR details.
        Loads from data/plant_qr_catalog.json (1,734 materials across 73 pages).
        """
        if cls._catalog_cache is not None and not force_reload:
            return cls._catalog_cache

        catalog_paths = [
            DATA_DIR / "plant_qr_catalog.json",
            BASE_DIR / "data" / "plant_qr_catalog.json",
            Path(__file__).resolve().parent.parent.parent / "data" / "plant_qr_catalog.json",
        ]

        for p in catalog_paths:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        cls._catalog_cache = json.load(f)
                        logger.info(f"Loaded {len(cls._catalog_cache)} plant QR catalog items from: {p}")
                        return cls._catalog_cache
                except Exception as exc:
                    logger.error(f"Error reading catalog from {p}: {exc}")

        cls._catalog_cache = []
        return cls._catalog_cache

    @classmethod
    def generate_pure_qr_image(cls, payload: str, box_size: int = 4, border: int = 1) -> Optional[Image.Image]:
        """
        Generate a pure high-contrast black-and-white QR code image encoding payload.
        """
        clean_text = str(payload).strip()
        if not clean_text:
            return None
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=box_size,
                border=border
            )
            qr.add_data(clean_text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            return img.convert("RGBA")
        except Exception as exc:
            logger.error(f"Failed to generate pure QR image for '{clean_text}': {exc}")
            return None

    @classmethod
    def generate_thermal_sticker_image(
        cls,
        material_code: str,
        material_name: str,
        uom: str = "EA",
        label_size: str = "50x25",
        dpi: int = 203
    ) -> Optional[Image.Image]:
        """
        Generate a ready-to-print thermal sticker label image formatted for thermal sticker printers.
        Common factory sizes:
          - '50x25': 50mm x 25mm (Standard Industrial Thermal Sticker roll, 400x200 px at 203 DPI)
          - '50x50': 50mm x 50mm (Square Sticker, 400x400 px at 203 DPI)
          - '75x50': 75mm x 50mm (Medium Box / Bin Sticker, 600x400 px at 203 DPI)
          - '100x50': 100mm x 50mm (Large Pallet / Warehouse Sticker, 800x400 px at 203 DPI)
        """
        code = str(material_code).strip()
        name = str(material_name).strip()
        unit = str(uom).strip() or "EA"
        if not code:
            return None

        # 203 DPI corresponds to ~8 dots per mm (standard 203 DPI thermal label printer)
        dpmm = dpi / 25.4
        size_configs = {
            "50x25": (int(50 * dpmm), int(25 * dpmm)),
            "50x50": (int(50 * dpmm), int(50 * dpmm)),
            "75x50": (int(75 * dpmm), int(50 * dpmm)),
            "100x50": (int(100 * dpmm), int(50 * dpmm)),
        }
        w, h = size_configs.get(label_size, size_configs["50x25"])

        card = Image.new("RGBA", (w, h), (255, 255, 255, 255))
        draw = ImageDraw.Draw(card)

        # Subtle clean outer boundary for thermal alignment
        draw.rectangle([1, 1, w - 2, h - 2], outline="#e2e8f0", width=1)

        qr_img = cls.generate_pure_qr_image(code, box_size=4, border=1)
        if not qr_img:
            return None

        if label_size == "50x25":
            # 50mm x 25mm: Left QR Code, Right Text (Code, Name, UOM)
            qr_size = min(h - 20, int(w * 0.42))
            scaled_qr = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)
            card.paste(scaled_qr, (14, (h - qr_size) // 2), scaled_qr)

            tx = qr_size + 24
            # 1. Material Code (Bold, Prominent)
            draw.text((tx, 14), code[:22], fill="#0f172a")
            draw.line([(tx, 38), (w - 14, 38)], fill="#cbd5e1", width=1)

            # 2. Material Name (Wrapped up to 2 lines)
            max_chars = max(18, int((w - tx - 14) / 7.5))
            line1 = name[:max_chars]
            line2 = name[max_chars:max_chars * 2] if len(name) > max_chars else ""
            if len(name) > max_chars * 2:
                line2 = line2[:max_chars - 3] + "..."
            draw.text((tx, 44), line1, fill="#334155")
            if line2:
                draw.text((tx, 66), line2, fill="#334155")

            # 3. UOM
            draw.text((tx, h - 36), f"UOM: {unit}", fill="#0f172a")

        elif label_size == "50x50":
            # 50mm x 50mm: Top Centered QR Code, Bottom Text
            qr_size = min(int(h * 0.58), int(w * 0.70))
            scaled_qr = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)
            card.paste(scaled_qr, ((w - qr_size) // 2, 14), scaled_qr)

            ty = qr_size + 24
            draw.text((16, ty), f"CODE: {code}", fill="#0f172a")
            draw.line([(14, ty + 22), (w - 14, ty + 22)], fill="#cbd5e1", width=1)
            draw.text((16, ty + 28), name[:32], fill="#334155")
            draw.text((16, ty + 50), f"UOM: {unit}", fill="#0f172a")

        else:
            # 75x50 or 100x50: Wide layout
            qr_size = min(h - 30, int(w * 0.38))
            scaled_qr = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)
            card.paste(scaled_qr, (20, (h - qr_size) // 2), scaled_qr)

            tx = qr_size + 35
            draw.text((tx, 20), f"CODE: {code}", fill="#0f172a")
            draw.line([(tx, 50), (w - 20, 50)], fill="#cbd5e1", width=1)
            draw.text((tx, 60), name[:40], fill="#334155")
            if len(name) > 40:
                draw.text((tx, 85), name[40:80], fill="#334155")
            draw.text((tx, h - 45), f"UOM: {unit}", fill="#0f172a")

        return card

    @classmethod
    def export_catalog_to_excel(
        cls,
        target_path: str,
        items: Optional[list[dict]] = None
    ) -> bool:
        """
        Export catalog to Excel (.xlsx) matching user image:
        Columns: Material Code | Material Name | UOM | QR Code
        Header styled with Dark Blue #1B365D, white bold text, row borders,
        and embedded high-contrast QR code images in Column D!
        """
        if items is None:
            items = cls.get_plant_catalog()
        if not items:
            logger.warning("No items to export to Excel.")
            return False

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Plant QR Codes"
            ws.views.sheetView[0].showGridLines = True

            # 1. Header Styling (matching reference Excel image)
            headers = ["Material Code", "Material Name", "UOM", "QR Code"]
            ws.append(headers)

            hdr_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
            hdr_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
            hdr_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

            thin_border_side = Side(border_style="thin", color="CBD5E1")
            grid_border = Border(
                left=thin_border_side,
                right=thin_border_side,
                top=thin_border_side,
                bottom=thin_border_side
            )

            ws.row_dimensions[1].height = 28
            for col_num in range(1, 5):
                cell = ws.cell(row=1, column=col_num)
                cell.fill = hdr_fill
                cell.font = hdr_font
                cell.alignment = hdr_align
                cell.border = grid_border

            # Column dimensions
            ws.column_dimensions["A"].width = 24
            ws.column_dimensions["B"].width = 50
            ws.column_dimensions["C"].width = 12
            ws.column_dimensions["D"].width = 16

            data_font = Font(name="Segoe UI", size=10)
            code_font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
            align_center = Alignment(horizontal="center", vertical="center")
            align_left = Alignment(horizontal="left", vertical="center")

            # 2. Append rows with embedded QR images
            for idx, item in enumerate(items, start=2):
                code = str(item.get("material_code", ""))
                name = str(item.get("material_name", ""))
                uom = str(item.get("uom", ""))

                ws.append([code, name, uom, ""])
                ws.row_dimensions[idx].height = 55

                c_code = ws.cell(row=idx, column=1)
                c_code.font = code_font
                c_code.alignment = align_left
                c_code.border = grid_border

                c_name = ws.cell(row=idx, column=2)
                c_name.font = data_font
                c_name.alignment = align_left
                c_name.border = grid_border

                c_uom = ws.cell(row=idx, column=3)
                c_uom.font = data_font
                c_uom.alignment = align_center
                c_uom.border = grid_border

                c_qr = ws.cell(row=idx, column=4)
                c_qr.border = grid_border
                c_qr.alignment = align_center

                # Generate QR image and embed into cell D
                qr_img = cls.generate_pure_qr_image(code, box_size=3, border=1)
                if qr_img:
                    bio = io.BytesIO()
                    qr_img.save(bio, format="PNG")
                    bio.seek(0)
                    xl_img = XLImage(bio)
                    xl_img.width = 62
                    xl_img.height = 62
                    ws.add_image(xl_img, f"D{idx}")

            Path(target_path).parent.mkdir(parents=True, exist_ok=True)
            wb.save(target_path)
            logger.info(f"Exported {len(items)} items to Excel with QR images: {target_path}")
            return True
        except Exception as exc:
            logger.error(f"Failed to export catalog Excel: {exc}")
            return False

    @classmethod
    def export_sticker_printer_pdf(
        cls,
        target_path: str,
        items: list[dict],
        label_size: str = "50x25",
        copies_per_item: int = 1
    ) -> bool:
        """
        Export printable PDF ready for sticker printer.
        Formats:
          - '50x25': 50mm x 25mm page size (continuous roll for thermal label printer)
          - '50x50': 50mm x 50mm page size
          - 'a4_sheet': A4 page size with 24 labels (3x8 grid), replicating the plant PDF.
        """
        if not items:
            return False

        try:
            temp_dir = Path(target_path).parent / "temp_stickers"
            temp_dir.mkdir(parents=True, exist_ok=True)

            if label_size in ["50x25", "50x50", "75x50", "100x50"]:
                dims = {
                    "50x25": (50 * mm, 25 * mm),
                    "50x50": (50 * mm, 50 * mm),
                    "75x50": (75 * mm, 50 * mm),
                    "100x50": (100 * mm, 50 * mm),
                }
                pw, ph = dims.get(label_size, dims["50x25"])
                pdf = canvas.Canvas(target_path, pagesize=(pw, ph))

                for item in items:
                    code = item.get("material_code", "")
                    name = item.get("material_name", "")
                    uom = item.get("uom", "EA")

                    lbl_img = cls.generate_thermal_sticker_image(code, name, uom=uom, label_size=label_size)
                    if not lbl_img:
                        continue

                    temp_img = temp_dir / f"lbl_{code}.png"
                    lbl_img.save(str(temp_img), format="PNG")

                    for _ in range(max(1, copies_per_item)):
                        pdf.drawImage(str(temp_img), 0, 0, width=pw, height=ph)
                        pdf.showPage()

                    if temp_img.exists():
                        try:
                            temp_img.unlink()
                        except Exception:
                            pass

                pdf.save()
                logger.info(f"Exported thermal sticker PDF to: {target_path}")
                return True

            elif label_size == "a4_sheet":
                # A4 sheet with 24 stickers (3 cols x 8 rows, exactly like the 73-page plant PDF)
                pdf = canvas.Canvas(target_path, pagesize=A4)
                page_w, page_h = A4
                cols, rows = 3, 8
                lbl_w = 58 * mm
                lbl_h = 32 * mm
                margin_x = (page_w - (cols * lbl_w)) / (cols + 1)
                margin_y = (page_h - (rows * lbl_h)) / (rows + 1)

                col_idx = 0
                row_idx = rows - 1

                for item in items:
                    code = item.get("material_code", "")
                    name = item.get("material_name", "")
                    uom = item.get("uom", "EA")

                    lbl_img = cls.generate_thermal_sticker_image(code, name, uom=uom, label_size="50x25")
                    if not lbl_img:
                        continue

                    temp_img = temp_dir / f"lbl_a4_{code}.png"
                    lbl_img.save(str(temp_img), format="PNG")

                    for _ in range(max(1, copies_per_item)):
                        x = margin_x + col_idx * (lbl_w + margin_x)
                        y = margin_y + row_idx * (lbl_h + margin_y)
                        pdf.drawImage(str(temp_img), x, y, width=lbl_w, height=lbl_h)

                        col_idx += 1
                        if col_idx >= cols:
                            col_idx = 0
                            row_idx -= 1
                            if row_idx < 0:
                                pdf.showPage()
                                row_idx = rows - 1

                    if temp_img.exists():
                        try:
                            temp_img.unlink()
                        except Exception:
                            pass

                if col_idx != 0 or row_idx != rows - 1:
                    pdf.showPage()

                pdf.save()
                logger.info(f"Exported A4 sheet sticker PDF to: {target_path}")
                return True

        except Exception as exc:
            logger.error(f"Failed to export sticker printer PDF: {exc}")
            return False
        finally:
            if temp_dir.exists():
                try:
                    for f in temp_dir.glob("*.png"):
                        f.unlink()
                    temp_dir.rmdir()
                except Exception:
                    pass
        return False


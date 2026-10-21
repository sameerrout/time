import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

from app.core.config import DATA_DIR, ICONS_DIR
from app.core.logger import get_logger
from app.services.settings_service import SettingsService

logger = get_logger("IssueSlipApp.IssueSlipPdfService")


class IssueSlipPdfService:
    @classmethod
    def generate_issue_slip_pdf(cls, slip_data: dict, items: list[dict], target_path: str) -> bool:
        """
        Generate an exact vector A4 portrait PDF document matching the TIME TECHNOPLAST LTD.
        company paper issue slip template with selectable text, logos, reference box,
        two-column header fields, 8-column bordered material table, and signature sections.
        """
        try:
            doc = SimpleDocTemplate(
                target_path,
                pagesize=A4,
                leftMargin=10 * mm,
                rightMargin=10 * mm,
                topMargin=10 * mm,
                bottomMargin=10 * mm
            )

            # Usable width on A4 with 10mm margins = 210 - 20 = 190mm
            page_w = 190 * mm
            elements = []

            company_name = SettingsService.get_setting("company_name", "TIME TECHNOPLAST LTD.")
            company_address = SettingsService.get_setting(
                "company_address",
                "Survey No. 787/3 & 4, (V) Kishtapur, Near Ravalkol Chaurastha,\nShameerpet Road, Medchal Mdl. & Dist. Hyderabad - 501 401 T.S"
            )
            ref_no = SettingsService.get_setting("ref_no", "Ref. No. TTL-HYD/SPIF-09")
            rev_date = SettingsService.get_setting("rev_date", "Rev & Date. 02/01.04.2024")

            # Styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CompanyTitle',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=14,
                leading=16,
                alignment=1
            )
            addr_style = ParagraphStyle(
                'CompanyAddr',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=7.5,
                leading=9.5,
                alignment=1
            )
            ref_style = ParagraphStyle(
                'RefText',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=7,
                leading=9,
                alignment=0
            )

            # 1. Header Layout Table (Logo, Title/Address, Ref Box)
            logo_path = ICONS_DIR / "company_logo.png"
            if logo_path.exists():
                logo_elem = RLImage(str(logo_path), width=32 * mm, height=14 * mm)
            else:
                logo_elem = Paragraph("<b>TIME</b>", title_style)

            center_header = [
                Paragraph(company_name, title_style),
                Spacer(1, 1 * mm),
                Paragraph(company_address.replace("\n", "<br/>"), addr_style)
            ]

            ref_box = [
                Paragraph(ref_no, ref_style),
                Spacer(1, 1 * mm),
                Paragraph(rev_date, ref_style)
            ]

            header_data = [[logo_elem, center_header, ref_box]]
            header_table = Table(header_data, colWidths=[36 * mm, 114 * mm, 40 * mm])
            header_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),
                ('ALIGN', (2, 0), (2, 0), 'LEFT'),
                ('BOX', (2, 0), (2, 0), 0.75, colors.black),
                ('TOPPADDING', (2, 0), (2, 0), 4),
                ('BOTTOMPADDING', (2, 0), (2, 0), 4),
                ('LEFTPADDING', (2, 0), (2, 0), 4),
                ('RIGHTPADDING', (2, 0), (2, 0), 4),
            ]))
            elements.append(header_table)
            elements.append(Spacer(1, 2 * mm))

            # 2. Black Banner: ISSUE SLIP
            banner_data = [["ISSUE SLIP"]]
            banner_table = Table(banner_data, colWidths=[page_w], rowHeights=[6.5 * mm])
            banner_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.black),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ]))
            elements.append(banner_table)
            elements.append(Spacer(1, 2.5 * mm))

            # 3. Two-Column Header Metadata Table
            dept = slip_data.get("department", "")
            date_str = slip_data.get("slip_date", "")
            gl_no = slip_data.get("gl_no", "")
            stores_post = slip_data.get("stores_posting_no", "")
            store_date = slip_data.get("store_posting_date", "")
            res_no = slip_data.get("reservation_no", "")
            slip_no = slip_data.get("slip_no", "")

            meta_data = [
                [f"Department Name : {dept}", f"Stores Posting No. : {stores_post}"],
                [f"Date            : {date_str}", f"Store Posting Date : {store_date}"],
                [f"G/L No          : {gl_no}", f"Reservation No.    : {res_no}"],
                ["", f"Issue Slip No.     : {slip_no}"],
            ]

            meta_table = Table(meta_data, colWidths=[95 * mm, 95 * mm])
            meta_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ]))
            elements.append(meta_table)
            elements.append(Spacer(1, 2.5 * mm))

            # 4. Material Table (9 Columns with Cost Center No. between UOM and Required Qty.)
            col_widths = [
                10 * mm,  # Sr. No.
                42 * mm,  # Description
                22 * mm,  # Material Code No.
                12 * mm,  # UOM
                20 * mm,  # Cost Center No.
                15 * mm,  # Required Qty.
                15 * mm,  # Issued Qty.
                28 * mm,  # Purpose
                26 * mm   # Receiver Name
            ]

            tbl_header = [
                "Sr.\nNo.",
                "Description of\nthe Material",
                "Material Code\nNo.",
                "UOM",
                "Cost Center\nNo.",
                "Required\nQty.",
                "Issued\nQty.",
                "Purpose",
                "Receiver\nName"
            ]

            cell_style = ParagraphStyle(
                'CellText',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=7.5,
                leading=9
            )
            hdr_style = ParagraphStyle(
                'HeaderCellText',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=7.5,
                leading=9.5,
                alignment=1
            )

            table_rows = [[Paragraph(h.replace("\n", "<br/>"), hdr_style) for h in tbl_header]]

            # Add actual material items
            for idx, itm in enumerate(items, start=1):
                sr = str(idx)
                desc = itm.get("material_name", "")
                code = itm.get("material_code", "")
                uom = itm.get("unit", "")
                cc_no = itm.get("cost_center_no", slip_data.get("cost_center_no", ""))
                req = f"{float(itm.get('required_qty', itm.get('quantity', 0))):.1f}"
                iss = f"{float(itm.get('quantity_issued', itm.get('quantity', 0))):.1f}"
                purp = itm.get("purpose", slip_data.get("purpose", ""))
                recv = itm.get("receiver_name", slip_data.get("receiver", ""))

                table_rows.append([
                    Paragraph(sr, hdr_style),
                    Paragraph(desc, cell_style),
                    Paragraph(code, cell_style),
                    Paragraph(uom, hdr_style),
                    Paragraph(cc_no, cell_style),
                    Paragraph(req, hdr_style),
                    Paragraph(iss, hdr_style),
                    Paragraph(purp, cell_style),
                    Paragraph(recv, cell_style)
                ])

            # Pad with empty rows to preserve paper template height (minimum 10 rows)
            min_rows = 10
            while len(table_rows) - 1 < min_rows:
                table_rows.append(["", "", "", "", "", "", "", "", ""])

            mat_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
            mat_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.75, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ]))
            elements.append(mat_table)
            elements.append(Spacer(1, 10 * mm))

            # 5. Signatures Section at bottom
            sig_data = [
                ["___________________________", "___________________________", "___________________________"],
                ["Authorised by", "Store Keeper", "Store (HOD)"]
            ]
            sig_table = Table(sig_data, colWidths=[63 * mm, 64 * mm, 63 * mm])
            sig_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 1), (-1, 1), 9),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            elements.append(KeepTogether(sig_table))

            # Background canvas decorator to draw the thin black outer border
            def draw_outer_border(canvas_obj, document_obj):
                canvas_obj.saveState()
                canvas_obj.setStrokeColor(colors.black)
                canvas_obj.setLineWidth(1.0)
                # Draw outer border 6mm from page boundaries
                canvas_obj.rect(6 * mm, 6 * mm, 198 * mm, 285 * mm)
                canvas_obj.restoreState()

            doc.build(elements, onFirstPage=draw_outer_border, onLaterPages=draw_outer_border)
            logger.info(f"Generated Issue Slip PDF matching paper template: {target_path}")
            return True

        except Exception as exc:
            logger.error(f"Failed to generate Issue Slip PDF: {exc}", exc_info=True)
            return False

import os
import json
from pathlib import Path
import pdfplumber

def extract_catalog():
    pdf_path = Path(r"C:/Users/samee/.gemini/antigravity-ide/brain/2b325952-abca-43fd-b45b-26a0e37dbb2b/.user_uploaded/media_1792526716265.pdf")
    if not pdf_path.exists():
        print(f"Error: {pdf_path} not found")
        return []

    known_uoms = {
        'EA', 'M', 'KG', 'PAC', 'PC', 'L', 'SET', 'PAA', 'CAR', 'BT',
        'BAG', 'FT', 'FT2', 'M2', 'ML', 'MM', 'ROL', 'EML', '"'
    }

    catalog = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, p in enumerate(pdf.pages):
            rects = sorted(p.rects, key=lambda r: (round(r['top'], 1), round(r['x0'], 1)))
            for r in rects:
                cropped = p.crop((r['x0'], r['top'], r['x1'], r['bottom']))
                text = cropped.extract_text()
                if not text:
                    continue
                lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
                if not lines:
                    continue
                code = lines[0]
                name_uom = lines[1] if len(lines) >= 2 else ""

                words = cropped.extract_words()
                bottom_words = [w for w in words if w['top'] > (r['top'] + r['bottom']) / 2]
                
                uom = "EA"
                name = name_uom
                if bottom_words:
                    last_w = max(bottom_words, key=lambda w: w['x1'])
                    cand_uom = last_w['text'].strip()
                    # Check if the rightmost token is a known UOM or placed far right
                    # Col width is ~177px, right edge of cell is ~177px from x0
                    # If last_w['x1'] is close to r['x1'] (within 20px)
                    if cand_uom in known_uoms or (r['x1'] - last_w['x1'] < 20 and len(cand_uom) <= 4):
                        uom = cand_uom
                        if name_uom.endswith(uom):
                            name = name_uom[:-len(uom)].strip()
                        else:
                            parts = name_uom.rsplit(None, 1)
                            name = parts[0]
                    else:
                        parts = name_uom.rsplit(None, 1)
                        if len(parts) > 1 and parts[1] in known_uoms:
                            name = parts[0]
                            uom = parts[1]
                else:
                    parts = name_uom.rsplit(None, 1)
                    if len(parts) > 1 and parts[1] in known_uoms:
                        name = parts[0]
                        uom = parts[1]

                # Special fix for SQUIZEE V TYPE "
                if uom == '"':
                    uom = "EA"

                catalog.append({
                    "s_no": len(catalog) + 1,
                    "page": page_num + 1,
                    "material_code": code,
                    "material_name": name,
                    "uom": uom
                })

    out_file = Path("data/plant_qr_catalog.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"Extracted {len(catalog)} materials to {out_file}")
    return catalog

if __name__ == "__main__":
    extract_catalog()

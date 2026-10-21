import os
import json
import sqlite3
from pathlib import Path
import pdfplumber

from app.core.config import DB_FILE, DATA_DIR
from app.core.database import initialize_database, get_db_connection

def import_inventory():
    pdf_path = Path(r"C:/Users/samee/.gemini/antigravity-ide/brain/2b325952-abca-43fd-b45b-26a0e37dbb2b/.user_uploaded/media_1792530077407.pdf")
    if not pdf_path.exists():
        print(f"Error: {pdf_path} not found.")
        return

    # Ensure database schema is initialized and migrated
    initialize_database()

    materials_list = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, p in enumerate(pdf.pages):
            tables = p.extract_tables()
            if not tables:
                continue
            for row in tables[0][1:]:
                # ['S No', 'Material Code', 'Material Name', 'UOM', 'Opening Stock', 'Received Stock', 'Issued Stock', 'Closing Stock']
                if row and row[0] and row[0].strip().isdigit():
                    s_no = int(row[0].strip())
                    code = row[1].strip()
                    name = row[2].strip()
                    uom = row[3].strip()
                    opening = float(row[4].strip() or 0.0)
                    received = float(row[5].strip() or 0.0)
                    issued = float(row[6].strip() or 0.0)
                    closing = float(row[7].strip() or 0.0)

                    materials_list.append({
                        "s_no": s_no,
                        "material_code": code,
                        "material_name": name,
                        "uom": uom,
                        "opening_stock": opening,
                        "received_stock": received,
                        "issued_stock": issued,
                        "closing_stock": closing
                    })

    print(f"Parsed {len(materials_list)} materials from PDF.")

    # Save to JSON backup in data/
    json_path = DATA_DIR / "plant_inventory_master.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(materials_list, f, indent=2, ensure_ascii=False)
    print(f"Saved inventory json to: {json_path}")

    # Insert into database
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Insert or update each material
        for item in materials_list:
            cur.execute("""
                INSERT INTO materials (
                    material_code,
                    name,
                    category,
                    unit,
                    barcode,
                    opening_stock,
                    received_stock,
                    issued_stock,
                    current_stock,
                    unit_price,
                    min_stock,
                    is_active
                ) VALUES (?, ?, 'Plant Materials', ?, ?, ?, ?, ?, ?, 0.0, 0.0, 1)
                ON CONFLICT(material_code) DO UPDATE SET
                    name = excluded.name,
                    unit = excluded.unit,
                    barcode = excluded.barcode,
                    opening_stock = excluded.opening_stock,
                    received_stock = excluded.received_stock,
                    issued_stock = excluded.issued_stock,
                    current_stock = excluded.current_stock;
            """, (
                item["material_code"],
                item["material_name"],
                item["uom"],
                item["material_code"],
                item["opening_stock"],
                item["received_stock"],
                item["issued_stock"],
                item["closing_stock"]
            ))

        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM materials;")
        count = cur.fetchone()[0]
        print(f"Successfully loaded {count} materials into SQLite database ({DB_FILE})!")

if __name__ == "__main__":
    import_inventory()

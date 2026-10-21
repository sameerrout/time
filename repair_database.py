"""
Repair tool for data damaged by the OLD test-suite.

Why it exists
-------------
Before the fix, running the tests executed `DELETE FROM materials` (and similar) on the REAL
database and left behind fake devices / scan events / inward purchases. This script:

  1. makes a safe backup of the database,
  2. removes the leftover TEST records (fake devices, their scan events, fake inward receipts
     made by 'Gate Phone 2' and the matching ledger rows),
  3. restores any materials that are missing from data/plant_inventory_master.json
     (existing materials and their current stock are NEVER overwritten).

Usage (from the project folder):
    python repair_database.py            # dry run - only shows what it WOULD do
    python repair_database.py --apply    # really do it (backup is created first)
"""
import argparse
import datetime
import json
import sqlite3
import sys
from pathlib import Path

from app.core.config import DB_FILE, DATA_DIR, BACKUPS_DIR

# Only the exact names the OLD tests created (see tests/test_checkpoint8_mobile_scanner.py)
TEST_DEVICE_NAMES = ("Galaxy Tab A", "Test Scanner", "Test Terminal")
TEST_SUPPLIER = "Phone: Gate Phone 2"
TEST_MATERIAL_CODE = "NON_EXISTENT_CODE_9999"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually modify the database (default: dry run)")
    args = ap.parse_args()

    if not Path(DB_FILE).exists():
        print(f"Database not found: {DB_FILE}")
        return 1

    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    q = lambda sql, p=(): cur.execute(sql, p).fetchall()
    marks = ",".join("?" * len(TEST_DEVICE_NAMES))

    test_devices = q(f"SELECT id, name FROM devices WHERE name IN ({marks})", TEST_DEVICE_NAMES)
    dev_ids = [r["id"] for r in test_devices]
    ev_marks = ",".join("?" * len(dev_ids)) or "NULL"
    test_events = q(f"SELECT event_id FROM scan_events WHERE device_id IN ({ev_marks}) OR material_code = ?",
                    (*dev_ids, TEST_MATERIAL_CODE))
    test_receipts = q("SELECT id, receipt_no, material_code, received_stock FROM purchased_materials WHERE supplier = ?",
                      (TEST_SUPPLIER,))
    receipt_nos = [r["receipt_no"] for r in test_receipts]

    missing = []
    master = DATA_DIR / "plant_inventory_master.json"
    if master.exists():
        items = json.loads(master.read_text(encoding="utf-8"))
        have = {r[0] for r in q("SELECT material_code FROM materials")}
        missing = [i for i in items if i["material_code"] not in have]

    print(f"Database: {DB_FILE}")
    print(f"  fake devices to remove          : {len(test_devices)}  {sorted({r['name'] for r in test_devices})}")
    print(f"  fake scan events to remove      : {len(test_events)}")
    print(f"  fake inward receipts to remove  : {len(test_receipts)}")
    print(f"  materials to restore from JSON  : {len(missing)}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to perform the repair.")
        conn.close()
        return 0

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUPS_DIR / f"issue_slip_before_repair_{stamp}.db"
    dst = sqlite3.connect(str(backup))
    conn.backup(dst)
    dst.close()
    print(f"\nBackup written: {backup}")

    cur.execute("PRAGMA foreign_keys = ON;")
    try:
        cur.execute("BEGIN;")
        if test_events:
            cur.executemany("DELETE FROM scan_events WHERE event_id = ?", [(r["event_id"],) for r in test_events])
        if dev_ids:
            cur.executemany("DELETE FROM devices WHERE id = ?", [(i,) for i in dev_ids])
        if receipt_nos:
            cur.executemany("DELETE FROM stock_ledger WHERE reference_no = ?", [(n,) for n in receipt_nos])
            cur.executemany("DELETE FROM purchased_materials WHERE receipt_no = ?", [(n,) for n in receipt_nos])
        for it in missing:
            cur.execute("""
                INSERT INTO materials (material_code, name, category, unit, barcode, opening_stock,
                                       received_stock, issued_stock, current_stock, unit_price, min_stock, is_active)
                VALUES (?, ?, 'Plant Materials', ?, ?, ?, ?, ?, ?, 0.0, 0.0, 1)
                ON CONFLICT(material_code) DO NOTHING;
            """, (it["material_code"], it["material_name"], it["uom"], it["material_code"],
                  it["opening_stock"], it["received_stock"], it["issued_stock"], it["closing_stock"]))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"FAILED, nothing was changed: {exc}")
        conn.close()
        return 1

    total = q("SELECT COUNT(*) FROM materials")[0][0]
    print(f"Repair complete. Materials in database now: {total}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

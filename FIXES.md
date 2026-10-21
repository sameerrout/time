# Fix log (code review, 21 Oct 2026)

## First: repair your database (important)
The old tests ran `DELETE FROM materials` on the REAL database and left fake devices,
scan events and inward receipts behind. The `data/issue_slip.db` in this package is
already repaired (1,734 materials restored from `data/plant_inventory_master.json`).
On another PC / your live folder run:

    python repair_database.py            # dry run, shows what it would do
    python repair_database.py --apply    # backup first, then repair

Note: stock is restored to the values in plant_inventory_master.json. Any real issue/receipt
transactions that the old tests deleted cannot be recovered from this snapshot.

## What was fixed
1. Scan lifecycle - scans are now `pending` until the desktop really uses them, then
   `applied` (added to slip / inward posted) or `rejected` (with reason). The phone shows
   "sent" and updates itself. Rejected scans are no longer retried forever.
   Retried (duplicate) scans are no longer forwarded to the desktop twice (double quantity).
2. Pairing - code is single-use, uses `secrets`, is burned after 5 wrong attempts.
   Also fixed a freeze (non-reentrant lock) when a new pairing code was generated.
3. `/api/devices` and `/api/devices/{id}/revoke` only work from the desktop PC itself.
4. Tests now run in an isolated temp folder (`ISSUE_SLIP_HOME`), never on real data.
5. `/api/materials` ETag covers stock + price, cache is `private, no-cache`; phones refresh
   the catalog every 60 s.
6. Scan validation - bad numbers give a clean 400 (was HTTP 500); 0% GST is kept; ISSUE price
   comes from the database; ISSUE beyond stock is rejected unless `allow_negative_stock=1`.
7. `requirements.txt` now lists aiohttp, cryptography, openpyxl.

## Extra bugs found and fixed while testing
- The phone app could not read the material list (server sends an object, app expected an array).
- Phone app turned a chosen 0% GST into 18%.
- Unknown `/api/...` paths now return 404 instead of the HTML page.

## Not changed
Schema-version numbering, blocking SQLite calls in async handlers, the hard-coded paths in
`IssueSlipManager.spec`, and the TLS key in `data/certs` (delete the folder to regenerate).

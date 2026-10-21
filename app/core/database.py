import os
import sqlite3
import datetime
from pathlib import Path
from contextlib import contextmanager
from app.core.config import DB_FILE, DATA_DIR
from app.core.logger import get_logger

logger = get_logger("IssueSlipApp.Database")

CURRENT_SCHEMA_VERSION = 2


def get_connection() -> sqlite3.Connection:
    """Create and return a configured SQLite connection with row factories and pragmas."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE), timeout=10.0)
    conn.row_factory = sqlite3.Row
    
    # Crucial Pragmas for reliability and data integrity
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@contextmanager
def get_db_connection():
    """Context manager for safe database connections with automatic commit/rollback."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Database error during transaction: {exc}", exc_info=True)
        raise
    finally:
        conn.close()


@contextmanager
def get_db_cursor():
    """Context manager yielding a cursor within an active connection."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        yield cursor


def initialize_database():
    """Create required tables and apply incremental schema migrations."""
    logger.info(f"Initializing database at: {DB_FILE}")
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Schema version table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            );
        """)

        # Application settings key-value table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Check existing version
        cursor.execute("SELECT MAX(version) AS current_ver FROM schema_version;")
        row = cursor.fetchone()
        current_ver = row["current_ver"] if row and row["current_ver"] is not None else 0

        # Migration 1: Foundation
        if current_ver < 1:
            logger.info("Applying Schema Version 1 (Core Foundation)...")
            cursor.execute(
                "INSERT INTO schema_version (version, notes) VALUES (1, 'Initial Foundation Schema');"
            )

            default_settings = [
                ("company_name", "Apex Industrial Manufacturing", "general", "Company or organization legal name"),
                ("facility_name", "Plant 1 - Central Warehouse", "general", "Warehouse, store, or facility identifier"),
                ("slip_prefix", "IS-", "operations", "Prefix for generated issue slip numbering"),
                ("require_approval", "0", "workflow", "1 if manager approval is required before stock deduction, else 0"),
                ("allow_negative_stock", "0", "stock", "1 to permit issuing beyond available physical stock, else 0"),
                ("departments", "BM Qc, Pipe Qc, BM production, pipe production, admin HR, BM Dispatch, store", "general", "Comma-separated list of recognized departments"),
                ("currency_symbol", "₹", "general", "Display symbol for material monetary values"),
                ("storekeeper_name", "Default Storekeeper", "operations", "Default active storekeeper name")
            ]

            cursor.executemany("""
                INSERT OR IGNORE INTO app_settings (key, value, category, description)
                VALUES (?, ?, ?, ?);
            """, default_settings)

        # Migration 2: Materials, Issue Slips, and Stock Ledger
        if current_ver < 2:
            logger.info("Applying Schema Version 2 (Materials, Slips & Stock Ledger)...")

            # 1. Materials Master Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT DEFAULT 'General',
                    unit TEXT DEFAULT 'PCS',
                    barcode TEXT UNIQUE NOT NULL,
                    current_stock REAL DEFAULT 0.0,
                    min_stock REAL DEFAULT 0.0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Issue Slips Header Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS issue_slips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slip_no TEXT UNIQUE NOT NULL,
                    slip_date TEXT NOT NULL,
                    department TEXT NOT NULL,
                    requester TEXT,
                    receiver TEXT NOT NULL,
                    purpose TEXT,
                    status TEXT DEFAULT 'FINALIZED',
                    total_items INTEGER DEFAULT 0,
                    remarks TEXT,
                    created_by TEXT DEFAULT 'Storekeeper',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 3. Issue Slip Items Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS issue_slip_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slip_id INTEGER NOT NULL REFERENCES issue_slips(id) ON DELETE CASCADE,
                    material_id INTEGER NOT NULL REFERENCES materials(id),
                    material_code TEXT NOT NULL,
                    material_name TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    quantity_issued REAL NOT NULL
                );
            """)

            # 4. Stock Movement Ledger Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_id INTEGER NOT NULL REFERENCES materials(id),
                    transaction_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    reference_no TEXT,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cursor.execute(
                "INSERT INTO schema_version (version, notes) VALUES (2, 'Materials, Issue Slips and Stock Ledger');"
            )
            logger.info("Schema Version 2 applied successfully.")

        # Migration 3: Issue Slip Paper Template Fields & Draft Support
        cursor.execute("SELECT MAX(version) AS current_ver FROM schema_version;")
        ver_row = cursor.fetchone()
        current_ver = ver_row["current_ver"] if ver_row and ver_row["current_ver"] is not None else 0

        cursor.execute("PRAGMA table_info(issue_slips);")
        slip_cols = [col["name"] for col in cursor.fetchall()]
        if "cost_center_no" not in slip_cols:
            cursor.execute("ALTER TABLE issue_slips ADD COLUMN cost_center_no TEXT DEFAULT '';")
        if "gl_no" not in slip_cols:
            cursor.execute("ALTER TABLE issue_slips ADD COLUMN gl_no TEXT DEFAULT '';")
        if "stores_posting_no" not in slip_cols:
            cursor.execute("ALTER TABLE issue_slips ADD COLUMN stores_posting_no TEXT DEFAULT '';")
        if "store_posting_date" not in slip_cols:
            cursor.execute("ALTER TABLE issue_slips ADD COLUMN store_posting_date TEXT DEFAULT '';")
        if "reservation_no" not in slip_cols:
            cursor.execute("ALTER TABLE issue_slips ADD COLUMN reservation_no TEXT DEFAULT '';")

        cursor.execute("PRAGMA table_info(issue_slip_items);")
        item_cols = [col["name"] for col in cursor.fetchall()]
        if "sr_no" not in item_cols:
            cursor.execute("ALTER TABLE issue_slip_items ADD COLUMN sr_no INTEGER DEFAULT 1;")
        if "required_qty" not in item_cols:
            cursor.execute("ALTER TABLE issue_slip_items ADD COLUMN required_qty REAL DEFAULT 0.0;")
        if "purpose" not in item_cols:
            cursor.execute("ALTER TABLE issue_slip_items ADD COLUMN purpose TEXT DEFAULT '';")
        if "receiver_name" not in item_cols:
            cursor.execute("ALTER TABLE issue_slip_items ADD COLUMN receiver_name TEXT DEFAULT '';")
        if "cost_center_no" not in item_cols:
            cursor.execute("ALTER TABLE issue_slip_items ADD COLUMN cost_center_no TEXT DEFAULT '';")

        template_settings = [
            ("company_address", "Survey No. 787/3 & 4, (V) Kishtapur, Near Ravalkol Chaurastha, Shameerpet Road, Medchal Mdl. & Dist. Hyderabad - 501 401 T.S", "general", "Company Plant Address"),
            ("ref_no", "Ref. No. TTL-HYD/SPIF-09", "general", "Quality Ref Number"),
            ("rev_date", "Rev & Date. 02/01.04.2024", "general", "Revision and Date")
        ]
        for key, val, cat, desc in template_settings:
            cursor.execute("""
                INSERT INTO app_settings (key, value, category, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """, (key, val, cat, desc))

        # Ensure active department options match user specified list
        cursor.execute("""
            INSERT INTO app_settings (key, value, category, description)
            VALUES ('departments', 'BM Qc, Pipe Qc, BM production, pipe production, admin HR, BM Dispatch, store', 'general', 'Comma-separated list of recognized departments')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """)

        # Ensure currency symbol is set to Rupee (₹)
        cursor.execute("""
            INSERT INTO app_settings (key, value, category, description)
            VALUES ('currency_symbol', '₹', 'general', 'Display symbol for material monetary values')
            ON CONFLICT(key) DO UPDATE SET value = '₹' WHERE value IN ('$', '', NULL);
        """)

        # Materials unit_price, opening_stock, received_stock, and issued_stock support
        cursor.execute("PRAGMA table_info(materials);")
        mat_cols = [col["name"] for col in cursor.fetchall()]
        if "unit_price" not in mat_cols:
            cursor.execute("ALTER TABLE materials ADD COLUMN unit_price REAL DEFAULT 0.0;")
        if "opening_stock" not in mat_cols:
            cursor.execute("ALTER TABLE materials ADD COLUMN opening_stock REAL DEFAULT 0.0;")
            cursor.execute("""
                UPDATE materials
                SET opening_stock = COALESCE(
                    (SELECT quantity FROM stock_ledger WHERE stock_ledger.material_id = materials.id AND transaction_type IN ('INITIAL', 'RECEIPT') AND reference_no IN ('INITIAL-OPENING', 'OPENING-BALANCE') LIMIT 1),
                    current_stock
                );
            """)
        if "received_stock" not in mat_cols:
            cursor.execute("ALTER TABLE materials ADD COLUMN received_stock REAL DEFAULT 0.0;")
        if "issued_stock" not in mat_cols:
            cursor.execute("ALTER TABLE materials ADD COLUMN issued_stock REAL DEFAULT 0.0;")
        if "plant" not in mat_cols:
            cursor.execute("ALTER TABLE materials ADD COLUMN plant TEXT DEFAULT '1304 HYDERABAD';")

        # Purchased Materials (Plant Inward Entry) Register Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchased_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_no TEXT NOT NULL,
                material_id INTEGER,
                material_code TEXT NOT NULL,
                material_name TEXT NOT NULL,
                uom TEXT NOT NULL,
                opening_stock REAL DEFAULT 0.0,
                received_stock REAL NOT NULL,
                issued_stock REAL DEFAULT 0.0,
                closing_stock REAL DEFAULT 0.0,
                unit_price REAL DEFAULT 0.0,
                total_price REAL DEFAULT 0.0,
                gst_percent REAL DEFAULT 18.0,
                gst_amount REAL DEFAULT 0.0,
                supplier TEXT DEFAULT '',
                challan_no TEXT DEFAULT '',
                remarks TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(material_id) REFERENCES materials(id)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_purchased_mat_code ON purchased_materials(material_code);")

        # Migrate existing purchased_materials table if missing gst columns or device_name
        cursor.execute("PRAGMA table_info(purchased_materials);")
        p_cols = [col["name"] for col in cursor.fetchall()]
        if "gst_percent" not in p_cols:
            cursor.execute("ALTER TABLE purchased_materials ADD COLUMN gst_percent REAL DEFAULT 18.0;")
        if "gst_amount" not in p_cols:
            cursor.execute("ALTER TABLE purchased_materials ADD COLUMN gst_amount REAL DEFAULT 0.0;")
        if "device_name" not in p_cols:
            cursor.execute("ALTER TABLE purchased_materials ADD COLUMN device_name TEXT DEFAULT '';")

        # Mobile PWA Scanner Tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                revoked INTEGER DEFAULT 0
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scan_events (
                event_id TEXT PRIMARY KEY,
                device_id INTEGER REFERENCES devices(id),
                device_name TEXT DEFAULT '',
                mode TEXT NOT NULL,
                material_code TEXT NOT NULL,
                material_name TEXT DEFAULT '',
                uom TEXT DEFAULT '',
                qty REAL NOT NULL,
                required_qty REAL DEFAULT 0.0,
                unit_price REAL DEFAULT 0.0,
                gst_pct REAL DEFAULT 18.0,
                total_price REAL DEFAULT 0.0,
                purpose TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                reject_reason TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                applied_at TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_events_status ON scan_events(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_events_code ON scan_events(material_code);")

        if current_ver < 3:
            cursor.execute("INSERT INTO schema_version (version, notes) VALUES (3, 'Paper Template Fields and Draft Support');")
            logger.info("Schema Version 3 applied successfully.")


def check_database_integrity() -> tuple[bool, str]:
    """Execute SQLite integrity check pragma to detect data corruption."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
            if result and result[0] == "ok":
                return True, "SQLite database integrity verified (OK)."
            return False, f"Integrity check reported issues: {result[0] if result else 'Unknown'}"
    except Exception as exc:
        return False, f"Failed to perform integrity check: {exc}"


def get_database_stats() -> dict:
    """Retrieve statistical metadata about the SQLite database."""
    stats = {
        "exists": DB_FILE.exists(),
        "path": str(DB_FILE),
        "size_kb": 0.0,
        "table_count": 0,
        "schema_version": 0,
        "journal_mode": "UNKNOWN"
    }

    if DB_FILE.exists():
        try:
            stats["size_kb"] = round(DB_FILE.stat().st_size / 1024, 2)
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table';")
                stats["table_count"] = cursor.fetchone()[0]

                cursor.execute("SELECT MAX(version) FROM schema_version;")
                ver_row = cursor.fetchone()
                stats["schema_version"] = ver_row[0] if ver_row and ver_row[0] else 0

                cursor.execute("PRAGMA journal_mode;")
                stats["journal_mode"] = cursor.fetchone()[0].upper()
        except Exception as exc:
            logger.warning(f"Error reading database stats: {exc}")

    return stats

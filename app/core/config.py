import os
import sys
import ctypes
from pathlib import Path

# Application Metadata
APP_NAME = "Issue Slip Manager"
APP_SUBTITLE = "Portable Barcode-Based Warehouse Issue Slip System"
APP_VERSION = "1.0.0"
APP_ID = "FactoryWarehouse.IssueSlipManager.Desktop.1.0"

# Path Resolution for Portable Mode
if getattr(sys, "frozen", False):
    # Running in a PyInstaller bundle; executable directory is the writable home
    BASE_DIR = Path(sys.executable).resolve().parent
    # Bundled read-only resources (icons, default configs) reside in _MEIPASS
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    # Running in live Python source tree
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    RESOURCE_DIR = BASE_DIR

# Writable directories on the host/pendrive.
# ISSUE_SLIP_HOME lets tests (or a custom install) redirect ALL writable data
# (database, certificates, logs, backups) to a different folder. The automated
# test-suite sets it to a temporary folder so tests can never touch real data.
_HOME_OVERRIDE = os.environ.get("ISSUE_SLIP_HOME", "").strip()
_WRITABLE_ROOT = Path(_HOME_OVERRIDE).resolve() if _HOME_OVERRIDE else BASE_DIR
DATA_DIR = _WRITABLE_ROOT / "data"
LOGS_DIR = _WRITABLE_ROOT / "logs"
BACKUPS_DIR = _WRITABLE_ROOT / "backups"
ASSETS_DIR = RESOURCE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"

# Primary database file path
DB_FILE = DATA_DIR / "issue_slip.db"
LOG_FILE = LOGS_DIR / "app.log"
APP_ICON_PNG = ICONS_DIR / "app_icon.png"
APP_ICON_ICO = ICONS_DIR / "app_icon.ico"


def ensure_directories():
    """Ensure all required mutable directories exist on the drive."""
    for directory in [DATA_DIR, LOGS_DIR, BACKUPS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def check_storage_writable() -> tuple[bool, str]:
    """Verify that the target storage location has write permissions."""
    ensure_directories()
    test_file = DATA_DIR / ".write_test"
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test_write")
        if test_file.exists():
            test_file.unlink()
        return True, "Storage directory is fully writable."
    except Exception as exc:
        return False, f"Storage directory is READ-ONLY or inaccessible: {exc}"


def get_drive_info() -> dict:
    """Detect storage drive type (USB Removable, Fixed HDD/SSD, Network, etc.)"""
    drive_str = str(BASE_DIR.anchor)
    info = {
        "drive_letter": drive_str,
        "is_removable": False,
        "drive_type_desc": "Local Fixed Drive",
        "path": str(BASE_DIR),
    }

    try:
        if os.name == "nt":
            # Windows API GetDriveTypeW:
            # 2 = DRIVE_REMOVABLE (USB flash drive / floppy)
            # 3 = DRIVE_FIXED (Local HDD/SSD)
            # 4 = DRIVE_REMOTE (Network drive)
            # 5 = DRIVE_CDROM (CD-ROM)
            # 6 = DRIVE_RAMDISK (RAM disk)
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_str)
            if drive_type == 2:
                info["is_removable"] = True
                info["drive_type_desc"] = "Portable USB / Removable Media"
            elif drive_type == 3:
                info["is_removable"] = False
                info["drive_type_desc"] = "Local Fixed Storage (HDD/SSD)"
            elif drive_type == 4:
                info["is_removable"] = False
                info["drive_type_desc"] = "Network Attached Drive"
            else:
                info["drive_type_desc"] = f"Drive Type Code ({drive_type})"
    except Exception:
        pass

    return info

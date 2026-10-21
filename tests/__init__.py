"""Tests package.

SAFETY: several tests insert / DELETE rows (e.g. ``DELETE FROM materials``) and
regenerate TLS certificates. They must NEVER run against the real database.
This module runs before any test module imports ``app.*`` and redirects every
writable path (data, logs, backups, certs) into a throw-away temp folder.
"""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

_REAL_ROOT = Path(__file__).resolve().parent.parent

if not os.environ.get("ISSUE_SLIP_HOME"):
    _tmp_home = Path(tempfile.mkdtemp(prefix="issue_slip_test_"))
    os.environ["ISSUE_SLIP_HOME"] = str(_tmp_home)
    # Read-only reference data some tests need (catalogs) - copied, never modified.
    (_tmp_home / "data").mkdir(parents=True, exist_ok=True)
    for _name in ("plant_qr_catalog.json", "plant_inventory_master.json"):
        _src = _REAL_ROOT / "data" / _name
        if _src.exists():
            shutil.copy2(_src, _tmp_home / "data" / _name)
    atexit.register(shutil.rmtree, str(_tmp_home), ignore_errors=True)

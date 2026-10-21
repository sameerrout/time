"""Regression tests for the code-review fixes (scan lifecycle, pairing, API, validation)."""
import asyncio
import os
import unittest
import uuid
from types import SimpleNamespace

from aiohttp.test_utils import make_mocked_request

from app.core.config import DATA_DIR
from app.core.database import initialize_database, get_db_connection
from app.server.device_service import DeviceService
from app.server.http_server import LocalServer
from app.server.scan_service import ScanService
from app.services.settings_service import SettingsService

CODE = "REVIEW-FIX-001"


def _pair(name="Review Phone"):
    code = DeviceService.generate_pairing_code()
    ok, msg, token, dev = DeviceService.verify_and_pair(code, name)
    assert ok, msg
    return token, dev


def _set_stock(stock, price=100.0):
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO materials (material_code, name, category, unit, barcode, current_stock, unit_price, is_active)
            VALUES (?, 'Review Fix Material', 'Test', 'EA', ?, ?, ?, 1)
            ON CONFLICT(material_code) DO UPDATE SET current_stock = excluded.current_stock,
                                                     unit_price = excluded.unit_price;
        """, (CODE, CODE, stock, price))


def _status(event_id):
    return ScanService.get_event_status(event_id)


class TestIsolation(unittest.TestCase):
    def test_tests_never_use_real_data_dir(self):
        self.assertTrue(os.environ.get("ISSUE_SLIP_HOME"))
        self.assertIn("issue_slip_test_", str(DATA_DIR))


class TestScanLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        _set_stock(50.0, 100.0)
        _, self.dev = _pair()

    def _scan(self, **kw):
        payload = {"event_id": str(uuid.uuid4()), "mode": "ISSUE", "material_code": CODE, "qty": 5}
        payload.update(kw)
        return payload, ScanService.process_scan(self.dev, payload)

    def test_scan_is_pending_then_applied_once(self):
        payload, (ok, _, res) = self._scan()
        self.assertTrue(ok)
        self.assertEqual(res["status"], "pending")
        self.assertFalse(res["duplicate"])
        self.assertEqual(_status(payload["event_id"])["status"], "pending")

        self.assertTrue(ScanService.mark_event_applied(payload["event_id"]))
        row = _status(payload["event_id"])
        self.assertEqual(row["status"], "applied")
        self.assertIsNotNone(row["applied_at"])
        # already finished -> cannot be flipped again
        self.assertFalse(ScanService.mark_event_rejected(payload["event_id"], "late"))
        self.assertEqual(_status(payload["event_id"])["status"], "applied")

    def test_desktop_rejection_is_recorded_with_reason(self):
        payload, (ok, _, _) = self._scan()
        self.assertTrue(ok)
        self.assertTrue(ScanService.mark_event_rejected(payload["event_id"], "Phone scanning is OFF"))
        row = _status(payload["event_id"])
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row["reject_reason"], "Phone scanning is OFF")

    def test_duplicate_event_is_flagged(self):
        payload, (ok, _, res) = self._scan()
        ok2, _, res2 = ScanService.process_scan(self.dev, payload)
        self.assertTrue(ok2)
        self.assertTrue(res2["duplicate"])

    def test_bad_numbers_are_rejected_cleanly(self):
        for bad in ("abc", "nan", "inf", "-3", 0):
            _, (ok, msg, res) = self._scan(qty=bad)
            self.assertFalse(ok, f"qty={bad!r} must be rejected")
            self.assertEqual(res["status"], "rejected")
        # bad number AND unknown material used to raise ValueError -> HTTP 500
        _, (ok, _, res) = self._scan(material_code="NOPE-123", qty="abc")
        self.assertFalse(ok)
        self.assertEqual(res["status"], "rejected")

    def test_zero_gst_is_respected_and_out_of_range_rejected(self):
        _, (ok, _, res) = self._scan(mode="RECEIVE", qty=10, unit_price=100, gst_pct=0)
        self.assertTrue(ok)
        self.assertEqual(res["gst_pct"], 0.0)
        self.assertEqual(res["total_price"], 1000.0)
        _, (ok, _, _) = self._scan(mode="RECEIVE", qty=10, gst_pct=250)
        self.assertFalse(ok)

    def test_issue_price_comes_from_database_not_phone(self):
        _, (ok, _, res) = self._scan(qty=2, unit_price=1)
        self.assertTrue(ok)
        self.assertEqual(res["unit_price"], 100.0)

    def test_receive_may_carry_phone_price(self):
        _, (ok, _, res) = self._scan(mode="RECEIVE", qty=2, unit_price=80, gst_pct=18)
        self.assertTrue(ok)
        self.assertEqual(res["unit_price"], 80.0)

    def test_issue_beyond_stock_rejected_unless_allowed(self):
        _, (ok, msg, res) = self._scan(qty=51)
        self.assertFalse(ok)
        self.assertIn("Insufficient stock", msg)
        self.assertEqual(res["status"], "rejected")
        # RECEIVE is never blocked by stock
        _, (ok, _, _) = self._scan(mode="RECEIVE", qty=51)
        self.assertTrue(ok)

        original = SettingsService.get_setting("allow_negative_stock", "0")
        SettingsService.set_setting("allow_negative_stock", "1")
        try:
            _, (ok, _, _) = self._scan(qty=51)
            self.assertTrue(ok)
        finally:
            SettingsService.set_setting("allow_negative_stock", original)


class TestPairingSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def test_code_is_single_use(self):
        code = DeviceService.generate_pairing_code()
        ok, *_ = DeviceService.verify_and_pair(code, "First Phone")
        self.assertTrue(ok)
        ok, msg, token, _ = DeviceService.verify_and_pair(code, "Intruder Phone")
        self.assertFalse(ok)
        self.assertIsNone(token)

    def test_brute_force_burns_the_code(self):
        code = DeviceService.generate_pairing_code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(DeviceService.MAX_FAILED_ATTEMPTS):
            ok, *_ = DeviceService.verify_and_pair(wrong, "Guesser")
            self.assertFalse(ok)
        # even the CORRECT code no longer works - desktop must generate a new one
        ok, *_ = DeviceService.verify_and_pair(code, "Guesser")
        self.assertFalse(ok)

    def test_new_code_after_use_does_not_deadlock(self):
        code = DeviceService.generate_pairing_code()
        DeviceService.verify_and_pair(code, "Phone")
        fresh = DeviceService.get_active_pairing_code()  # used to risk a lock deadlock
        self.assertEqual(len(fresh), 6)
        self.assertNotEqual(fresh, code)


class TestHttpHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()
        cls.server = LocalServer()

    def _call(self, handler, method, path, headers=None, remote="127.0.0.1", match_info=None):
        req = make_mocked_request(method, path, headers=headers or {}, match_info=match_info or {})
        # make_mocked_request has no real socket; emulate the peer address
        req = SimpleNamespace(
            headers=req.headers, query=req.query, match_info=req.match_info,
            remote=remote, path=path, method=method, json=req.json,
        )
        return asyncio.run(handler(req))

    def test_device_endpoints_are_desktop_only(self):
        token, dev = _pair("Victim")
        r = self._call(self.server._handle_devices_list, "GET", "/api/devices", remote="192.168.0.50")
        self.assertEqual(r.status, 403)
        r = self._call(self.server._handle_device_revoke, "POST", f"/api/devices/{dev['id']}/revoke",
                       remote="192.168.0.50", match_info={"device_id": str(dev["id"])})
        self.assertEqual(r.status, 403)
        # the forbidden revoke attempt must not have revoked anything
        self.assertIsNotNone(DeviceService.validate_token(token))
        # from the desktop itself it works
        r = self._call(self.server._handle_devices_list, "GET", "/api/devices", remote="127.0.0.1")
        self.assertEqual(r.status, 200)

    def test_materials_etag_changes_when_stock_changes(self):
        token, _ = _pair("Etag Phone")
        hdr = {"Authorization": f"Bearer {token}"}
        _set_stock(10.0)
        r1 = self._call(self.server._handle_materials, "GET", "/api/materials", headers=hdr, remote="192.168.0.9")
        _set_stock(7.0)
        r2 = self._call(self.server._handle_materials, "GET", "/api/materials", headers=hdr, remote="192.168.0.9")
        self.assertEqual(r1.status, 200)
        self.assertNotEqual(r1.headers["ETag"], r2.headers["ETag"])
        self.assertIn("no-cache", r2.headers["Cache-Control"])
        # unchanged data + matching If-None-Match -> 304
        hdr2 = dict(hdr, **{"If-None-Match": r2.headers["ETag"]})
        r3 = self._call(self.server._handle_materials, "GET", "/api/materials", headers=hdr2, remote="192.168.0.9")
        self.assertEqual(r3.status, 304)

    def test_unknown_api_path_is_404(self):
        r = self._call(self.server._handle_fallback, "GET", "/api/does-not-exist")
        self.assertEqual(r.status, 404)


if __name__ == "__main__":
    unittest.main()

"""Unit and integration tests for Remote Listener (127.0.0.1:8444) and Tunnel Manager."""
import asyncio
import io
import json
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from app.core.database import initialize_database, get_db_connection
from app.remote.remote_server import RemoteServer, MAX_BODY_SIZE, PAIRING_LIMIT_PER_MINUTE
from app.remote.tunnel_manager import TunnelManager
from app.server.device_service import DeviceService
from app.server.scan_service import ScanService
from app.services.settings_service import SettingsService

TEST_MAT_CODE = "REMOTE-TEST-MAT-01"


def _seed_material(stock: float = 100.0, price: float = 250.0):
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO materials (
                material_code, name, category, unit, barcode, current_stock, unit_price, is_active, plant
            ) VALUES (?, 'Remote Test Material', 'Test', 'EA', ?, ?, ?, 1, '1304 HYDERABAD')
            ON CONFLICT(material_code) DO UPDATE SET
                current_stock = excluded.current_stock,
                unit_price = excluded.unit_price;
        """, (TEST_MAT_CODE, TEST_MAT_CODE, stock, price))


def _create_paired_device(name: str = "Test Remote Phone"):
    code = DeviceService.generate_pairing_code()
    ok, msg, token, dev = DeviceService.verify_and_pair(code, name)
    assert ok, f"Failed to pair device: {msg}"
    return token, dev


class TestRemoteListener(AioHTTPTestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        super().setUp()
        _seed_material(50.0, 150.0)

    async def get_application(self):
        self.server_obj = RemoteServer(port=8444)
        return self.server_obj.create_app()

    @unittest_run_loop
    async def test_01_exposed_routes_and_lifecycle(self):
        # 1. Health check
        resp = await self.client.request("GET", "/api/health")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("port"), 8444)

        # 2. Pairing with code
        code = DeviceService.generate_pairing_code()
        resp_pair = await self.client.request(
            "POST",
            "/api/pair",
            json={"code": code, "device_name": "Pixel Scanner"}
        )
        self.assertEqual(resp_pair.status, 200)
        pair_data = await resp_pair.json()
        self.assertTrue(pair_data.get("success"))
        token = pair_data.get("token")
        self.assertTrue(bool(token))

        # 3. Materials with ETag
        auth_hdr = {"Authorization": f"Bearer {token}"}
        resp_mat = await self.client.request("GET", "/api/materials", headers=auth_hdr)
        self.assertEqual(resp_mat.status, 200)
        etag = resp_mat.headers.get("ETag")
        self.assertTrue(bool(etag))
        self.assertIn("no-cache", resp_mat.headers.get("Cache-Control", ""))

        # 3b. 304 Not Modified when ETag matches
        resp_mat_cached = await self.client.request(
            "GET",
            "/api/materials",
            headers={**auth_hdr, "If-None-Match": etag}
        )
        self.assertEqual(resp_mat_cached.status, 304)

        # 4. Scan submission (ISSUE mode)
        event_id = str(uuid.uuid4())
        scan_payload = {
            "event_id": event_id,
            "mode": "ISSUE",
            "material_code": TEST_MAT_CODE,
            "qty": 5.0,
            "purpose": "Remote Test Assembly"
        }
        resp_scan = await self.client.request("POST", "/api/scan", headers=auth_hdr, json=scan_payload)
        self.assertEqual(resp_scan.status, 200)
        scan_data = await resp_scan.json()
        self.assertTrue(scan_data.get("success"))
        self.assertEqual(scan_data["data"]["status"], "pending")

        # 5. Scan status polling
        resp_status = await self.client.request("GET", f"/api/scan/{event_id}", headers=auth_hdr)
        self.assertEqual(resp_status.status, 200)
        status_data = await resp_status.json()
        self.assertTrue(status_data.get("success"))
        self.assertEqual(status_data["data"]["event_id"], event_id)
        self.assertIn(status_data["data"]["status"], ("pending", "applied"))

    @unittest_run_loop
    async def test_02_excluded_endpoints_return_404(self):
        """All desktop endpoints, websockets, and static PWA routes must return 404."""
        token, _ = _create_paired_device("Intruder Probe")
        auth_hdr = {"Authorization": f"Bearer {token}"}

        forbidden_routes = [
            ("GET", "/api/devices"),
            ("POST", "/api/devices/1/revoke"),
            ("GET", "/ws"),
            ("GET", "/"),
            ("GET", "/index.html"),
            ("GET", "/sw.js"),
            ("GET", "/manifest.json"),
            ("GET", "/api/stock/1001"),
            ("GET", "/api/unknown-endpoint"),
        ]

        for method, path in forbidden_routes:
            resp = await self.client.request(method, path, headers=auth_hdr)
            self.assertEqual(resp.status, 404, f"Route {method} {path} should return 404 on remote listener")
            body = await resp.json()
            self.assertFalse(body.get("success"))

    @unittest_run_loop
    async def test_03_query_token_ignored_and_revoked_rejected(self):
        token, dev = _create_paired_device("Query Test Device")

        # Case A: Token passed via query string ?token=... is strictly ignored -> 401
        resp_query = await self.client.request("GET", f"/api/materials?token={token}")
        self.assertEqual(resp_query.status, 401, "Query string tokens must be ignored")

        # Case B: Token in Authorization: Bearer succeeds -> 200
        resp_bearer = await self.client.request(
            "GET",
            "/api/materials",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(resp_bearer.status, 200)

        # Case C: Once device is revoked, bearer token is immediately rejected -> 401
        DeviceService.revoke_device(dev["id"])
        resp_revoked = await self.client.request(
            "GET",
            "/api/materials",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(resp_revoked.status, 401, "Revoked device must be rejected immediately")

    @unittest_run_loop
    async def test_04_rate_limiting_enforcement(self):
        # Reset limiter for this test
        self.server_obj.rate_limiter.reset()

        cf_ip = "203.0.113.42"
        headers = {"Cf-Connecting-Ip": cf_ip}

        # 5 pairing requests within 1 minute are allowed
        for i in range(PAIRING_LIMIT_PER_MINUTE):
            resp = await self.client.request(
                "POST",
                "/api/pair",
                headers=headers,
                json={"code": "000000", "device_name": f"Guess {i}"}
            )
            # Response may be 400 (invalid code) but NOT 429
            self.assertNotEqual(resp.status, 429, f"Attempt {i+1} should not be rate-limited")

        # 6th pairing request from same IP must be rate-limited (HTTP 429)
        resp_blocked = await self.client.request(
            "POST",
            "/api/pair",
            headers=headers,
            json={"code": "000000", "device_name": "Exceeded"}
        )
        self.assertEqual(resp_blocked.status, 429, "6th pairing attempt must return 429")
        self.assertTrue(bool(resp_blocked.headers.get("Retry-After")), "Retry-After header must be present")

    @unittest_run_loop
    async def test_05_oversized_payload_rejected(self):
        token, _ = _create_paired_device("Oversize Device")
        # Create payload > 64 KB
        large_purpose = "A" * (MAX_BODY_SIZE + 1024)
        oversized_json = {
            "event_id": str(uuid.uuid4()),
            "mode": "ISSUE",
            "material_code": TEST_MAT_CODE,
            "qty": 1.0,
            "purpose": large_purpose
        }

        resp = await self.client.request(
            "POST",
            "/api/scan",
            headers={"Authorization": f"Bearer {token}"},
            json=oversized_json
        )
        # Should be rejected with 413 Payload Too Large
        self.assertEqual(resp.status, 413, "Payload exceeding 64KB must return 413")


class TestTunnelManager(unittest.TestCase):
    def test_06_url_parsing_from_cloudflared_logs(self):
        sample_logs = [
            (
                "2026-10-21T10:00:00Z INF |  https://orange-mango-banana.trycloudflare.com  |",
                "https://orange-mango-banana.trycloudflare.com"
            ),
            (
                "INF +--------------------------------------------------------------------------------------------+\n"
                "INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |\n"
                "INF |  https://my-quick-tunnel-123.trycloudflare.com                                             |\n"
                "INF +--------------------------------------------------------------------------------------------+",
                "https://my-quick-tunnel-123.trycloudflare.com"
            ),
            (
                "2026-10-21T10:01:00Z ERR Failed to create tunnel: connection reset",
                None
            ),
            (
                "",
                None
            )
        ]

        for log_text, expected_url in sample_logs:
            parsed = TunnelManager.extract_tunnel_url(log_text)
            self.assertEqual(parsed, expected_url, f"Failed parsing: {log_text}")

    def test_07_tunnel_manager_modes_and_lifecycle(self):
        tm = TunnelManager(target_port=8444)

        # Mode: 'off'
        tm.set_mode("off")
        tm.start()
        self.assertEqual(tm.get_mode(), "off")
        self.assertEqual(tm.status, "offline")
        self.assertEqual(tm.get_public_url(), "")

        # Mode: 'custom'
        tm.set_mode("custom", custom_url="https://scanner.acmefactory.com")
        tm.start()
        self.assertEqual(tm.get_mode(), "custom")
        self.assertEqual(tm.status, "online")
        self.assertEqual(tm.get_public_url(), "https://scanner.acmefactory.com")

        # QR payload generation
        code = "482910"
        payload = tm.get_qr_payload(pairing_code=code)
        self.assertEqual(payload["v"], 1)
        self.assertEqual(payload["url"], "https://scanner.acmefactory.com")
        self.assertEqual(payload["code"], "482910")
        self.assertTrue(bool(payload["id"]), "Installation ID must be populated")

        # Installation ID is persistent
        id1 = TunnelManager.get_installation_id()
        id2 = TunnelManager.get_installation_id()
        self.assertEqual(id1, id2, "Installation ID must remain stable across calls")

        # Stop manager
        tm.stop()
        self.assertEqual(tm.status, "offline")

    def test_08_fake_subprocess_lifecycle(self):
        """Test start and stop lifecycle with a mock subprocess to verify clean teardown."""
        tm = TunnelManager(target_port=8444)
        tm.set_mode("tunnel")

        mock_proc = MagicMock()
        def fake_stdout():
            yield "INF | https://test-fake-tunnel.trycloudflare.com |\n"
            # Block until manager calls stop()
            tm._stop_event.wait(timeout=2.0)

        mock_proc.stdout = fake_stdout()
        mock_proc.wait.return_value = 0
        mock_proc.terminate.side_effect = lambda: tm._stop_event.set()

        with patch("subprocess.Popen", return_value=mock_proc), \
             patch.object(TunnelManager, "find_cloudflared_binary", return_value=Path("C:/fake/cloudflared.exe")):
            tm.start()
            import time
            time.sleep(0.2)
            self.assertEqual(tm.status, "online")
            self.assertEqual(tm.get_public_url(), "https://test-fake-tunnel.trycloudflare.com")

            tm.stop()
            self.assertEqual(tm.status, "offline")
            self.assertTrue(mock_proc.terminate.called or mock_proc.kill.called)


if __name__ == "__main__":
    unittest.main()

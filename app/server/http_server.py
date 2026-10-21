import asyncio
import hashlib
import json
import ssl
import threading
from pathlib import Path
from typing import Optional, Set

from aiohttp import web
from PySide6.QtCore import QObject, Signal

from app.core.config import DATA_DIR, RESOURCE_DIR, BASE_DIR
from app.core.logger import get_logger
from app.core.database import get_db_connection
from app.server.cert_manager import ensure_certificate, get_local_ip
from app.server.device_service import DeviceService
from app.server.scan_service import ScanService
from app.services.material_service import MaterialService

logger = get_logger("IssueSlipApp.HttpServer")


class ServerSignals(QObject):
    """Qt signal bridge for thread-safe cross-thread UI notification."""
    scan_received = Signal(dict)
    device_paired = Signal(dict)
    device_revoked = Signal(int)
    server_status = Signal(bool, str)  # (running, url)


# Global singleton signals instance
server_signals = ServerSignals()


class LocalServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8443):
        self.host = host
        self.port = port
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.thread: Optional[threading.Thread] = None
        self._is_running = False
        self._ws_clients: Set[web.WebSocketResponse] = set()

        # Locate PWA directory with fallback for PyInstaller frozen mode
        candidate_paths = [
            Path(__file__).parent / "pwa",
            RESOURCE_DIR / "app" / "server" / "pwa",
            BASE_DIR / "app" / "server" / "pwa"
        ]
        self.pwa_dir = next((p for p in candidate_paths if p.exists()), candidate_paths[0])

    @property
    def is_running(self) -> bool:
        return self._is_running

    def get_server_url(self) -> str:
        lan_ip = get_local_ip()
        return f"https://{lan_ip}:{self.port}"

    def start(self):
        """Start HTTPS server in a background daemon thread."""
        if self._is_running:
            return

        self.thread = threading.Thread(target=self._run_event_loop, daemon=True, name="HttpServerThread")
        self.thread.start()

    def stop(self):
        """Stop HTTPS server gracefully."""
        if not self._is_running or not self.loop:
            return

        async def _cleanup():
            # Close all active web sockets
            for ws in list(self._ws_clients):
                try:
                    await ws.close(code=1000, message=b"Server shutting down")
                except Exception:
                    pass
            self._ws_clients.clear()

            if self.runner:
                await self.runner.cleanup()

        future = asyncio.run_coroutine_threadsafe(_cleanup(), self.loop)
        try:
            future.result(timeout=5)
        except Exception as exc:
            logger.warning(f"Error during server shutdown: {exc}")
        finally:
            self._is_running = False
            server_signals.server_status.emit(False, "")
            logger.info("Local HTTPS server stopped.")

    def _run_event_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start_server_coroutine())
            self.loop.run_forever()
        except Exception as exc:
            logger.error(f"Error in server thread: {exc}", exc_info=True)
            self._is_running = False
            server_signals.server_status.emit(False, "")
        finally:
            self.loop.close()

    async def _start_server_coroutine(self):
        app = web.Application(middlewares=[self._cors_middleware])

        # API Routes
        app.router.add_get("/api/health", self._handle_health)
        app.router.add_post("/api/pair", self._handle_pair)
        app.router.add_get("/api/materials", self._handle_materials)
        app.router.add_get("/api/stock/{code}", self._handle_stock)
        app.router.add_post("/api/scan", self._handle_scan)
        app.router.add_get("/api/scan/{event_id}", self._handle_scan_status)
        app.router.add_get("/api/devices", self._handle_devices_list)
        app.router.add_post("/api/devices/{device_id}/revoke", self._handle_device_revoke)
        app.router.add_get("/ws", self._handle_websocket)

        # Static PWA files
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/index.html", self._handle_index)
        app.router.add_get("/manifest.json", self._handle_manifest)
        app.router.add_get("/sw.js", self._handle_service_worker)

        if (self.pwa_dir / "css").exists():
            app.router.add_static("/css", str(self.pwa_dir / "css"))
        if (self.pwa_dir / "js").exists():
            app.router.add_static("/js", str(self.pwa_dir / "js"))
        if (self.pwa_dir / "icons").exists():
            app.router.add_static("/icons", str(self.pwa_dir / "icons"))

        # Fallback catch-all to index.html for SPA routing
        app.router.add_get("/{tail:.*}", self._handle_fallback)

        # Setup TLS / SSL
        cert_file, key_file = ensure_certificate()
        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_ctx.load_cert_chain(str(cert_file), str(key_file))

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port, ssl_context=ssl_ctx)
        await self.site.start()

        self._is_running = True
        server_url = self.get_server_url()
        logger.info(f"Local HTTPS Server started successfully on {server_url}")
        server_signals.server_status.emit(True, server_url)

    @web.middleware
    async def _cors_middleware(self, request, handler):
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            try:
                response = await handler(request)
            except web.HTTPException as ex:
                response = ex

        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Device-Token, If-None-Match"
        return response

    def _extract_token(self, request: web.Request) -> str:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        if "X-Device-Token" in request.headers:
            return request.headers["X-Device-Token"].strip()
        if "token" in request.query:
            return request.query["token"].strip()
        return ""

    def _authenticate_request(self, request: web.Request):
        token = self._extract_token(request)
        if not token:
            return None
        return DeviceService.validate_token(token)

    @staticmethod
    def _is_local_request(request: web.Request) -> bool:
        """True only for requests coming from this very PC (the desktop app itself)."""
        remote = request.remote or ""
        return remote in ("127.0.0.1", "::1", "localhost") or remote.startswith("::ffff:127.")

    async def _handle_health(self, request: web.Request):
        return web.json_response({
            "status": "ok",
            "app": "TTL Scanner",
            "lan_ip": get_local_ip(),
            "port": self.port
        })

    async def _handle_pair(self, request: web.Request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"success": False, "message": "Invalid JSON body"}, status=400)

        code = str(data.get("code") or data.get("pairing_code", "")).strip()
        device_name = str(data.get("device_name", "")).strip() or "Mobile Terminal"

        success, message, token, device = DeviceService.verify_and_pair(code, device_name)
        if not success:
            return web.json_response({"success": False, "message": message}, status=400)

        # Emit Qt signal for desktop device list refresh
        server_signals.device_paired.emit(device)

        # Notify via websocket
        await self._broadcast_ws({
            "type": "device_paired",
            "device": device
        })

        return web.json_response({
            "success": True,
            "message": "Device paired successfully",
            "token": token,
            "device": device
        })

    async def _handle_materials(self, request: web.Request):
        device = self._authenticate_request(request)
        if not device:
            return web.json_response({"success": False, "message": "Unauthorized device token"}, status=401)

        # Fetch materials
        materials = MaterialService.get_all(active_only=True)

        # Format items for mobile client
        formatted = []
        for m in materials:
            formatted.append({
                "code": m.get("material_code", ""),
                "name": m.get("name", ""),
                "uom": m.get("unit", "EA"),
                "stock": float(m.get("current_stock") or 0.0),
                "price": float(m.get("unit_price") or 0.0),
                "plant": m.get("plant", "1304 HYDERABAD")
            })

        # ETag is a fingerprint of everything the phone displays (code, stock, price, ...),
        # so ANY stock/price change produces a new ETag and phones never show stale stock.
        digest = hashlib.md5()
        for item in formatted:
            digest.update(
                f"{item['code']}|{item['name']}|{item['uom']}|{item['stock']}|{item['price']}|{item['plant']};".encode("utf-8")
            )
        etag = f'"{digest.hexdigest()}"'
        cache_headers = {"ETag": etag, "Cache-Control": "private, no-cache"}

        client_etag = request.headers.get("If-None-Match")
        if client_etag and client_etag.strip() == etag:
            return web.Response(status=304, headers=cache_headers)

        return web.json_response(
            {"version": etag, "count": len(formatted), "materials": formatted},
            headers=cache_headers
        )

    async def _handle_stock(self, request: web.Request):
        device = self._authenticate_request(request)
        if not device:
            return web.json_response({"success": False, "message": "Unauthorized device token"}, status=401)

        code = request.match_info.get("code", "").strip()
        mat = MaterialService.get_by_code(code)
        if not mat:
            mat = MaterialService.get_by_barcode(code)

        if not mat:
            return web.json_response({"success": False, "message": f"Material '{code}' not found"}, status=404)

        return web.json_response({
            "success": True,
            "material": {
                "code": mat.get("material_code", ""),
                "name": mat.get("name", ""),
                "uom": mat.get("unit", "EA"),
                "current_stock": float(mat.get("current_stock") or 0.0),
                "unit_price": float(mat.get("unit_price") or 0.0),
                "plant": mat.get("plant", "1304 HYDERABAD")
            }
        })

    async def _handle_scan(self, request: web.Request):
        device = self._authenticate_request(request)
        if not device:
            return web.json_response({"success": False, "message": "Unauthorized device token"}, status=401)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"success": False, "message": "Invalid JSON body"}, status=400)

        success, message, result_dict = ScanService.process_scan(device, payload)
        if not success:
            return web.json_response({
                "success": False,
                "message": message,
                "data": result_dict
            }, status=400)

        # A retried event (same event_id) was already handled: acknowledge it to the phone
        # but do NOT forward it to the desktop again, otherwise the quantity is added twice.
        if not result_dict.get("duplicate"):
            # Emit Qt Signal for desktop views (Issue Slip / Plant Inward)
            server_signals.scan_received.emit(result_dict)

            # Broadcast event over WebSocket
            await self._broadcast_ws({
                "type": "scan_received",
                "data": result_dict
            })

        return web.json_response({
            "success": True,
            "message": message,
            "data": result_dict
        })

    async def _handle_scan_status(self, request: web.Request):
        device = self._authenticate_request(request)
        if not device:
            return web.json_response({"success": False, "message": "Unauthorized device token"}, status=401)

        event_id = request.match_info.get("event_id", "").strip()
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT event_id, device_id, device_name, mode, material_code, material_name,
                       uom, qty, required_qty, unit_price, gst_pct, total_price, purpose,
                       status, reject_reason, created_at, applied_at
                FROM scan_events
                WHERE event_id = ?;
            """, (event_id,))
            row = cur.fetchone()
            if not row:
                return web.json_response({"success": False, "message": "Event not found"}, status=404)
            return web.json_response({"success": True, "data": dict(row)})

    async def _handle_devices_list(self, request: web.Request):
        # Device management is a desktop-only operation: never expose it to the LAN.
        if not self._is_local_request(request):
            return web.json_response({"success": False, "message": "Forbidden: desktop only"}, status=403)
        devices = DeviceService.list_devices()
        return web.json_response({"success": True, "devices": devices})

    async def _handle_device_revoke(self, request: web.Request):
        if not self._is_local_request(request):
            return web.json_response({"success": False, "message": "Forbidden: desktop only"}, status=403)
        device_id_str = request.match_info.get("device_id", "")
        try:
            device_id = int(device_id_str)
        except ValueError:
            return web.json_response({"success": False, "message": "Invalid device ID"}, status=400)

        success, message = DeviceService.revoke_device(device_id)
        if success:
            server_signals.device_revoked.emit(device_id)
            await self._broadcast_ws({
                "type": "device_revoked",
                "device_id": device_id
            })
            return web.json_response({"success": True, "message": message})
        return web.json_response({"success": False, "message": message}, status=400)

    async def _handle_websocket(self, request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        logger.info(f"WebSocket client connected ({request.remote}). Total clients: {len(self._ws_clients)}")

        try:
            async for msg in ws:
                pass
        finally:
            self._ws_clients.discard(ws)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self._ws_clients)}")

        return ws

    async def _broadcast_ws(self, message: dict):
        if not self._ws_clients:
            return
        payload = json.dumps(message)
        dead_clients = set()
        for ws in self._ws_clients:
            try:
                await ws.send_str(payload)
            except Exception:
                dead_clients.add(ws)
        self._ws_clients -= dead_clients

    async def _handle_index(self, request: web.Request):
        index_file = self.pwa_dir / "index.html"
        if index_file.exists():
            return web.FileResponse(index_file)
        return web.Response(text="TTL Scanner PWA - index.html not found", status=404)

    async def _handle_manifest(self, request: web.Request):
        manifest_file = self.pwa_dir / "manifest.json"
        if manifest_file.exists():
            return web.FileResponse(manifest_file, headers={"Content-Type": "application/manifest+json"})
        return web.Response(text="Manifest not found", status=404)

    async def _handle_service_worker(self, request: web.Request):
        sw_file = self.pwa_dir / "sw.js"
        if sw_file.exists():
            return web.FileResponse(sw_file, headers={
                "Content-Type": "application/javascript",
                "Service-Worker-Allowed": "/"
            })
        return web.Response(text="Service worker not found", status=404)

    async def _handle_fallback(self, request: web.Request):
        if request.path.startswith("/api/"):
            return web.json_response({"success": False, "message": "Unknown API endpoint"}, status=404)
        # Fallback to index.html for SPA client navigation
        index_file = self.pwa_dir / "index.html"
        if index_file.exists():
            return web.FileResponse(index_file)
        return web.Response(text="Not found", status=404)


# Global server instance
_server_instance: Optional[LocalServer] = None


def get_server() -> LocalServer:
    global _server_instance
    if _server_instance is None:
        _server_instance = LocalServer()
    return _server_instance


def start_server(port: int = 8443) -> LocalServer:
    server = get_server()
    server.port = port
    server.start()
    return server


def stop_server():
    global _server_instance
    if _server_instance is not None:
        _server_instance.stop()
        _server_instance = None

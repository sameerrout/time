import asyncio
import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from aiohttp import web
from PySide6.QtCore import QObject, Signal

from app.core.database import get_db_connection
from app.core.logger import get_logger
from app.server.device_service import DeviceService
from app.server.http_server import server_signals
from app.server.scan_service import ScanService
from app.services.material_service import MaterialService

logger = get_logger("IssueSlipApp.RemoteServer")

MAX_BODY_SIZE = 64 * 1024  # 64 KB limit
PAIRING_LIMIT_PER_MINUTE = 5
DEVICE_LIMIT_PER_MINUTE = 120
WINDOW_SECONDS = 60.0
REQUEST_TIMEOUT_SECONDS = 15.0


class RateLimiter:
    """Thread-safe sliding-window rate limiter per key (IP or device identifier)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._history: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window: float = WINDOW_SECONDS) -> Tuple[bool, int]:
        """
        Check if request is allowed.
        Returns (allowed: bool, retry_after: int seconds).
        """
        now = time.monotonic()
        with self._lock:
            timestamps = self._history[key]
            # Discard timestamps outside window
            cutoff = now - window
            self._history[key] = [ts for ts in timestamps if ts > cutoff]
            timestamps = self._history[key]

            if len(timestamps) >= max_requests:
                # Calculate remaining seconds until oldest entry expires
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + window - now))
                return False, retry_after

            timestamps.append(now)
            return True, 0

    def reset(self):
        with self._lock:
            self._history.clear()


class RemoteServerSignals(QObject):
    """Signals specific to the remote internet listener."""
    remote_status = Signal(bool, str)  # (running, url)


remote_server_signals = RemoteServerSignals()


class RemoteServer:
    """
    Hardened loopback-only HTTP server bound to 127.0.0.1:8444.
    Exposes strictly 5 phone scanner endpoints.
    Desktop-only endpoints (/api/devices, /revoke, /ws, PWA) are strictly excluded.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8444):
        self.host = host
        self.port = port
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.thread: Optional[threading.Thread] = None
        self._is_running = False
        self.rate_limiter = RateLimiter()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def get_server_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self):
        """Start the remote listener in a background daemon thread."""
        if self._is_running:
            return
        self.thread = threading.Thread(
            target=self._run_event_loop,
            daemon=True,
            name="RemoteHttpServerThread"
        )
        self.thread.start()

    def stop(self):
        """Stop the remote listener cleanly."""
        if not self._is_running or not self.loop:
            return

        async def _cleanup():
            if self.runner:
                await self.runner.cleanup()

        try:
            future = asyncio.run_coroutine_threadsafe(_cleanup(), self.loop)
            future.result(timeout=3.0)
        except Exception as exc:
            logger.warning(f"Error during remote server shutdown: {exc}")
        finally:
            self._is_running = False
            remote_server_signals.remote_status.emit(False, "")
            logger.info("Remote loopback HTTP server stopped.")

    def _run_event_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start_server_coroutine())
            self.loop.run_forever()
        except Exception as exc:
            logger.error(f"Error in remote server thread: {exc}", exc_info=True)
            self._is_running = False
            remote_server_signals.remote_status.emit(False, "")
        finally:
            self.loop.close()

    def create_app(self) -> web.Application:
        """Create and configure the hardened aiohttp application."""
        app = web.Application(
            client_max_size=MAX_BODY_SIZE,
            middlewares=[
                self._error_and_headers_middleware,
                self._rate_limit_middleware,
            ]
        )

        # STRICTLY the 5 allowed phone endpoints
        app.router.add_get("/api/health", self._handle_health)
        app.router.add_post("/api/pair", self._handle_pair)
        app.router.add_get("/api/materials", self._handle_materials)
        app.router.add_post("/api/scan", self._handle_scan)
        app.router.add_get("/api/scan/{event_id}", self._handle_scan_status)

        # Explicitly reject /api/devices or any variants with JSON 404
        app.router.add_get("/api/devices", self._handle_not_found)
        app.router.add_post("/api/devices/{tail:.*}", self._handle_not_found)

        # Catch-all for any unknown route -> JSON 404
        app.router.add_route("*", "/{tail:.*}", self._handle_not_found)

        return app

    async def _start_server_coroutine(self):
        app = self.create_app()
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        self._is_running = True
        server_url = self.get_server_url()
        logger.info(f"Remote loopback listener started on {server_url}")
        remote_server_signals.remote_status.emit(True, server_url)

    # -------------------------------------------------------------------------
    # Security Helpers & Middleware
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_client_ip(request: web.Request) -> str:
        """
        Extract client IP.
        Cf-Connecting-Ip header is trusted here because this listener is bound
        STRICTLY to 127.0.0.1 (only Cloudflare tunnel forwards requests here).
        """
        cf_ip = request.headers.get("Cf-Connecting-Ip", "").strip()
        if cf_ip:
            return cf_ip
        return request.remote or "127.0.0.1"

    @staticmethod
    def _extract_token(request: web.Request) -> Optional[str]:
        """
        Extract bearer token ONLY from Authorization: Bearer <token>.
        ?token= query strings and non-bearer headers are strictly ignored.
        """
        auth_header = request.headers.get("Authorization", "").strip()
        if not auth_header:
            return None
        parts = auth_header.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
            return token if token else None
        return None

    def _authenticate_device(self, request: web.Request) -> Optional[dict]:
        token = self._extract_token(request)
        if not token:
            return None
        return DeviceService.validate_token(token)

    @web.middleware
    async def _error_and_headers_middleware(self, request: web.Request, handler):
        if request.method == "OPTIONS":
            resp = web.Response(status=204)
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, If-None-Match"
            return resp

        try:
            # Apply request timeout
            resp = await asyncio.wait_for(handler(request), timeout=REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            resp = web.json_response(
                {"success": False, "message": "Request timeout"},
                status=408
            )
        except web.HTTPRequestEntityTooLarge:
            resp = web.json_response(
                {"success": False, "message": f"Payload too large. Maximum size is {MAX_BODY_SIZE} bytes."},
                status=413
            )
        except web.HTTPNotFound:
            resp = web.json_response(
                {"success": False, "message": "Endpoint not found"},
                status=404
            )
        except json.JSONDecodeError:
            resp = web.json_response(
                {"success": False, "message": "Invalid JSON format"},
                status=400
            )
        except Exception as exc:
            # Mask any internal tracebacks from remote clients
            logger.error(f"Internal server error on {request.method} {request.path}: {exc}")
            resp = web.json_response(
                {"success": False, "message": "Internal server error"},
                status=500
            )

        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, If-None-Match"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @web.middleware
    async def _rate_limit_middleware(self, request: web.Request, handler):
        client_ip = self._get_client_ip(request)

        # 1. Pairing rate limit: max 5 requests / min per IP
        if request.path == "/api/pair":
            allowed, retry_after = self.rate_limiter.is_allowed(
                f"pair:{client_ip}",
                max_requests=PAIRING_LIMIT_PER_MINUTE,
                window=WINDOW_SECONDS
            )
            if not allowed:
                logger.warning(f"Rate limit exceeded for pairing from IP {client_ip}")
                return web.json_response(
                    {"success": False, "message": "Too many pairing attempts. Please try again later."},
                    status=429,
                    headers={"Retry-After": str(retry_after)}
                )

        # 2. General endpoint rate limit: max 120 calls / min per device (or IP)
        token = self._extract_token(request)
        rate_key = f"dev:{token[:16]}" if token else f"ip:{client_ip}"
        allowed, retry_after = self.rate_limiter.is_allowed(
            rate_key,
            max_requests=DEVICE_LIMIT_PER_MINUTE,
            window=WINDOW_SECONDS
        )
        if not allowed:
            logger.warning(f"Rate limit exceeded for {rate_key}")
            return web.json_response(
                {"success": False, "message": "Too many requests. Please slow down."},
                status=429,
                headers={"Retry-After": str(retry_after)}
            )

        return await handler(request)

    # -------------------------------------------------------------------------
    # Request Handlers
    # -------------------------------------------------------------------------
    async def _handle_not_found(self, request: web.Request):
        return web.json_response({"success": False, "message": "Not found"}, status=404)

    async def _handle_health(self, request: web.Request):
        return web.json_response({
            "status": "ok",
            "app": "TTL Scanner Remote",
            "listener": "127.0.0.1",
            "port": self.port
        })

    async def _handle_pair(self, request: web.Request):
        try:
            data = await request.json()
            if not isinstance(data, dict):
                return web.json_response({"success": False, "message": "Invalid JSON object"}, status=400)
        except web.HTTPException:
            raise
        except Exception:
            return web.json_response({"success": False, "message": "Invalid JSON body"}, status=400)

        code = str(data.get("code") or data.get("pairing_code", "")).strip()
        device_name = str(data.get("device_name", "")).strip() or "Remote Mobile Scanner"

        # Redact pairing code in logs
        logger.info(f"Remote pairing attempt received for device name: '{device_name}'")

        success, message, token, device = DeviceService.verify_and_pair(code, device_name)
        if not success:
            return web.json_response({"success": False, "message": message}, status=400)

        server_signals.device_paired.emit(device)

        return web.json_response({
            "success": True,
            "message": "Device paired successfully",
            "token": token,
            "device": device
        })

    async def _handle_materials(self, request: web.Request):
        device = self._authenticate_device(request)
        if not device:
            return web.json_response({"success": False, "message": "Unauthorized or revoked device token"}, status=401)

        materials = MaterialService.get_all(active_only=True)
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

    async def _handle_scan(self, request: web.Request):
        device = self._authenticate_device(request)
        if not device:
            return web.json_response({"success": False, "message": "Unauthorized or revoked device token"}, status=401)

        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                return web.json_response({"success": False, "message": "Invalid JSON object"}, status=400)
        except web.HTTPException:
            raise
        except Exception:
            return web.json_response({"success": False, "message": "Invalid JSON body"}, status=400)

        success, message, result_dict = ScanService.process_scan(device, payload)
        if not success:
            return web.json_response({
                "success": False,
                "message": message,
                "data": result_dict
            }, status=400)

        if not result_dict.get("duplicate"):
            server_signals.scan_received.emit(result_dict)

        return web.json_response({
            "success": True,
            "message": message,
            "data": result_dict
        })

    async def _handle_scan_status(self, request: web.Request):
        device = self._authenticate_device(request)
        if not device:
            return web.json_response({"success": False, "message": "Unauthorized or revoked device token"}, status=401)

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


_remote_server_instance: Optional[RemoteServer] = None
_remote_server_lock = threading.Lock()


def get_remote_server() -> Optional[RemoteServer]:
    return _remote_server_instance


def start_remote_server(port: int = 8444) -> RemoteServer:
    global _remote_server_instance
    with _remote_server_lock:
        if _remote_server_instance is None:
            _remote_server_instance = RemoteServer(port=port)
            _remote_server_instance.start()
        elif not _remote_server_instance.is_running:
            _remote_server_instance.start()
        return _remote_server_instance


def stop_remote_server():
    global _remote_server_instance
    with _remote_server_lock:
        if _remote_server_instance is not None:
            _remote_server_instance.stop()
            _remote_server_instance = None

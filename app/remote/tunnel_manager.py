import ctypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from app.core.config import BASE_DIR, DATA_DIR, RESOURCE_DIR
from app.core.logger import get_logger
from app.services.settings_service import SettingsService

logger = get_logger("IssueSlipApp.TunnelManager")

URL_REGEX = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9


def _assign_process_to_kill_on_close_job(proc_handle):
    """Assign process to a Windows Job Object that automatically terminates on parent exit."""
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryLimit", ctypes.c_size_t),
                ("PeakJobMemoryLimit", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        res = kernel32.SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info)
        )
        if res:
            kernel32.AssignProcessToJobObject(job, int(proc_handle))
            return job
    except Exception as exc:
        logger.debug(f"Job object assignment note: {exc}")
    return None


class TunnelSignals(QObject):
    """Qt signal bridge for tunnel status notifications."""
    status_changed = Signal(str, str, str)  # (status, public_url, error_message)


tunnel_signals = TunnelSignals()


class TunnelManager:
    """
    Manages the Cloudflare Tunnel subprocess for remote phone access.
    Supports 3 modes:
      - 'off': Internet access disabled (Local Wi-Fi only)
      - 'tunnel': Built-in Cloudflare quick tunnel (automatic trycloudflare.com address)
      - 'custom': Custom public address specified by user (no local cloudflared process)
    """

    def __init__(self, target_port: int = 8444):
        self.target_port = target_port
        self.mode: str = "off"  # "off" | "tunnel" | "custom"
        self.status: str = "offline"  # "offline" | "starting" | "online" | "error"
        self.public_url: str = ""
        self.last_error: str = ""
        self._proc: Optional[subprocess.Popen] = None
        self._job_handle = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    @staticmethod
    def extract_tunnel_url(log_text: str) -> Optional[str]:
        """Extract trycloudflare.com public URL from cloudflared output."""
        if not log_text:
            return None
        match = URL_REGEX.search(log_text)
        if match:
            return match.group(0).rstrip("/")
        return None

    @classmethod
    def get_installation_id(cls) -> str:
        """Fetch or generate persistent installation ID."""
        inst_id = SettingsService.get_setting("installation_id", "").strip()
        if not inst_id:
            inst_id = str(uuid.uuid4())
            SettingsService.set_setting(
                "installation_id",
                inst_id,
                category="remote",
                description="Unique installation ID for phone scanner binding"
            )
        return inst_id

    @classmethod
    def find_cloudflared_binary(cls) -> Optional[Path]:
        """Locate cloudflared.exe binary in bundle, app, or system path."""
        candidates = [
            RESOURCE_DIR / "bin" / "cloudflared.exe",
            BASE_DIR / "bin" / "cloudflared.exe",
            DATA_DIR / "bin" / "cloudflared.exe",
        ]
        for path in candidates:
            if path.exists() and path.is_file():
                return path

        which_path = shutil.which("cloudflared")
        if which_path:
            return Path(which_path)

        return None

    def get_public_url(self) -> str:
        mode = self.get_mode()
        if mode == "custom":
            return SettingsService.get_setting("custom_public_url", "").strip().rstrip("/")
        elif mode == "tunnel":
            return self.public_url if self.status == "online" else ""
        return ""

    def get_mode(self) -> str:
        return SettingsService.get_setting("internet_access_mode", "off").strip().lower()

    def set_mode(self, mode: str, custom_url: str = ""):
        mode = mode.strip().lower()
        if mode not in ("off", "tunnel", "custom"):
            mode = "off"
        SettingsService.set_setting("internet_access_mode", mode, category="remote")
        if custom_url:
            SettingsService.set_setting("custom_public_url", custom_url.strip(), category="remote")
        self.mode = mode

    def get_qr_payload(self, pairing_code: str = "") -> dict:
        """
        Build standard QR code dictionary:
        {v: 1, url: <public_url>, id: <installation_id>, code: <pairing_code>}
        """
        return {
            "v": 1,
            "url": self.get_public_url(),
            "id": self.get_installation_id(),
            "code": pairing_code.strip() if pairing_code else ""
        }

    def start(self):
        """Start the tunnel manager according to the active mode."""
        with self._lock:
            self._stop_event.clear()
            self.mode = self.get_mode()

            if self.mode == "off":
                self._update_status("offline", "", "")
                return

            if self.mode == "custom":
                custom_url = SettingsService.get_setting("custom_public_url", "").strip().rstrip("/")
                if not custom_url:
                    self._update_status("error", "", "Custom URL is empty. Please configure it in Settings.")
                else:
                    self._update_status("online", custom_url, "")
                return

            # Built-in cloudflared tunnel
            if self._thread and self._thread.is_alive():
                return

            self._update_status("starting", "", "")
            self._thread = threading.Thread(
                target=self._run_tunnel_loop,
                daemon=True,
                name="CloudflareTunnelThread"
            )
            self._thread.start()

    def stop(self):
        """Stop the tunnel subprocess and background loop cleanly."""
        with self._lock:
            self._stop_event.set()
            self._terminate_subprocess()
            self._update_status("offline", "", "")

    def _terminate_subprocess(self):
        if self._proc:
            try:
                logger.info("Stopping cloudflared tunnel process...")
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=1.0)
            except Exception as exc:
                logger.warning(f"Error terminating cloudflared: {exc}")
            finally:
                self._proc = None

    def _update_status(self, status: str, url: str, error: str):
        self.status = status
        self.public_url = url
        self.last_error = error
        tunnel_signals.status_changed.emit(status, url, error)

    def _run_tunnel_loop(self):
        backoff = 2.0
        while not self._stop_event.is_set():
            binary = self.find_cloudflared_binary()
            if not binary:
                err = "cloudflared.exe binary not found. Please install or place in bin/ folder."
                logger.error(err)
                self._update_status("error", "", err)
                # Wait for file to appear or user to change setting
                if self._stop_event.wait(timeout=10.0):
                    break
                continue

            cmd = [
                str(binary),
                "tunnel",
                "--no-autoupdate",
                "--url",
                f"http://127.0.0.1:{self.target_port}"
            ]

            logger.info(f"Launching Cloudflare Tunnel: {' '.join(cmd)}")
            creation_flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    creationflags=creation_flags
                )

                if os.name == "nt" and hasattr(self._proc, "_handle"):
                    self._job_handle = _assign_process_to_kill_on_close_job(self._proc._handle)

                url_discovered = False
                for line in self._proc.stdout:
                    if self._stop_event.is_set():
                        break
                    line_str = line.strip()
                    if not line_str:
                        continue

                    # Mask sensitive details in log, but keep diagnostic info
                    if "INF" in line_str or "trycloudflare" in line_str:
                        logger.debug(f"[cloudflared] {line_str}")

                    if not url_discovered:
                        discovered_url = self.extract_tunnel_url(line_str)
                        if discovered_url:
                            logger.info(f"Cloudflare Tunnel online at: {discovered_url}")
                            url_discovered = True
                            backoff = 2.0  # reset backoff upon success
                            self._update_status("online", discovered_url, "")

                exit_code = self._proc.wait() if self._proc else 0
                if self._stop_event.is_set():
                    break

                logger.warning(f"cloudflared exited unexpectedly with code {exit_code}")
                self._update_status("error", "", f"Tunnel disconnected (exit code {exit_code})")

            except Exception as exc:
                if self._stop_event.is_set():
                    break
                err = f"Failed to run cloudflared: {exc}"
                logger.error(err)
                self._update_status("error", "", err)

            # Backoff before restarting
            logger.info(f"Will retry tunnel launch in {backoff:.1f}s...")
            if self._stop_event.wait(timeout=backoff):
                break
            backoff = min(30.0, backoff * 1.5)

        self._terminate_subprocess()
        self._update_status("offline", "", "")


_tunnel_manager_instance: Optional[TunnelManager] = None
_tunnel_lock = threading.Lock()


def get_tunnel_manager() -> TunnelManager:
    global _tunnel_manager_instance
    with _tunnel_lock:
        if _tunnel_manager_instance is None:
            _tunnel_manager_instance = TunnelManager()
        return _tunnel_manager_instance

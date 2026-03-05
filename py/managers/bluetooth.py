"""Bluetooth device management via bluetoothctl."""

import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field

from logger import get_logger

log = get_logger("bt")


@dataclass
class BTDevice:
    address: str
    name: str
    paired: bool = False
    connected: bool = False


class BluetoothManager:
    def __init__(self):
        self._stub = shutil.which("bluetoothctl") is None
        self._devices: list[BTDevice] = []
        self._lock = threading.Lock()
        self._scanning = False
        self._scan_thread: threading.Thread | None = None

    @property
    def is_scanning(self) -> bool:
        return self._scanning

    # ── Lifecycle ──

    def start(self):
        if self._stub:
            log.warning("bluetoothctl not found, running in stub mode")
            return
        try:
            self._run("rfkill", "unblock", "bluetooth")
            self._btctl("power", "on")
            self._btctl("agent", "NoInputNoOutput")
            self._btctl("default-agent")
        except Exception as e:
            log.error("bt start failed: %s", e)
        self.refresh_devices()

    def stop(self):
        self.scan_stop()

    # ── Scanning ──

    def scan_start(self):
        if self._stub or self._scanning:
            return
        self._scanning = True
        self._scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
        self._scan_thread.start()

    def scan_stop(self):
        self._scanning = False
        if self._scan_thread and self._scan_thread.is_alive():
            self._scan_thread.join(timeout=3)
        self._scan_thread = None

    def _scan_worker(self):
        try:
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            proc.stdin.write("scan on\n")
            proc.stdin.flush()

            for _ in range(15):
                if not self._scanning:
                    break
                time.sleep(1)
                self.refresh_devices()

            proc.stdin.write("scan off\n")
            proc.stdin.write("quit\n")
            proc.stdin.flush()
            proc.wait(timeout=5)
        except Exception as e:
            log.error("scan error: %s", e)
        finally:
            self._scanning = False

    # ── Device list ──

    def get_devices(self) -> list[BTDevice]:
        with self._lock:
            return list(self._devices)

    def refresh_devices(self):
        if self._stub:
            return
        try:
            out = self._btctl("devices")
            devices = []
            for line in out.splitlines():
                # "Device AA:BB:CC:DD:EE:FF Name"
                parts = line.strip().split(" ", 2)
                if len(parts) >= 2 and parts[0] == "Device":
                    addr = parts[1]
                    name = parts[2] if len(parts) > 2 else addr
                    info = self._get_device_info(addr)
                    devices.append(BTDevice(
                        address=addr,
                        name=name,
                        paired=info.get("paired", False),
                        connected=info.get("connected", False),
                    ))
            with self._lock:
                self._devices = devices
        except Exception as e:
            log.error("refresh_devices: %s", e)

    def _get_device_info(self, address: str) -> dict:
        try:
            out = self._btctl("info", address)
            paired = False
            connected = False
            for line in out.splitlines():
                stripped = line.strip()
                if stripped.startswith("Paired:"):
                    paired = "yes" in stripped.lower()
                elif stripped.startswith("Connected:"):
                    connected = "yes" in stripped.lower()
            return {"paired": paired, "connected": connected}
        except Exception:
            return {}

    # ── Operations (synchronous, caller runs in thread) ──

    def pair(self, address: str) -> tuple[bool, str]:
        try:
            self._btctl("pair", address, timeout=15)
            self._btctl("trust", address, timeout=5)
            self.refresh_devices()
            return True, "Paired"
        except Exception as e:
            return False, str(e)

    def connect(self, address: str) -> tuple[bool, str]:
        try:
            self._btctl("connect", address, timeout=15)
            self.refresh_devices()
            return True, "Connected"
        except Exception as e:
            return False, str(e)

    def disconnect(self, address: str) -> tuple[bool, str]:
        try:
            self._btctl("disconnect", address, timeout=5)
            self.refresh_devices()
            return True, "Disconnected"
        except Exception as e:
            return False, str(e)

    def remove(self, address: str) -> tuple[bool, str]:
        try:
            self._btctl("remove", address, timeout=5)
            self.refresh_devices()
            return True, "Removed"
        except Exception as e:
            return False, str(e)

    # ── Helpers ──

    def _btctl(self, *args, timeout=5) -> str:
        result = subprocess.run(
            ["bluetoothctl", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout

    @staticmethod
    def _run(*args, timeout=5) -> str:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout

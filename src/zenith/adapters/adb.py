"""ADB Adapter — Android Debug Bridge transport.

Primary transport via adbutils library. Falls back to subprocess if adbutils unavailable.
Supports wireless ADB, device info, shell commands, file operations.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType

ADB_TIMEOUT = 30
ADB_RETRIES = 2
ADB_RETRY_DELAY = 1.0

_SERIAL_PATTERN = re.compile(r"^[a-zA-Z0-9._:\-]+$")
_SHELL_META = re.compile(r"[;&|`$(){}<>]")


class ADBAdapter(AdapterProtocol):
    name: ClassVar[str] = "adb"
    binary: ClassVar[str] = "adb"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.ADB, DeviceType.ANDROID)

    _pool_client: ClassVar[Any] = None
    _pool_lock: ClassVar[Any] = __import__("threading").Lock()

    @classmethod
    def _get_pooled_client(cls) -> Any:
        """Share a single adbutils client across all ADBAdapter instances."""
        if cls._pool_client is None:
            with cls._pool_lock:
                if cls._pool_client is None:
                    try:
                        from adbutils import AdbClient
                        cls._pool_client = AdbClient(host="127.0.0.1", port=5037)
                    except ImportError:
                        cls._pool_client = False
        return cls._pool_client if cls._pool_client is not False else None

    def __init__(self) -> None:
        self._active_serial: str | None = None
        self._use_adbutils = False
        self._init_adbutils()

    @staticmethod
    def _validate_serial(serial: str) -> None:
        if not _SERIAL_PATTERN.match(serial):
            raise ValueError(f"Invalid device serial: {serial!r}")

    @staticmethod
    def _validate_path(path: str, label: str = "path") -> None:
        if _SHELL_META.search(path):
            raise ValueError(f"Invalid {label} (contains shell metacharacters): {path!r}")

    def _init_adbutils(self) -> None:
        self._client = self._get_pooled_client()
        if self._client is not None:
            self._use_adbutils = True
            logger.info("ADBAdapter initialized with pooled adbutils client")

    def is_available(self) -> bool:
        if self._use_adbutils:
            return True
        return shutil.which(self.binary) is not None

    def list_devices(self) -> list[dict[str, str]]:
        if self._use_adbutils and self._client:
            try:
                results: list[dict[str, str]] = []
                for d in self._client.list(extended=True):
                    results.append({
                        "serial": d.serial, "state": d.state,
                        "model": getattr(d, "model", ""),
                        "product": getattr(d, "product", ""),
                    })
                return results
            except Exception as e:
                logger.warning(f"adbutils list failed: {e}")
        return self._list_via_subprocess()

    def _list_via_subprocess(self) -> list[dict[str, str]]:
        try:
            result = subprocess.run(
                [self.binary, "devices", "-l"], capture_output=True, text=True, timeout=10
            )
            devices: list[dict[str, str]] = []
            for line in result.stdout.strip().split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    info: dict[str, str] = {"serial": parts[0], "state": "device"}
                    for extra in parts[2:]:
                        if ":" in extra:
                            k, v = extra.split(":", 1)
                            info[k] = v
                    devices.append(info)
            return devices
        except Exception as e:
            logger.error(f"ADB subprocess list failed: {e}")
            return []

    def run(self, *args: str, timeout: int = ADB_TIMEOUT) -> AdapterResult:
        cmd_parts = [self.binary]
        if self._active_serial and len(args) > 0 and args[0] != "-s":
            cmd_parts.extend(["-s", self._active_serial])
        cmd_parts.extend(args)

        cmd_str = " ".join(cmd_parts)
        last_error = ""
        for attempt in range(1 + ADB_RETRIES):
            try:
                proc = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=timeout)
                return AdapterResult(
                    success=proc.returncode == 0,
                    command=cmd_str,
                    stdout=proc.stdout.strip(),
                    stderr=proc.stderr.strip(),
                    returncode=proc.returncode,
                )
            except subprocess.TimeoutExpired:
                last_error = "Command timed out"
            except Exception as e:
                last_error = str(e)
            if attempt < ADB_RETRIES:
                time.sleep(ADB_RETRY_DELAY)
        return AdapterResult(success=False, command=cmd_str, stderr=last_error)

    def connect(self, device_id: str) -> AdapterResult:
        self._validate_serial(device_id)
        self._active_serial = device_id
        return self.run("devices")

    def disconnect(self) -> None:
        self._active_serial = None

    def shell(self, command: str, timeout: int = ADB_TIMEOUT) -> AdapterResult:
        return self.run("shell", command, timeout=timeout)

    def getprop(self, prop: str) -> AdapterResult:
        return self.run("shell", "getprop", prop)

    def get_info(self, device_id: str = "") -> dict[str, Any]:
        if device_id:
            self._validate_serial(device_id)
            self._active_serial = device_id

        serial = self._active_serial or ""
        info: dict[str, Any] = {
            "serial": serial,
            "model": "Unknown",
            "manufacturer": "Unknown",
            "brand": "Unknown",
            "android_version": "Unknown",
            "sdk_level": "Unknown",
            "build_number": "Unknown",
            "cpu_abi": "Unknown",
            "security_patch": "Unknown",
            "hardware": "Unknown",
            "product_board": "Unknown",
        }

        r = self.run("shell", "getprop")
        if r.success and r.stdout:
            props: dict[str, str] = {}
            for line in r.stdout.splitlines():
                match = re.match(r"^\[(.+?)\]:\s*\[(.*?)\]", line.strip())
                if match:
                    props[match.group(1)] = match.group(2)

            info["model"] = props.get("ro.product.model", "Unknown")
            info["manufacturer"] = props.get("ro.product.manufacturer", "Unknown")
            info["brand"] = props.get("ro.product.brand", "Unknown")
            info["android_version"] = props.get("ro.build.version.release", "Unknown")
            info["sdk_level"] = props.get("ro.build.version.sdk", "Unknown")
            info["build_number"] = props.get("ro.build.display.id", "Unknown")
            info["cpu_abi"] = props.get("ro.product.cpu.abi", "Unknown")
            info["security_patch"] = props.get("ro.build.version.security_patch", "Unknown")
            info["hardware"] = props.get("ro.hardware", "Unknown")
            info["product_board"] = props.get("ro.product.board", "Unknown")

        return info

    def reboot(self, mode: str | None = None, timeout: int = 30) -> AdapterResult:
        args = ["reboot"]
        if mode:
            args.append(mode)
        return self.run(*args, timeout=timeout)

    def reboot_bootloader(self) -> AdapterResult:
        return self.reboot("bootloader")

    def reboot_recovery(self) -> AdapterResult:
        return self.reboot("recovery")

    def reboot_edl(self) -> AdapterResult:
        return self.reboot("edl")

    def install(self, apk_path: str, timeout: int = 120) -> AdapterResult:
        return self.run("install", apk_path, timeout=timeout)

    def uninstall(self, package: str) -> AdapterResult:
        return self.run("uninstall", package)

    def push(self, local: str, remote: str, timeout: int = 120) -> AdapterResult:
        return self.run("push", local, remote, timeout=timeout)

    def pull(self, remote: str, local: str, timeout: int = 120) -> AdapterResult:
        return self.run("pull", remote, local, timeout=timeout)

    def logcat_dump(self, timeout: int = 60) -> AdapterResult:
        return self.run("logcat", "-d", timeout=timeout)

    def bugreport(self, output: str = "", timeout: int = 300) -> AdapterResult:
        args = ["bugreport"]
        if output:
            args.append(output)
        return self.run(*args, timeout=timeout)

    def connect_wireless(self, host: str, port: int = 5555) -> AdapterResult:
        return self.run("connect", f"{host}:{port}")

    def pair(self, host: str, port: int, code: str) -> AdapterResult:
        return self.run("pair", f"{host}:{port}", code)

    def root_restart(self) -> AdapterResult:
        r = self.run("root")
        if not r.success:
            return r
        return self.run("remount")

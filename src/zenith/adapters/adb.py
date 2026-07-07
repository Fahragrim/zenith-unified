"""ADB Adapter — Android Debug Bridge transport.

Primary transport via adbutils library. Falls back to subprocess if adbutils unavailable.
Supports wireless ADB, device info, shell commands, file operations.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType

ADB_TIMEOUT = 30


class ADBAdapter(AdapterProtocol):
    name: ClassVar[str] = "adb"
    binary: ClassVar[str] = "adb"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.ADB, DeviceType.ANDROID)

    def __init__(self) -> None:
        self._client = None
        self._active_serial: str | None = None
        self._use_adbutils = False
        self._init_adbutils()

    def _init_adbutils(self) -> None:
        try:
            from adbutils import AdbClient  # type: ignore[attr-defined]
            self._client = AdbClient(host="127.0.0.1", port=5037)
            self._use_adbutils = True
            logger.info("ADBAdapter initialized with adbutils")
        except ImportError:
            self._use_adbutils = False
            logger.warning("adbutils not installed — using subprocess fallback")

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
            return AdapterResult(success=False, command=cmd_str, stderr="Command timed out")
        except Exception as e:
            return AdapterResult(success=False, command=cmd_str, stderr=str(e))

    def connect(self, device_id: str) -> AdapterResult:
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
            self._active_serial = device_id

        def _getprop(key: str) -> str:
            r = self.getprop(key)
            return r.stdout if r.success else "Unknown"

        return {
            "serial": self._active_serial or "",
            "model": _getprop("ro.product.model"),
            "manufacturer": _getprop("ro.product.manufacturer"),
            "brand": _getprop("ro.product.brand"),
            "android_version": _getprop("ro.build.version.release"),
            "sdk_level": _getprop("ro.build.version.sdk"),
            "build_number": _getprop("ro.build.display.id"),
            "cpu_abi": _getprop("ro.product.cpu.abi"),
            "security_patch": _getprop("ro.build.version.security_patch"),
            "hardware": _getprop("ro.hardware"),
            "product_board": _getprop("ro.product.board"),
        }

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
        self.run("root")
        return self.run("remount")

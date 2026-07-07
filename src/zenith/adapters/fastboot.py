"""Fastboot Adapter — Fastboot/Bootloader transport.

Supports getvar, flash, erase, oem commands, and OEM fuzzing.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType

# Hidden OEM commands for fuzzing
OEM_FUZZ_COMMANDS = [
    "unlock", "unlock-go", "device-info", "edl", "reboot-recovery",
    "enable-bp-tools", "qcom-on", "diag-enable", "hw-test", "off-mode-charge 0",
    "dump-registers", "test-mode", "debug-on", "serial-log-on", "atd-on",
]


class FastbootAdapter(AdapterProtocol):
    name: ClassVar[str] = "fastboot"
    binary: ClassVar[str] = "fastboot"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.FASTBOOT,)

    def __init__(self) -> None:
        self._active_serial: str | None = None

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def _run_raw(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str] | None:
        cmd_parts = [self.binary]
        if self._active_serial and args and args[0] != "-s":
            cmd_parts.extend(["-s", self._active_serial])
        cmd_parts.extend(args)
        try:
            return subprocess.run(cmd_parts, capture_output=True, text=True, timeout=timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def list_devices(self) -> list[dict[str, str]]:
        proc = self._run_raw("devices", timeout=10)
        if proc and proc.returncode == 0:
            devices: list[dict[str, str]] = []
            for line in proc.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 2:
                    devices.append({"serial": parts[0].strip(), "state": parts[1].strip()})
            return devices
        return []

    def run(self, *args: str, timeout: int = 60) -> AdapterResult:
        proc = self._run_raw(*args, timeout=timeout)
        if proc is None:
            cmd = f"fastboot {' '.join(args)}"
            return AdapterResult(success=False, command=cmd, stderr="Command failed or timed out")
        return AdapterResult(
            success=proc.returncode == 0,
            command=f"fastboot {' '.join(args)}",
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
            returncode=proc.returncode,
        )

    def connect(self, device_id: str) -> AdapterResult:
        self._active_serial = device_id
        return self.run("devices")

    def disconnect(self) -> None:
        self._active_serial = None

    def get_info(self, device_id: str = "") -> dict[str, Any]:
        if device_id:
            self._active_serial = device_id
        info: dict[str, Any] = {}
        for var in ("product", "serialno", "secure", "unlocked",
                     "battery-voltage", "version-baseband", "version-bootloader",
                     "variant", "hw-revision", "max-download-size"):
            r = self.run("getvar", var, timeout=10)
            if r.success:
                for line in r.stdout.split("\n"):
                    if line.startswith(f"{var}:"):
                        info[var] = line.split(": ", 1)[-1].strip()
        return info

    # ─── Read-only ──────────────────────────────

    def getvar(self, var: str) -> AdapterResult:
        return self.run("getvar", var)

    def getvar_all(self) -> AdapterResult:
        return self.run("getvar", "all", timeout=30)

    def devices_raw(self) -> AdapterResult:
        return self.run("devices")

    # ─── Destructive ──────────────────────────────

    def flash(self, partition: str, image_path: str, timeout: int = 300) -> AdapterResult:
        logger.warning(f"Flashing {partition} with {image_path}")
        return self.run("flash", partition, image_path, timeout=timeout)

    def erase(self, partition: str) -> AdapterResult:
        logger.warning(f"Erasing {partition}")
        return self.run("erase", partition)

    def format(self, partition: str) -> AdapterResult:
        logger.warning(f"Formatting {partition}")
        return self.run("format", partition)

    def boot(self, kernel_img: str) -> AdapterResult:
        return self.run("boot", kernel_img, timeout=60)

    # ─── Bootloader control ──────────────────────

    def reboot(self) -> AdapterResult:
        return self.run("reboot")

    def reboot_bootloader(self) -> AdapterResult:
        return self.run("reboot-bootloader")

    def continue_boot(self) -> AdapterResult:
        return self.run("continue")

    def oem_device_info(self) -> AdapterResult:
        return self.run("oem", "device-info")

    def oem_unlock(self) -> AdapterResult:
        logger.warning("FASTBOOT OEM UNLOCK — may wipe all device data")
        return self.run("oem", "unlock")

    def oem_lock(self) -> AdapterResult:
        return self.run("oem", "lock")

    def oem_edl(self) -> AdapterResult:
        return self.run("oem", "edl")

    def flashing_unlock(self) -> AdapterResult:
        return self.run("flashing", "unlock")

    def flashing_lock(self) -> AdapterResult:
        return self.run("flashing", "lock")

    def flashing_unlock_critical(self) -> AdapterResult:
        return self.run("flashing", "unlock_critical")

    # ─── OEM Fuzzing ──────────────────────────────

    def fuzz_oem_commands(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for cmd in OEM_FUZZ_COMMANDS:
            r = self.run("oem", cmd, timeout=10)
            stderr_lower = r.stderr.lower()
            interesting = "unknown command" not in stderr_lower and "not allowed" not in stderr_lower
            results.append({
                "command": f"fastboot oem {cmd}",
                "response": r.stderr or r.stdout,
                "interesting": interesting,
            })
            logger.info(f"OEM fuzz: {cmd} → interesting={interesting}")
        return results

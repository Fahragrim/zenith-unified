"""Sony S1 Adapter — Sony Flashmode (S1 Protocol) via Newflasher.

USB VID: 0x0FCE, PID: 0xADE5 (Flashmode).
Wraps Newflasher for firmware flashing, TA backup/restore, and S1 detect.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType

S1_VID = 0x0FCE
S1_PID = 0xADE5
FASTBOOT_VID = 0x0FCE
FASTBOOT_PID = 0x0DDE


class SonyS1Adapter(AdapterProtocol):
    name: ClassVar[str] = "sony_s1"
    binary: ClassVar[str] = "newflasher"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.QUALCOMM_EDL,)

    def __init__(self) -> None:
        self._newflasher = self._find_newflasher()
        self._available = self._newflasher is not None
        self._has_pyusb = bool(importlib.util.find_spec("usb.core"))

    def _find_newflasher(self) -> str | None:
        candidates = [shutil.which("newflasher")]
        local = Path("newflasher.exe")
        if local.exists():
            candidates.append(str(local.resolve()))
        for c in candidates:
            if c:
                return c
        return None

    def is_available(self) -> bool:
        return self._available or self._has_pyusb

    def connect(self, device_id: str = "") -> AdapterResult:
        if not self._has_pyusb:
            return AdapterResult(success=False, command="sony_s1 connect",
                                stderr="pyusb not installed")
        try:
            import usb.core
            dev = usb.core.find(idVendor=S1_VID, idProduct=S1_PID)
            if dev is not None:
                return AdapterResult(success=True, command="sony_s1 connect",
                                    stdout=f"Sony Flashmode device: {dev.bus}:{dev.address}")
            return AdapterResult(success=False, command="sony_s1 connect",
                                stderr="No Sony Flashmode device (VID 0FCE, PID ADE5)")
        except Exception as e:
            return AdapterResult(success=False, command="sony_s1 connect", stderr=str(e))

    def list_devices(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            import usb.core
            dev = usb.core.find(idVendor=S1_VID, idProduct=S1_PID)
            if dev is not None:
                results.append({"serial": f"S1_{dev.bus:03d}_{dev.address:03d}",
                               "vid": "0x0FCE", "pid": "0xADE5", "mode": "flashmode"})
            dev2 = usb.core.find(idVendor=FASTBOOT_VID, idProduct=FASTBOOT_PID)
            if dev2 is not None:
                results.append({"serial": f"FB_{dev2.bus:03d}_{dev2.address:03d}",
                               "vid": "0x0FCE", "pid": "0x0DDE", "mode": "fastboot"})
        except Exception:
            pass
        if self._available:
            results.append({"status": "available", "tool": "newflasher"})
        return results

    def run(self, *args: str, timeout: int = 600) -> AdapterResult:
        if not self._newflasher:
            return AdapterResult(success=False, command="newflasher", stderr="newflasher not found")
        try:
            cmd = [self._newflasher] + list(args)
            logger.info(f"Running: {' '.join(cmd)}")
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return AdapterResult(success=proc.returncode == 0, command=f"newflasher {' '.join(args)}",
                                stdout=proc.stdout.strip(), stderr=proc.stderr.strip())
        except subprocess.TimeoutExpired:
            return AdapterResult(success=False, command="newflasher", stderr=f"Timed out after {timeout}s")
        except Exception as e:
            return AdapterResult(success=False, command="newflasher", stderr=str(e))

    def flash(self, firmware_dir: str = "") -> AdapterResult:
        """Flash all firmware from a directory containing .sin files."""
        fw = Path(firmware_dir) if firmware_dir else Path.cwd()
        if not fw.exists():
            return AdapterResult(success=False, command="newflasher flash", stderr=f"Firmware dir not found: {fw}")
        sin_files = list(fw.glob("*.sin"))
        if not sin_files:
            return AdapterResult(success=False, command="newflasher flash", stderr=f"No .sin files in {fw}")
        logger.warning(f"Newflasher — flashing {len(sin_files)} .sin files from {fw}")
        return self.run("-i", "firmware.txt")

    def list_firmware(self, firmware_dir: str = "") -> list[dict[str, Any]]:
        """List firmware files in a directory (output for GUI preview)."""
        fw = Path(firmware_dir) if firmware_dir else Path.cwd()
        if not fw.exists():
            return []
        results = []
        for ext in ("*.sin", "*.ta", "*.elf", "*.mbn"):
            for f in sorted(fw.glob(ext)):
                results.append({"filename": f.name, "size_bytes": f.stat().st_size,
                               "type": f.suffix.lstrip(".")})
        return results

    def backup_ta(self, output_dir: str = "") -> AdapterResult:
        """Backup TA (DRM) partition before bootloader unlock."""
        out = Path(output_dir) if output_dir else Path.cwd()
        out.mkdir(parents=True, exist_ok=True)
        logger.warning("TA partition backup via newflasher")
        return self.run("-t", str(out))

    def detect(self) -> AdapterResult:
        try:
            import usb.core
            dev = usb.core.find(idVendor=S1_VID, idProduct=S1_PID)
            if dev is not None:
                return AdapterResult(success=True, command="sony detect",
                                    stdout=f"Sony Flashmode device: {dev.bus}:{dev.address}")
            dev2 = usb.core.find(idVendor=FASTBOOT_VID, idProduct=FASTBOOT_PID)
            if dev2 is not None:
                return AdapterResult(success=True, command="sony detect",
                                    stdout=f"Sony Fastboot device: {dev2.bus}:{dev2.address}")
            return AdapterResult(success=False, command="sony detect", stderr="No Sony device found")
        except ImportError:
            if self._available:
                return AdapterResult(success=True, command="sony detect",
                                    stdout="newflasher available (plug in device to Flashmode)")
            return AdapterResult(success=False, command="sony detect", stderr="pyusb not installed, newflasher not found")
        except Exception as e:
            return AdapterResult(success=False, command="sony detect", stderr=str(e))

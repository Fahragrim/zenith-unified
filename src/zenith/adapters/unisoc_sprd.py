"""Unisoc SPRD Adapter — BootROM HDLC + Socrates protocol via pyusb.

Native Python implementation. USB VID: 1782, PID: 4D00.
Supports FDL1/FDL2 chainloading, .pac flashing, partition read/write/erase.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class UnisocSPRDAdapter(AdapterProtocol):
    name: ClassVar[str] = "unisoc_sprd"
    binary: ClassVar[str] = ""
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.UNISOC_SPD,)

    def __init__(self) -> None:
        self._usb_available = False
        self._device = None
        self._hdlc = None
        self._socrates = None
        self._init()

    def _init(self) -> None:
        self._usb_available = bool(importlib.util.find_spec("usb.core"))
        if not self._usb_available:
            logger.warning("pyusb not installed — SPRD USB mode unavailable")

    def is_available(self) -> bool:
        return self._usb_available

    def connect(self, device_id: str = "") -> AdapterResult:
        if not self._usb_available:
            return AdapterResult(success=False, command="sprd connect", stderr="pyusb not installed")
        try:
            from ._sprd_protocol import HDLCBootROM, SPRDDevice
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            dev = SPRDDevice()
            ok = loop.run_until_complete(dev.open())
            if not ok:
                loop.close()
                return AdapterResult(success=False, command="sprd connect",
                                    stderr="Could not open SPRD USB device (VID 1782, PID 4D00)")
            hdlc = HDLCBootROM(dev)
            loop.run_until_complete(hdlc.send_hello())
            self._device = dev
            self._hdlc = hdlc
            loop.close()
            return AdapterResult(success=True, command="sprd connect",
                                stdout="SPRD BootROM connected")
        except Exception as e:
            return AdapterResult(success=False, command="sprd connect", stderr=str(e))

    def disconnect(self) -> None:
        if self._device is not None:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._device.close())
                loop.close()
            except Exception:
                pass
            self._device = None
            self._hdlc = None
            self._socrates = None

    def _ensure_hdlc(self) -> None:
        if self._hdlc is None:
            self.connect()

    def _ensure_socrates(self) -> None:
        self._ensure_hdlc()
        if self._socrates is None and self._device is not None:
            from ._sprd_protocol import Socrates
            self._socrates = Socrates(self._device)

    def list_devices(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            import usb.core
            dev = usb.core.find(idVendor=0x1782, idProduct=0x4D00)
            if dev is not None:
                results.append({"serial": f"SPRD_{dev.bus:03d}_{dev.address:03d}",
                               "vid": "0x1782", "pid": "0x4D00", "status": "detected"})
        except Exception:
            pass
        return results

    def run(self, *args: str, timeout: int = 60) -> AdapterResult:
        if not args:
            return AdapterResult(success=False, command="sprd", stderr="No command")
        cmd = args[0]

        if cmd == "detect":
            return self.detect()
        elif cmd == "connect":
            return self.connect()
        elif cmd == "disconnect":
            self.disconnect()
            return AdapterResult(success=True, command="sprd disconnect")
        elif cmd == "load_fdl1":
            if len(args) < 2:
                return AdapterResult(success=False, command=cmd, stderr="Need FDL1 path")
            return self.load_fdl1_sync(args[1])
        elif cmd == "load_fdl2":
            if len(args) < 2:
                return AdapterResult(success=False, command=cmd, stderr="Need FDL2 path")
            return self.load_fdl2_sync(args[1])
        elif cmd == "load_fdl_from_pac":
            if len(args) < 2:
                return AdapterResult(success=False, command=cmd, stderr="Need .pac path")
            which = args[2] if len(args) > 2 else "fdl1"
            return self.load_fdl_from_pac_sync(args[1], which)
        elif cmd == "flash_pac":
            if len(args) < 2:
                return AdapterResult(success=False, command=cmd, stderr="Need .pac path")
            return self.flash_pac_sync(args[1])
        elif cmd == "get_version":
            return self._run_socrates("get_version")
        elif cmd == "read32":
            if len(args) < 2:
                return AdapterResult(success=False, command=cmd, stderr="Need address")
            return self._run_socrates("read32", addr=int(args[1], 0))
        else:
            return AdapterResult(success=False, command=f"sprd {cmd}",
                                stderr=f"Unknown SPRD command: {cmd}")

    def detect(self) -> AdapterResult:
        try:
            import usb.core
            dev = usb.core.find(idVendor=0x1782, idProduct=0x4D00)
            if dev is not None:
                return AdapterResult(success=True, command="sprd detect",
                                    stdout=f"SPRD BootROM found: bus={dev.bus} addr={dev.address}")
            return AdapterResult(success=False, command="sprd detect", stderr="No SPRD BootROM device found")
        except Exception as e:
            return AdapterResult(success=False, command="sprd detect", stderr=str(e))

    def _run_hdlc(self, method: str, *args: Any, **kwargs: Any) -> AdapterResult:
        self._ensure_hdlc()
        if self._hdlc is None:
            return AdapterResult(success=False, command=method, stderr="Not connected")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            coro = getattr(self._hdlc, method)(*args, **kwargs)
            result = loop.run_until_complete(coro)
            loop.close()
            return AdapterResult(success=True, command=f"sprd {method}", stdout=str(result))
        except Exception as e:
            return AdapterResult(success=False, command=f"sprd {method}", stderr=str(e))

    def _run_socrates(self, method: str, **kwargs: Any) -> AdapterResult:
        self._ensure_socrates()
        if self._socrates is None:
            return AdapterResult(success=False, command=method, stderr="Socrates not initialized")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            coro = getattr(self._socrates, method)(**kwargs)
            result = loop.run_until_complete(coro)
            loop.close()
            return AdapterResult(success=True, command=f"sprd {method}", stdout=str(result))
        except Exception as e:
            return AdapterResult(success=False, command=f"sprd {method}", stderr=str(e))

    def load_fdl1_sync(self, fdl1_path: str) -> AdapterResult:
        from pathlib import Path
        p = Path(fdl1_path)
        if not p.exists():
            return AdapterResult(success=False, command="load_fdl1", stderr=f"FDL1 not found: {fdl1_path}")
        data = p.read_bytes()
        return self._run_hdlc("send_payload", 0x50000000, data)

    def load_fdl2_sync(self, fdl2_path: str) -> AdapterResult:
        from pathlib import Path
        p = Path(fdl2_path)
        if not p.exists():
            return AdapterResult(success=False, command="load_fdl2", stderr=f"FDL2 not found: {fdl2_path}")
        data = p.read_bytes()
        return self._run_hdlc("send_payload", 0x9EFFFE00, data)

    def load_fdl_from_pac_sync(self, pac_path: str, which: str = "fdl1") -> AdapterResult:
        try:
            from ._sprd_protocol import extract_fdl1, extract_fdl2, parse_pac
            pac = parse_pac(pac_path)
            if which == "fdl1":
                data = extract_fdl1(pac)
                addr = 0x50000000
            else:
                data = extract_fdl2(pac)
                addr = 0x9EFFFE00
            self._ensure_hdlc()
            if self._hdlc is None:
                return AdapterResult(success=False, command=f"load_{which}", stderr="Not connected")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._hdlc.send_payload(addr, data))
            loop.run_until_complete(self._hdlc.send_jump_to_payload(addr))
            loop.close()
            return AdapterResult(success=True, command=f"sprd load_{which}",
                                stdout=f"{which.upper()} loaded ({len(data)} bytes) from PAC")
        except Exception as e:
            return AdapterResult(success=False, command=f"sprd load_{which}", stderr=str(e))

    def flash_pac_sync(self, pac_path: str) -> AdapterResult:
        try:
            from ._sprd_protocol import flash_pac_file
            self._ensure_socrates()
            if self._socrates is None:
                return AdapterResult(success=False, command="flash_pac", stderr="Socrates not initialized")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(flash_pac_file(self._socrates, pac_path))
            loop.close()
            total = len(results)
            ok = sum(1 for v in results.values() if v)
            return AdapterResult(success=ok == total, command=f"sprd flash_pac {pac_path}",
                                stdout=f"Flashed {ok}/{total} partitions from {Path(pac_path).name}")
        except Exception as e:
            return AdapterResult(success=False, command="sprd flash_pac", stderr=str(e))

    async def connect_raw(self) -> AdapterResult:
        return self.connect()

    async def get_bootrom_version(self) -> AdapterResult:
        return self._run_hdlc("send_hello")

    async def load_fdl1(self, fdl1_data: bytes) -> AdapterResult:
        result = self._run_hdlc("send_payload", 0x50000000, fdl1_data)
        if result.success:
            self._run_hdlc("send_jump_to_payload", 0x50000000)
        return result

    async def load_fdl_from_pac(self, pac_path: str, which: str = "fdl1") -> AdapterResult:
        return self.load_fdl_from_pac_sync(pac_path, which)

    async def flash_pac(self, pac_path: str) -> AdapterResult:
        return self.flash_pac_sync(pac_path)

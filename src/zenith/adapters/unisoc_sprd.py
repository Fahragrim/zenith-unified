"""Unisoc SPRD Adapter — BootROM HDLC + Socrates protocol via pyusb.

Native Python implementation of the SPRD BootROM protocol.
USB VID: 1782, PID: 4D00.
Supports FDL1/FDL2 chainloading, .pac flashing, partition read/write/erase.
"""

from __future__ import annotations

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
        self._init()

    def _init(self) -> None:
        try:
            import usb.core  # noqa: F401
            self._usb_available = True
        except ImportError:
            logger.warning("pyusb not installed — SPRD USB mode unavailable")

    def is_available(self) -> bool:
        return self._usb_available

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
        return AdapterResult(success=False, command="sprd",
                            stderr="SPRD adapter requires device connection. Use connect() first with pyusb.")

    def detect(self) -> AdapterResult:
        """Check if a Unisoc SPD BootROM device is connected via USB."""
        try:
            import usb.core
            dev = usb.core.find(idVendor=0x1782, idProduct=0x4D00)
            if dev is not None:
                return AdapterResult(success=True, command="sprd detect",
                                    stdout=f"SPRD BootROM found: bus={dev.bus} addr={dev.address}")
            return AdapterResult(success=False, command="sprd detect", stderr="No SPRD BootROM device found")
        except Exception as e:
            return AdapterResult(success=False, command="sprd detect", stderr=str(e))

    async def connect_raw(self) -> AdapterResult:
        """Connect via pyusb to the SPRD BootROM device."""
        try:
            from ._sprd_protocol import SPRDDevice
            self._device = SPRDDevice()
            ok = await self._device.open()
            return AdapterResult(success=ok, command="sprd connect",
                                stdout="Connected" if ok else "",
                                stderr="" if ok else "Could not open SPRD USB device")
        except ImportError:
            return AdapterResult(success=False, command="sprd connect",
                                stderr="pyusb not installed. Run: pip install pyusb")
        except Exception as e:
            return AdapterResult(success=False, command="sprd connect", stderr=str(e))

    async def get_bootrom_version(self) -> AdapterResult:
        try:
            if not hasattr(self, '_device') or self._device is None:
                return AdapterResult(success=False, command="sprd version", stderr="Not connected")
            from ._sprd_protocol import HDLCBootROM
            hdlc = HDLCBootROM(self._device)
            version = await hdlc.send_hello()
            return AdapterResult(success=True, command="sprd version", stdout=version)
        except Exception as e:
            return AdapterResult(success=False, command="sprd version", stderr=str(e))

    async def load_fdl1(self, fdl1_data: bytes) -> AdapterResult:
        try:
            from ._sprd_protocol import HDLCBootROM
            hdlc = HDLCBootROM(self._device)
            await hdlc.send_payload(0x50000000, fdl1_data)
            await hdlc.send_jump_to_payload(0x50000000)
            return AdapterResult(success=True, command="sprd load_fdl1",
                                stdout=f"FDL1 loaded ({len(fdl1_data)} bytes)")
        except Exception as e:
            return AdapterResult(success=False, command="sprd load_fdl1", stderr=str(e))

    async def load_fdl_from_pac(self, pac_path: str, which: str = "fdl1") -> AdapterResult:
        """Load FDL1 or FDL2 from a .pac firmware file."""
        try:
            from ._sprd_protocol import HDLCBootROM, extract_fdl1, extract_fdl2, parse_pac
            pac = parse_pac(pac_path)
            hdlc = HDLCBootROM(self._device)
            addr: int
            if which == "fdl1":
                data = extract_fdl1(pac)
                addr = 0x50000000
            else:
                data = extract_fdl2(pac)
                addr = 0x60000000
            await hdlc.send_payload(addr, data)
            await hdlc.send_jump_to_payload(addr)
            return AdapterResult(success=True, command=f"sprd load_{which}",
                                stdout=f"{which.upper()} loaded ({len(data)} bytes)")
        except Exception as e:
            return AdapterResult(success=False, command=f"sprd load_{which}", stderr=str(e))

    async def flash_pac(self, pac_path: str) -> AdapterResult:
        """Flash all partitions from a .pac file."""
        try:
            from ._sprd_protocol import Socrates, flash_pac_file
            soc = Socrates(self._device)
            results = await flash_pac_file(soc, pac_path)
            return AdapterResult(success=all(results.values()), command=f"sprd flash_pac {pac_path}",
                                stdout=f"Flashed {sum(1 for v in results.values() if v)}/{len(results)} partitions")
        except Exception as e:
            return AdapterResult(success=False, command=f"sprd flash_pac {pac_path}", stderr=str(e))

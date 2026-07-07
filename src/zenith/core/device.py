"""Device abstraction and models.

Combines the best of:
- OpencodeDeviceTool's devices/base.py (Device ABC, DeviceType, DeviceInfo)
- xperiatool's core/models.py (DeviceProfile, FRPMethod, RiskLevel)
- Pydantic v2 for validation and serialization
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ─── Enums ───────────────────────────────────────────────────────────────────


class DeviceType(str, Enum):
    ADB = "adb"
    FASTBOOT = "fastboot"
    ANDROID = "android"
    QUALCOMM_EDL = "qualcomm_edl"
    MTK_BROM = "mtk_brom"
    SAMSUNG_ODIN = "samsung_odin"
    APPLE_DFU = "apple_dfu"
    ROCKCHIP_MASKROM = "rockchip_maskrom"
    ALLWINNER_FEL = "allwinner_fel"
    UNISOC_SPD = "unisoc_spd"
    STORAGE = "storage"
    UART = "uart"
    DIAG = "diag"
    UNKNOWN = "unknown"


class DeviceStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    BUSY = "busy"
    ERROR = "error"


class ActionType(str, Enum):
    READ = "read"
    WRITE = "write"
    ERASE = "erase"
    FLASH = "flash"
    REBOOT = "reboot"
    UNLOCK = "unlock"
    DIAG = "diag"
    SCAN = "scan"
    BACKUP = "backup"
    RESTORE = "restore"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SoCVendor(str, Enum):
    QUALCOMM = "Qualcomm"
    MEDIATEK = "MediaTek"
    UNISOC = "Unisoc"
    SAMSUNG = "Samsung"
    GOOGLE = "Google"
    HISILICON = "HiSilicon"
    ROCKCHIP = "Rockchip"
    ALLWINNER = "Allwinner"
    APPLE = "Apple"
    NVIDIA = "Nvidia"
    UNKNOWN = "Unknown"


# ─── Pydantic Models ─────────────────────────────────────────────────────────


class DeviceInfo(BaseModel):
    """Information about a connected device."""

    model_config = ConfigDict(extra="forbid")

    type: DeviceType = DeviceType.UNKNOWN
    serial: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    codename: str | None = None
    soc: str | None = None
    soc_vendor: SoCVendor | None = None
    android_version: str | None = None
    sdk_level: str | None = None
    build_number: str | None = None
    build_fingerprint: str | None = None
    security_patch: str | None = None
    cpu_abi: str | None = None
    cpu_cores: int | None = None
    battery_level: int | None = None
    battery_status: str | None = None
    ram_total_gb: float | None = None
    ram_free_gb: float | None = None
    storage_total_gb: float | None = None
    storage_free_gb: float | None = None
    usb_vid: int | None = None
    usb_pid: int | None = None
    is_rooted: bool = False
    is_unlocked: bool = False
    is_usb_debug_enabled: bool = False
    bootloader_status: str | None = None
    display_name: str | None = None
    properties: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def vid_pid_label(self) -> str:
        if self.usb_vid is not None and self.usb_pid is not None:
            return f"{self.usb_vid:04X}:{self.usb_pid:04X}"
        return ""


class UsbIdentifier(BaseModel):
    """USB Vendor ID / Product ID pair."""

    vid: int
    pid: int = 0

    def match(self, vid: int, pid: int) -> bool:
        return self.vid == vid and (self.pid == 0 or self.pid == pid)

    @property
    def label(self) -> str:
        return f"{self.vid:04X}:{self.pid:04X}"


class PortInfo(BaseModel):
    """Information about a serial COM port."""

    device: str
    description: str = ""
    hwid: str = ""
    vid: int | None = None
    pid: int | None = None


class ActionResult(BaseModel):
    """Result of an operation on a device."""

    success: bool
    action: str
    device_serial: str | None = None
    output: str | None = None
    error: str | None = None
    duration_ms: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        if self.success:
            return f"[OK] {self.action}: {self.output or 'Success'} ({self.duration_ms:.0f}ms)"
        return f"[FAIL] {self.action}: {self.error or 'Unknown error'}"


class DeviceSnapshot(BaseModel):
    """Full device snapshot for comparison and history."""

    info: DeviceInfo
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    connection_type: str | None = None
    fastboot_vars: dict[str, str] = Field(default_factory=dict)
    partition_layout: list[str] = Field(default_factory=list)


# ─── Device ABC ──────────────────────────────────────────────────────────────


class Device(ABC):
    """Abstract base class for all device types."""

    def __init__(self, identifier: str, device_type: DeviceType = DeviceType.UNKNOWN) -> None:
        self.identifier = identifier
        self._type = device_type
        self._status = DeviceStatus.DISCONNECTED
        self._info: DeviceInfo | None = None
        self._last_error: str | None = None
        self._on_disconnect: list[Callable[[Device], None]] = []

    @property
    def type(self) -> DeviceType:
        return self._type

    @property
    def status(self) -> DeviceStatus:
        return self._status

    @property
    def info(self) -> DeviceInfo | None:
        return self._info

    @property
    def is_connected(self) -> bool:
        return self._status == DeviceStatus.CONNECTED

    @property
    def serial(self) -> str:
        return self.identifier

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @abstractmethod
    async def connect(self) -> bool: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_info(self) -> DeviceInfo: ...

    @abstractmethod
    async def execute(self, command: str, timeout: int = 30) -> ActionResult: ...

    async def read_data(self, path: str, offset: int = 0, size: int = 1024) -> bytes:
        raise NotImplementedError(f"read_data not supported for {self._type.value}")

    async def write_data(self, path: str, data: bytes) -> bool:
        raise NotImplementedError(f"write_data not supported for {self._type.value}")

    async def get_partitions(self) -> list[str]:
        return []

    async def reboot(self, mode: str | None = None) -> bool:
        cmd = f"reboot {mode}" if mode else "reboot"
        result = await self.execute(cmd)
        return result.success

    async def backup(self, output_path: str) -> ActionResult:
        return ActionResult(
            success=False, action="backup", device_serial=self.serial,
            error="Backup not implemented for this device type",
        )

    async def restore(self, backup_path: str) -> ActionResult:
        return ActionResult(
            success=False, action="restore", device_serial=self.serial,
            error="Restore not implemented for this device type",
        )

    def register_disconnect_callback(self, cb: Callable[[Device], None]) -> None:
        self._on_disconnect.append(cb)

    def _mark_disconnected(self) -> None:
        self._status = DeviceStatus.DISCONNECTED
        for cb in self._on_disconnect:
            with contextlib.suppress(Exception):
                cb(self)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(serial={self.serial}, type={self._type.value}, status={self._status.value})"


# ─── Device Registry ─────────────────────────────────────────────────────────


class DeviceRegistry:
    """Maps DeviceType → Device class for factory instantiation."""

    _registry: dict[DeviceType, type[Device]] = {}

    @classmethod
    def register(cls, device_type: DeviceType, device_cls: type[Device]) -> None:
        cls._registry[device_type] = device_cls

    @classmethod
    def create(cls, device_type: DeviceType, identifier: str, **kwargs: Any) -> Device:
        device_cls = cls._registry.get(device_type)
        if device_cls is None:
            raise ValueError(f"No device class registered for {device_type.value}")
        return device_cls(identifier, device_type=device_type, **kwargs)

    @classmethod
    def get_class(cls, device_type: DeviceType) -> type[Device]:
        device_cls = cls._registry.get(device_type)
        if device_cls is None:
            raise ValueError(f"No device class registered for {device_type.value}")
        return device_cls

    @classmethod
    def supported_types(cls) -> list[DeviceType]:
        return list(cls._registry.keys())


# ─── USB Detection Map ───────────────────────────────────────────────────────

# Known USB VID/PID pairs to DeviceType mapping
USB_DEVICE_MAP: dict[tuple[int, int], DeviceType] = {
    (0x05C6, 0x9008): DeviceType.QUALCOMM_EDL,
    (0x05C6, 0x9006): DeviceType.DIAG,
    (0x05C6, 0x901D): DeviceType.DIAG,
    (0x05C6, 0x900E): DeviceType.QUALCOMM_EDL,
    (0x0E8D, 0x0003): DeviceType.MTK_BROM,
    (0x0E8D, 0x2000): DeviceType.MTK_BROM,
    (0x0E8D, 0x3000): DeviceType.MTK_BROM,
    (0x04E8, 0x685D): DeviceType.SAMSUNG_ODIN,
    (0x04E8, 0x68C3): DeviceType.SAMSUNG_ODIN,
    (0x04E8, 0x6860): DeviceType.SAMSUNG_ODIN,
    (0x05AC, 0x1227): DeviceType.APPLE_DFU,
    (0x05AC, 0x1281): DeviceType.APPLE_DFU,
    (0x2207, 0x0000): DeviceType.ROCKCHIP_MASKROM,
    (0x1F3A, 0x0000): DeviceType.ALLWINNER_FEL,
    (0x1782, 0x4D00): DeviceType.UNISOC_SPD,
    (0x0FCE, 0xADE5): DeviceType.QUALCOMM_EDL,  # Sony S1 Flashmode
    (0x0FCE, 0x0DDE): DeviceType.FASTBOOT,       # Sony Fastboot
    (0x18D1, 0x4EE0): DeviceType.FASTBOOT,       # Google Fastboot
    (0x18D1, 0x0D00): DeviceType.ANDROID,
    (0x0FCE, 0x0000): DeviceType.ANDROID,
    (0x12D1, 0x0000): DeviceType.ANDROID,
    (0x18D1, 0x0000): DeviceType.ANDROID,
}

# USB VID → vendor name
VID_VENDOR_MAP: dict[int, str] = {
    0x05C6: "Qualcomm",
    0x0E8D: "MediaTek",
    0x04E8: "Samsung",
    0x05AC: "Apple",
    0x2207: "Rockchip",
    0x1F3A: "Allwinner",
    0x1782: "Unisoc/Spreadtrum",
    0x0FCE: "Sony",
    0x18D1: "Google",
    0x12D1: "HiSilicon",
}


def detect_device_type_from_usb(vid: int, pid: int) -> DeviceType:
    """Determine device type from USB VID/PID."""
    # Exact match first
    key = (vid, pid)
    if key in USB_DEVICE_MAP:
        return USB_DEVICE_MAP[key]
    # Wildcard match (pid=0)
    for (map_vid, map_pid), dtype in USB_DEVICE_MAP.items():
        if map_vid == vid and map_pid == 0:
            return dtype
    return DeviceType.ANDROID


def get_vendor_name(vid: int) -> str:
    return VID_VENDOR_MAP.get(vid, f"0x{vid:04X}")

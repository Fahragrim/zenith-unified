"""Device discovery engine.

Scans USB, serial, ADB, and Fastboot buses to detect connected devices.
Combines xperiatool2's discovery.py with OpencodeDeviceTool's protocol_negotiator.
"""

from __future__ import annotations

import contextlib
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class ConnectionMode(str, Enum):
    UNKNOWN = "unknown"
    ADB = "adb"
    ADB_UNAUTHORIZED = "adb_unauthorized"
    ADB_WIFI = "adb_wifi"
    RECOVERY_ADB = "recovery_adb"
    SIDELOAD = "sideload"
    FASTBOOT = "fastboot"
    FASTBOOTD = "fastbootd"
    QUALCOMM_EDL = "qualcomm_edl"
    QUALCOMM_DIAG = "qualcomm_diag"
    SONY_FLASHMODE = "sony_flashmode"
    SONY_FASTBOOT = "sony_fastboot"
    MTK_BROM = "mtk_brom"
    SAMSUNG_DOWNLOAD = "samsung_download"
    SPRD_BOOTROM = "sprd_bootrom"
    SPRD_DIAG = "sprd_diag"
    ROCKCHIP_MASKROM = "rockchip_maskrom"
    ALLWINNER_FEL = "allwinner_fel"
    APPLE_DFU = "apple_dfu"


@dataclass
class UsbEndpoint:
    vid: int
    pid: int
    mode: ConnectionMode
    label: str
    suggested_action: str = ""


@dataclass
class DiscoveryResult:
    modes: list[ConnectionMode] = field(default_factory=list)
    usb_hits: list[UsbEndpoint] = field(default_factory=list)
    serial_ports: list[dict[str, Any]] = field(default_factory=list)
    adb_devices: list[dict[str, str]] = field(default_factory=list)
    fastboot_devices: list[str] = field(default_factory=list)
    matched_profiles: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)
    primary_mode: ConnectionMode = ConnectionMode.UNKNOWN
    suggested_playbook: str = ""
    fastboot_is_userspace: bool | None = None

    def to_display_text(self) -> str:
        return "\n".join(self.summary_lines) if self.summary_lines else "No devices detected."


# Known USB signatures for device mode detection
USB_SIGNATURES: list[UsbEndpoint] = [
    UsbEndpoint(0x05C6, 0x9008, ConnectionMode.QUALCOMM_EDL, "Qualcomm EDL 9008",
                "Open EDL playbook — match firehose to bootloader build"),
    UsbEndpoint(0x05C6, 0x900E, ConnectionMode.QUALCOMM_EDL, "Qualcomm EDL 900E",
                "Try memory dump or power-cycle"),
    UsbEndpoint(0x05C6, 0x9006, ConnectionMode.QUALCOMM_DIAG, "Qualcomm Diag 9006",
                "Use QPST or AT command console"),
    UsbEndpoint(0x0FCE, 0xADE5, ConnectionMode.SONY_FLASHMODE, "Sony Flashmode S1",
                "Launch Newflasher with firmware folder"),
    UsbEndpoint(0x0FCE, 0x0DDE, ConnectionMode.SONY_FASTBOOT, "Sony Fastboot",
                "Run fastboot getvar all — check unlock state"),
    UsbEndpoint(0x1782, 0x4D00, ConnectionMode.SPRD_BOOTROM, "Unisoc SPRD BootROM",
                "Open Nokia C32 SPRD flash/FRP playbook"),
    UsbEndpoint(0x0E8D, 0x0003, ConnectionMode.MTK_BROM, "MediaTek BROM",
                "Use mtkclient or BROM handshake probe"),
    UsbEndpoint(0x0E8D, 0x2000, ConnectionMode.MTK_BROM, "MediaTek BROM DA",
                "MediaTek Download Agent active"),
    UsbEndpoint(0x04E8, 0x685D, ConnectionMode.SAMSUNG_DOWNLOAD, "Samsung Download",
                "Use Odin/Heimdall"),
    UsbEndpoint(0x05AC, 0x1227, ConnectionMode.APPLE_DFU, "Apple DFU",
                "Use libimobiledevice for recovery"),
    UsbEndpoint(0x2207, 0x0000, ConnectionMode.ROCKCHIP_MASKROM, "Rockchip MaskROM",
                "Use rkdeveloptool"),
    UsbEndpoint(0x1F3A, 0x0000, ConnectionMode.ALLWINNER_FEL, "Allwinner FEL",
                "Use sunxi-fel"),
]

MODE_PRIORITY: list[ConnectionMode] = [
    ConnectionMode.QUALCOMM_EDL,
    ConnectionMode.SPRD_BOOTROM,
    ConnectionMode.MTK_BROM,
    ConnectionMode.APPLE_DFU,
    ConnectionMode.SONY_FLASHMODE,
    ConnectionMode.SAMSUNG_DOWNLOAD,
    ConnectionMode.ALLWINNER_FEL,
    ConnectionMode.ROCKCHIP_MASKROM,
    ConnectionMode.QUALCOMM_DIAG,
    ConnectionMode.SIDELOAD,
    ConnectionMode.RECOVERY_ADB,
    ConnectionMode.FASTBOOTD,
    ConnectionMode.SONY_FASTBOOT,
    ConnectionMode.FASTBOOT,
    ConnectionMode.ADB_UNAUTHORIZED,
    ConnectionMode.ADB_WIFI,
    ConnectionMode.ADB,
]


# ─── USB detection via pyusb ──────────────────────────────────────────────

def scan_usb_pyusb() -> list[UsbEndpoint]:
    """Scan USB bus via pyusb for known device signatures."""
    hits: list[UsbEndpoint] = []
    try:
        import usb.core  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("pyusb not available — USB scan skipped")
        return hits

    try:
        for sig in USB_SIGNATURES:
            dev = usb.core.find(idVendor=sig.vid, idProduct=sig.pid)
            if dev is not None:
                hits.append(sig)
                logger.info(f"USB: {sig.label} ({sig.vid:04X}:{sig.pid:04X})")
    except Exception as e:
        logger.debug(f"USB scan error (expected without devices): {e}")
    return hits


# ─── Serial port detection ────────────────────────────────────────────────

SPRD_DIAG_KEYWORDS = ("SPRD", "SCI-USB", "U2S Diag", "Spreadtrum", "UNISOC")
SPRD_FDL1_KEYWORDS = ("FDL1", "FDL 1")
SPRD_FDL2_KEYWORDS = ("FDL2", "FDL 2", "DOWNLOAD")


def _parse_hwid(hwid: str) -> tuple[int | None, int | None]:
    vid_m = re.search(r"VID[_:]([0-9A-Fa-f]{4})", hwid, re.I)
    pid_m = re.search(r"PID[_:]([0-9A-Fa-f]{4})", hwid, re.I)
    vid = int(vid_m.group(1), 16) if vid_m else None
    pid = int(pid_m.group(1), 16) if pid_m else None
    return vid, pid


def scan_serial_ports() -> list[dict[str, Any]]:
    """Scan serial/COM ports for diagnostic devices."""
    hits: list[dict[str, Any]] = []
    try:
        import serial.tools.list_ports
    except ImportError:
        return hits

    for port in serial.tools.list_ports.comports():
        vid, pid = _parse_hwid(port.hwid or "")
        entry: dict[str, Any] = {
            "device": port.device,
            "description": port.description or "",
            "hwid": port.hwid or "",
            "vid": vid,
            "pid": pid,
        }
        desc_upper = (port.description or "").upper()
        if vid == 0x1782 and pid == 0x4D00:
            entry["mode"] = ConnectionMode.SPRD_BOOTROM.value
        elif any(k in desc_upper for k in SPRD_FDL2_KEYWORDS):
            entry["mode"] = "sprd_fdl2"
        elif any(k in desc_upper for k in SPRD_FDL1_KEYWORDS):
            entry["mode"] = "sprd_fdl1"
        elif any(k in desc_upper for k in SPRD_DIAG_KEYWORDS):
            entry["mode"] = ConnectionMode.SPRD_DIAG.value
        elif "QDLOADER" in desc_upper or "9008" in desc_upper:
            entry["mode"] = ConnectionMode.QUALCOMM_EDL.value
        else:
            entry["mode"] = ConnectionMode.UNKNOWN.value
        hits.append(entry)
        if entry["mode"] != ConnectionMode.UNKNOWN.value:
            logger.info(f"Serial: {port.device} — {port.description} [{entry['mode']}]")
    return hits


# ─── ADB detection ────────────────────────────────────────────────────────

def scan_adb() -> list[dict[str, str]]:
    """Scan ADB for connected devices."""
    devices: list[dict[str, str]] = []
    try:
        result = subprocess.run(
            ["adb", "devices", "-l"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                info: dict[str, str] = {"serial": parts[0], "state": "device"}
                for extra in parts[2:]:
                    if ":" in extra:
                        k, v = extra.split(":", 1)
                        info[k] = v
                devices.append(info)
                logger.info(f"ADB: {parts[0]} (device)")
            elif len(parts) >= 2 and parts[1] == "unauthorized":
                devices.append({"serial": parts[0], "state": "unauthorized"})
                logger.info(f"ADB: {parts[0]} (unauthorized)")
            elif len(parts) >= 2 and parts[1] in ("recovery", "sideload"):
                devices.append({"serial": parts[0], "state": parts[1]})
                logger.info(f"ADB: {parts[0]} ({parts[1]})")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        logger.debug(f"ADB scan error: {e}")
    return devices


# ─── Fastboot detection ───────────────────────────────────────────────────

def scan_fastboot() -> list[str]:
    """Scan Fastboot for connected devices."""
    devices: list[str] = []
    try:
        result = subprocess.run(
            ["fastboot", "devices"], capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if parts:
                devices.append(parts[0])
                logger.info(f"Fastboot: {parts[0]}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        logger.debug(f"Fastboot scan error: {e}")
    return devices


# ─── Combined discovery ───────────────────────────────────────────────────

def _pick_primary_mode(modes: list[ConnectionMode]) -> ConnectionMode:
    for mode in MODE_PRIORITY:
        if mode in modes:
            return mode
    return modes[0] if modes else ConnectionMode.UNKNOWN


def _suggest_playbook(modes: list[ConnectionMode]) -> str:
    if ConnectionMode.SPRD_BOOTROM in modes:
        return "nokia-c32-sprd-frp"
    if ConnectionMode.SONY_FLASHMODE in modes:
        return "sony-xz2-frp-newflasher"
    if ConnectionMode.QUALCOMM_EDL in modes:
        return "sony-xz2-frp-edl"
    if ConnectionMode.SONY_FASTBOOT in modes or ConnectionMode.FASTBOOT in modes:
        return "sony-xz2-frp-fastboot"
    if ConnectionMode.SAMSUNG_DOWNLOAD in modes:
        return "samsung-odin-firmware-rescue"
    if ConnectionMode.MTK_BROM in modes:
        return "mtk-brom-bypass"
    if ConnectionMode.APPLE_DFU in modes:
        return "apple-dfu-triage"
    return ""


def _match_profiles(modes: list[ConnectionMode]) -> list[str]:
    profiles: list[str] = []
    sony_modes = {
        ConnectionMode.SONY_FASTBOOT, ConnectionMode.SONY_FLASHMODE,
        ConnectionMode.QUALCOMM_EDL, ConnectionMode.ADB, ConnectionMode.FASTBOOT,
    }
    nokia_modes = {ConnectionMode.SPRD_BOOTROM, ConnectionMode.SPRD_DIAG, ConnectionMode.ADB}
    samsung_modes = {ConnectionMode.SAMSUNG_DOWNLOAD, ConnectionMode.ADB}
    mtk_modes = {ConnectionMode.MTK_BROM, ConnectionMode.ADB}
    apple_modes = {ConnectionMode.APPLE_DFU}

    if modes and any(m in sony_modes for m in modes):
        profiles.append("sony_xz2_h8266")
    if modes and any(m in nokia_modes for m in modes):
        profiles.append("nokia_c32_ta1534")
    if modes and any(m in samsung_modes for m in modes):
        profiles.append("samsung_generic")
    if modes and any(m in mtk_modes for m in modes):
        profiles.append("mediatek_generic")
    if modes and any(m in apple_modes for m in modes):
        profiles.append("apple_generic")
    return profiles


def run_discovery(
    adb_devices: list[dict[str, str]] | None = None,
    fastboot_devices: list[str] | None = None,
    fastboot_is_userspace: bool | None = None,
) -> DiscoveryResult:
    """Run a full discovery scan across all transport layers."""
    result = DiscoveryResult()
    result.adb_devices = adb_devices if adb_devices is not None else scan_adb()
    result.fastboot_devices = fastboot_devices if fastboot_devices is not None else scan_fastboot()
    result.fastboot_is_userspace = fastboot_is_userspace
    result.serial_ports = scan_serial_ports()
    result.usb_hits = scan_usb_pyusb()

    modes: list[ConnectionMode] = []

    for dev in result.adb_devices:
        state = dev.get("state", "")
        serial = dev.get("serial", "")
        if state == "unauthorized":
            modes.append(ConnectionMode.ADB_UNAUTHORIZED)
        elif state == "recovery":
            modes.append(ConnectionMode.RECOVERY_ADB)
        elif state == "sideload":
            modes.append(ConnectionMode.SIDELOAD)
        elif state == "device":
            if ":" in serial:
                modes.append(ConnectionMode.ADB_WIFI)
            modes.append(ConnectionMode.ADB)

    if result.fastboot_devices:
        modes.append(ConnectionMode.FASTBOOTD if fastboot_is_userspace else ConnectionMode.FASTBOOT)

    for hit in result.usb_hits:
        modes.append(hit.mode)

    for port in result.serial_ports:
        mode_str = port.get("mode", "")
        if mode_str and mode_str != "unknown":
            with contextlib.suppress(ValueError):
                modes.append(ConnectionMode(mode_str))

    result.modes = list(dict.fromkeys(modes))  # Deduplicated, preserving order

    # Build summary
    lines: list[str] = ["=== ZENITH DEVICE DISCOVERY ===", ""]

    if result.adb_devices:
        lines.append("[ADB]")
        for d in result.adb_devices:
            lines.append(f"  {d.get('serial', '?')}  state={d.get('state')}  model={d.get('model', '?')}")
        lines.append("")

    if result.fastboot_devices:
        fb_label = "FASTBOOTD" if fastboot_is_userspace else "FASTBOOT"
        lines.append(f"[{fb_label}]")
        for s in result.fastboot_devices:
            lines.append(f"  {s}")
        lines.append("")

    if result.usb_hits:
        lines.append("[USB MODES]")
        for h in result.usb_hits:
            lines.append(f"  [{h.label}] VID={h.vid:04X} PID={h.pid:04X}")
            if h.suggested_action:
                lines.append(f"    -> {h.suggested_action}")
        lines.append("")

    interesting_ports = [p for p in result.serial_ports if p.get("mode") != "unknown"]
    if interesting_ports:
        lines.append("[SERIAL]")
        for p in interesting_ports:
            lines.append(f"  {p['device']} — {p['description']} ({p['mode']})")
        lines.append("")

    result.matched_profiles = _match_profiles(result.modes)
    if result.matched_profiles:
        lines.append("[MATCHED PROFILES]")
        for pid in result.matched_profiles:
            lines.append(f"  {pid}")
        lines.append("")

    if result.modes:
        result.primary_mode = _pick_primary_mode(result.modes)
        result.suggested_playbook = _suggest_playbook(result.modes)
        lines.append(f"[PRIMARY MODE] {result.primary_mode.value}")
        if result.suggested_playbook:
            lines.append(f"[SUGGESTED PLAYBOOK] {result.suggested_playbook}")
    else:
        lines.append("No supported device modes detected. Check USB drivers and cable.")

    result.summary_lines = lines
    return result

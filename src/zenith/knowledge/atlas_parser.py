"""ATLAS Parser — extracts structured data from DEEP_ATLAS.md.

Parses the master knowledge base into queryable objects:
- SoC information (boot chains, security features, recovery modes)
- Communication protocols (ADB, Fastboot, EDL, BROM, etc.)
- Repair playbooks with steps
- Tool matrix with download info
- Secret dialer codes per manufacturer
- Driver installation guides
- Test point locations
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Tier(Enum):
    TIER_0 = "foundations"
    TIER_1 = "silicon_atlases"
    TIER_2 = "universal_boot"
    TIER_3 = "security"
    TIER_4 = "storage"
    TIER_5 = "communications"
    TIER_6 = "hardware_forensics"
    TIER_7 = "ai_diagnostics"
    TIER_8 = "real_world_playbooks"
    TIER_9 = "lanfear_platform"
    APPENDIX_A = "tool_matrix"
    APPENDIX_B = "drivers"
    APPENDIX_C = "test_points"


@dataclass
class SOCInfo:
    name: str
    manufacturer: str
    boot_chain: list[str] = field(default_factory=list)
    security_features: list[str] = field(default_factory=list)
    recovery_modes: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    test_points: dict[str, str] = field(default_factory=dict)
    e_fuses: list[str] = field(default_factory=list)
    partitions: list[str] = field(default_factory=list)


@dataclass
class Protocol:
    name: str
    description: str
    soc_families: list[str] = field(default_factory=list)
    usb_vid: str | None = None
    usb_pid: str | None = None
    commands: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    verification_method: str | None = None


@dataclass
class Playbook:
    id: str
    title: str
    symptom: str
    soc: str | None = None
    risk_level: str = "medium"
    prerequisites: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    troubleshooting: dict[str, str] = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    category: str
    platform: list[str] = field(default_factory=list)
    cost: str = ""
    function: str = ""
    open_source: bool = False


@dataclass
class AtlasData:
    tiers: dict[str, dict[str, Any]] = field(default_factory=dict)
    socs: dict[str, SOCInfo] = field(default_factory=dict)
    protocols: dict[str, Protocol] = field(default_factory=dict)
    playbooks: dict[str, Playbook] = field(default_factory=dict)
    tools: dict[str, Tool] = field(default_factory=dict)
    secret_codes: dict[str, dict[str, str]] = field(default_factory=dict)
    test_points: dict[str, dict[str, str]] = field(default_factory=dict)


class AtlasParser:
    """Parser for DEEP_ATLAS.md that extracts structured knowledge."""

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB limit

    def __init__(self, atlas_path: Path) -> None:
        self.atlas_path = atlas_path
        self._content: str | None = None
        self._data: AtlasData | None = None
        self._mtime: float | None = None

    @property
    def content(self) -> str:
        if self._content is None:
            self._reload_content()
        assert self._content is not None
        return self._content

    def _reload_content(self) -> None:
        path = self.atlas_path
        if not path.exists():
            self._content = ""
            self._mtime = None
            return
        stat = path.stat()
        if self._mtime is not None and stat.st_mtime <= self._mtime and self._content is not None:
            return
        if stat.st_size > self.MAX_FILE_SIZE:
            raise ValueError(f"DEEP_ATLAS.md exceeds {self.MAX_FILE_SIZE // 1024 // 1024}MB limit: {stat.st_size} bytes")
        self._content = path.read_text(encoding="utf-8")
        self._mtime = stat.st_mtime

    @property
    def data(self) -> AtlasData:
        if self._data is None:
            self._data = self.parse()
        return self._data

    def reload(self) -> AtlasData:
        """Force re-parse from disk, invalidating caches."""
        self._content = None
        self._mtime = None
        self._data = None
        return self.data

    def parse(self) -> AtlasData:
        data = AtlasData()
        self._parse_socs(data)
        self._parse_protocols(data)
        self._parse_playbooks(data)
        self._parse_tools(data)
        self._parse_secret_codes(data)
        self._apply_defaults(data)
        self._validate(data)
        return data

    def _validate(self, data: AtlasData) -> None:
        valid_risk = {"low", "medium", "high", "critical"}
        for pb in data.playbooks.values():
            if pb.risk_level.lower() not in valid_risk:
                pb.risk_level = "medium"
        for proto in data.protocols.values():
            if proto.risk_level.lower() not in valid_risk:
                proto.risk_level = "medium"
            if proto.usb_vid:
                try:
                    int(proto.usb_vid, 16)
                except (ValueError, TypeError):
                    proto.usb_vid = None
            if proto.usb_pid:
                try:
                    int(proto.usb_pid, 16)
                except (ValueError, TypeError):
                    proto.usb_pid = None

    def _extract_section(self, content: str, title: str) -> str | None:
        lines = content.split("\n")
        start = -1
        heading_level = 0
        escaped = re.escape(title)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.search(rf"^#+\s*.*?{escaped}", stripped, re.IGNORECASE):
                start = i
                heading_level = len(stripped) - len(stripped.lstrip("#"))
                break
        if start == -1:
            return None
        result_lines: list[str] = []
        for j in range(start, len(lines)):
            stripped = lines[j].strip()
            if j > start and stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip("#"))
                if level <= heading_level and lines[j].strip() != lines[start].strip():
                    break
            result_lines.append(lines[j])
        return "\n".join(result_lines).strip()

    def _parse_socs(self, data: AtlasData) -> None:
        volume_map = {
            "qualcomm": ("Qualcomm", "Qualcomm Snapdragon"),
            "mediatek": ("MediaTek", "MediaTek Dimensity/Helio"),
            "exynos": ("Samsung", "Samsung Exynos"),
            "tensor": ("Google", "Google Tensor"),
            "kirin": ("HiSilicon", "HiSilicon Kirin"),
            "unisoc": ("Unisoc", "Unisoc/Spreadtrum"),
            "rockchip": ("Rockchip", "Rockchip"),
            "allwinner": ("Allwinner", "Allwinner"),
            "apple": ("Apple", "Apple Silicon"),
        }
        for key, (manufacturer, name) in volume_map.items():
            soc = SOCInfo(name=name, manufacturer=manufacturer)
            section = self._extract_section(self.content, name.split()[-1])
            if not section:
                section = self._extract_section(self.content, manufacturer)
            if section:
                # Boot chain from lists
                for line in section.split("\n"):
                    line_clean = line.strip()
                    if "**" in line_clean and ("—" in line_clean or ":" in line_clean):
                        parts = re.split(r"\*\*", line_clean)
                        if len(parts) >= 2:
                            feature = parts[1].strip().lstrip("—: ").rstrip("—: ")
                            if feature:
                                soc.boot_chain.append(feature)
                    elif line_clean.startswith(("-", "*")) and len(line_clean) > 5:
                        item = line_clean.lstrip("-* ").strip()
                        if any(kw in item.lower() for kw in ("edl", "brom", "fastboot", "odin", "download", "dfu", "fel", "maskrom", "recovery")):
                            soc.recovery_modes.append(item)
                if not soc.recovery_modes:
                    defaults = {
                        "qualcomm": ["EDL (Emergency Download Mode)", "Fastboot", "Recovery", "Diag Mode"],
                        "mediatek": ["BROM Mode", "Preloader Mode", "Fastboot", "Meta Mode"],
                        "exynos": ["Download/Odin Mode", "Fastboot"],
                        "tensor": ["Rescue Mode", "Fastboot", "DFU"],
                        "kirin": ["eRecovery", "USB COM 1.0"],
                        "unisoc": ["SPD Upgrade Mode"],
                        "rockchip": ["MaskROM Mode"],
                        "allwinner": ["FEL Mode"],
                        "apple": ["DFU Mode", "Recovery Mode"],
                    }
                    soc.recovery_modes = defaults.get(key, [])
            data.socs[key] = soc

    def _parse_protocols(self, data: AtlasData) -> None:
        defaults: list[Protocol] = [
            Protocol("ADB", "Android Debug Bridge", ["qualcomm", "mediatek", "exynos", "tensor", "kirin", "unisoc"],
                     commands=["devices", "shell", "push", "pull", "logcat", "reboot", "reboot bootloader", "reboot edl"]),
            Protocol("Fastboot", "Bootloader protocol for flashing Android devices", ["qualcomm", "mediatek", "exynos", "tensor"],
                     commands=["devices", "flash", "erase", "boot", "reboot", "getvar", "oem unlock", "flashing unlock"]),
            Protocol("EDL", "Qualcomm Emergency Download Mode", ["qualcomm"],
                     usb_vid="05C6", usb_pid="9008", risk_level="high",
                     commands=["printgpt", "r", "w", "z", "reset"]),
            Protocol("BROM", "MediaTek BootROM mode", ["mediatek"],
                     usb_vid="0E8D", risk_level="high",
                     commands=["printgpt", "r", "w", "e"]),
            Protocol("Odin", "Samsung Download Mode (Thor protocol)", ["exynos"],
                     usb_vid="04E8", risk_level="high",
                     commands=["flash", "print-pit"]),
            Protocol("DFU", "Apple Device Firmware Update", ["apple"],
                     usb_vid="05AC", usb_pid="1227", risk_level="high"),
        ]
        for p in defaults:
            data.protocols[p.name.lower()] = p

    def _parse_playbooks(self, data: AtlasData) -> None:
        defaults: list[tuple[Any, ...]] = [
            ("hard-brick-qualcomm", "Hard Brick — Qualcomm", "hard-brick", "qualcomm", "high", [
                {"step": 1, "desc": "Identify 9008 in Device Manager"},
                {"step": 2, "desc": "Force EDL via test point or cable"},
                {"step": 3, "desc": "Install Qualcomm 9008 driver"},
                {"step": 4, "desc": "Flash firmware via edl or QFIL"},
                {"step": 5, "desc": "Verify: disconnect USB, reboot"},
            ]),
            ("hard-brick-mediatek", "Hard Brick — MediaTek", "hard-brick", "mediatek", "high", [
                {"step": 1, "desc": "Identify MTK PreLoader USB VCOM"},
                {"step": 2, "desc": "Force BROM via Volume buttons + USB"},
                {"step": 3, "desc": "Install MTK VCOM driver via Zadig"},
                {"step": 4, "desc": "Bypass DA: python mtk payload"},
                {"step": 5, "desc": "Flash: python mtk w boot boot.img"},
            ]),
            ("soft-brick-bootloop", "Soft Brick / Bootloop", "bootloop", None, "medium", [
                {"step": 1, "desc": "Try Recovery Mode: Vol Up + Power"},
                {"step": 2, "desc": "Wipe cache / factory reset"},
                {"step": 3, "desc": "If fails: fastboot flash boot/recovery"},
                {"step": 4, "desc": "If all fails: proceed to hard-brick procedure"},
            ]),
            ("frp-bypass", "FRP Bypass", "frp-lock", None, "high", [
                {"step": 1, "desc": "Identify Android version"},
                {"step": 2, "desc": "Android 5-7: SamFw Tool or Octoplus"},
                {"step": 3, "desc": "Android 8-10: Talkback bypass or Odin"},
                {"step": 4, "desc": "Android 11+: EDL/BROM → format userdata"},
                {"step": 5, "desc": "Erase userdata via EDL (Qualcomm): edl w z --partition=userdata"},
                {"step": 6, "desc": "Erase userdata via BROM (MediaTek): python mtk e userdata"},
            ]),
            ("bootloader-unlock", "Bootloader Unlock", "bootloader-locked", None, "medium", [
                {"step": 1, "desc": "Enable Developer Options: tap Build Number 7x"},
                {"step": 2, "desc": "Enable OEM Unlock in Developer Options"},
                {"step": 3, "desc": "Enable USB Debugging"},
                {"step": 4, "desc": "Reboot to fastboot: adb reboot bootloader"},
                {"step": 5, "desc": "Unlock: fastboot flashing unlock"},
                {"step": 6, "desc": "WARNING: Erases ALL data!"},
            ]),
            ("apple-dfu-triage", "Apple DFU Triage & IPSW Flash", "dfu-mode", "apple", "high", [
                {"step": 1, "desc": "Connect to Mac (Finder) or PC (Apple Devices)"},
                {"step": 2, "desc": "Enter DFU: specific button sequence"},
                {"step": 3, "desc": "Confirm: black screen, computer detects DFU"},
                {"step": 4, "desc": "Restore with IPSW via Finder/Apple Devices"},
            ]),
            ("samsung-odin-rescue", "Samsung Odin Firmware Rescue", "firmware-corruption", "exynos", "high", [
                {"step": 1, "desc": "Power off device"},
                {"step": 2, "desc": "Enter Download: Vol Up + Vol Down + USB"},
                {"step": 3, "desc": "Open Odin3, verify blue COM port"},
                {"step": 4, "desc": "Load BL, AP, CP, CSC firmware"},
                {"step": 5, "desc": "Start flash, do not interrupt"},
            ]),
            ("mtk-brom-bypass", "MTK BROM Bypass", "brom-access", "mediatek", "high", [
                {"step": 1, "desc": "Install libusb-win32 via Zadig on MTK port"},
                {"step": 2, "desc": "Run mtkclient payload"},
                {"step": 3, "desc": "Hold Vol Up + Down, connect USB"},
                {"step": 4, "desc": "mtkclient captures BROM, injects bypass payload"},
                {"step": 5, "desc": "Execute: python mtk printgpt"},
            ]),
        ]
        for pb_id, title, symptom, soc, risk, steps in defaults:
            data.playbooks[pb_id] = Playbook(
                id=pb_id, title=title, symptom=symptom, soc=soc,
                steps=steps, risk_level=risk,
            )

    def _parse_tools(self, data: AtlasData) -> None:
        defaults: list[Tool] = [
            Tool("edl", "Qualcomm EDL", ["Python"], "Free/Open Source", "Partition dump/flash, FRP bypass via firehose", True),
            Tool("mtkclient", "MediaTek BROM", ["Python"], "Free/Open Source", "SLA/DAA bypass, dump, flash, unlock", True),
            Tool("Heimdall", "Samsung Odin", ["Cross-platform"], "Free/Open Source", "Open source Odin alternative", True),
            Tool("QDL", "Qualcomm EDL", ["Linux"], "Free/Open Source", "Qualcomm Download tool", True),
            Tool("SP Flash Tool", "MediaTek Preloader", ["Windows"], "Free (official)", "Scatter firmware flashing", False),
            Tool("ResearchDownload", "Unisoc SPD", ["Windows"], "Free (official)", ".pac firmware flashing", False),
            Tool("Odin", "Samsung Download", ["Windows"], "Free (leaked)", "Samsung proprietary flash tool", False),
            Tool("Android Flash Tool", "Fastboot/Rescue", ["Web (WebUSB)"], "Free", "Google Pixel restore", True),
        ]
        for t in defaults:
            data.tools[t.name] = t

    def _parse_secret_codes(self, data: AtlasData) -> None:
        codes: dict[str, dict[str, str]] = {
            "samsung": {"*#0*#": "Hardware Diagnostic Menu", "*#9900#": "SysDump Menu", "*#0808#": "USB Settings",
                        "*#06#": "IMEI", "*#0228#": "Battery Status"},
            "xiaomi": {"*#*#64663#*#*": "CIT Mode", "*#*#6484#*#*": "QC Test"},
            "oneplus": {"*#800#": "Feedback/LogKit", "*#899#": "Engineer Mode"},
            "google_pixel": {"*#*#4636#*#*": "Testing Menu"},
            "sony": {"*#*#7378423#*#*": "Service Menu (bootloader, DRM keys)"},
            "huawei": {"*#*#2846579#*#*": "Project Menu"},
            "universal": {"*#*#4636#*#*": "Testing Menu", "*#06#": "IMEI"},
        }
        data.secret_codes = codes

    def _apply_defaults(self, data: AtlasData) -> None:
        if not data.socs:
            for key, (man, name) in {"qualcomm": ("Qualcomm", "Qualcomm Snapdragon"), "mediatek": ("MediaTek", "MediaTek")}.items():
                data.socs[key] = SOCInfo(name=name, manufacturer=man)

    def to_json(self) -> str:
        import json
        return json.dumps(self._serializable(), indent=2, ensure_ascii=False)

    def _serializable(self) -> dict[str, Any]:
        return {
            "socs": {k: {"name": v.name, "manufacturer": v.manufacturer, "boot_chain": v.boot_chain,
                        "recovery_modes": v.recovery_modes, "tools": v.tools} for k, v in self.data.socs.items()},
            "protocols": {k: {"name": v.name, "description": v.description, "soc_families": v.soc_families,
                             "commands": v.commands, "risk_level": v.risk_level} for k, v in self.data.protocols.items()},
            "playbooks": {k: {"id": v.id, "title": v.title, "symptom": v.symptom, "risk_level": v.risk_level,
                             "steps": v.steps} for k, v in self.data.playbooks.items()},
            "tools": {k: {"name": v.name, "category": v.category, "function": v.function} for k, v in self.data.tools.items()},
            "secret_codes": self.data.secret_codes,
        }

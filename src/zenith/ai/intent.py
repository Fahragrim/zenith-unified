"""Intent Parser — classifies natural language queries into structured intents."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    DIAGNOSE = "diagnose"
    REPAIR = "repair"
    BACKUP = "backup"
    RESTORE = "restore"
    FLASH = "flash"
    UNLOCK = "unlock"
    FRP_BYPASS = "frp_bypass"
    INFO = "info"
    RECOVER = "recover"
    SHELL = "shell"
    REBOOT = "reboot"
    SCAN = "scan"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    type: IntentType
    confidence: float = 1.0
    device_serial: str | None = None
    target_partition: str | None = None
    target_soc: str | None = None
    target_symptom: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value, "confidence": self.confidence,
            "device_serial": self.device_serial, "target_partition": self.target_partition,
            "target_soc": self.target_soc, "target_symptom": self.target_symptom,
            "params": self.params,
        }


INTENT_PATTERNS: list[tuple[IntentType, list[str]]] = [
    (IntentType.DIAGNOSE, ["diagnos", "vad är fel", "felsök", "varför", "bootloop", "startar inte", "kraschar"]),
    (IntentType.REPAIR, ["reparera", "fixa", "laga", "åtgärda", "repair", "fix"]),
    (IntentType.BACKUP, ["backup", "säkerhetskopiera", "backa upp", "spara"]),
    (IntentType.RESTORE, ["restore", "återställ", "återskapa"]),
    (IntentType.FLASH, ["flash", "bränn", "skriv partition", "firmware", "flash boot", "flash recovery"]),
    (IntentType.UNLOCK, ["lås upp", "unlock", "bootloader unlock", "oem unlock"]),
    (IntentType.FRP_BYPASS, ["frp", "google-konto", "fabriksskydd", "factory reset protection"]),
    (IntentType.INFO, ["info", "information", "status", "visa", "list"]),
    (IntentType.RECOVER, ["recover", "rädda", "data recovery", "återskapa filer"]),
    (IntentType.SHELL, ["shell", "kör kommando", "exec", "adb shell"]),
    (IntentType.REBOOT, ["reboot", "starta om", "bootloader", "recovery"]),
    (IntentType.SCAN, ["scan", "scanna", "sök enheter", "discover", "hitta"]),
    (IntentType.HELP, ["hjälp", "help", "?\"", "vad kan du"]),
]

SOC_KEYWORDS = {
    "qualcomm": ["qualcomm", "snapdragon", "edl", "9008"],
    "mediatek": ["mediatek", "mtk", "brom", "vcom"],
    "exynos": ["samsung", "exynos", "odin"],
    "apple": ["apple", "iphone", "ipad", "dfu"],
    "unisoc": ["unisoc", "spreadtrum", "sprd"],
}

SYMPTOM_KEYWORDS = {
    "bootloop": ["bootloop", "startar om", "loop", "boot loop"],
    "hard-brick": ["hard brick", "helt död", "ingen tecken", "9008", "brom"],
    "frp-lock": ["frp", "google-konto", "fabriksskydd"],
    "bootloader-locked": ["bootloader låst", "oem låst"],
    "no-power": ["ingen ström", "laddar inte", "död", "no power"],
    "overheating": ["överhettad", "varm", "overheating"],
}


def parse_intent(text: str) -> Intent:
    """Parse a natural language query into a structured Intent."""
    text_lower = text.lower().strip()
    best_type = IntentType.UNKNOWN
    best_confidence = 0.0

    for intent_type, keywords in INTENT_PATTERNS:
        for kw in keywords:
            if kw in text_lower:
                confidence = 0.7 if intent_type == best_type else 0.8
                if confidence > best_confidence:
                    best_type = intent_type
                    best_confidence = confidence
                break

    # Extract SoC
    target_soc = None
    for soc, keywords in SOC_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            target_soc = soc
            break

    # Extract symptom
    target_symptom = None
    for symptom, keywords in SYMPTOM_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            target_symptom = symptom
            break

    # Extract partition
    target_partition = None
    for part in ["boot", "recovery", "system", "userdata", "vbmeta", "dtbo"]:
        if part in text_lower:
            target_partition = part
            break

    return Intent(
        type=best_type, confidence=best_confidence,
        target_soc=target_soc, target_symptom=target_symptom,
        target_partition=target_partition,
    )

"""Arsenal Shell — interactive diagnostic console (Python port of lanfear_arsenal.sh).

10 diagnostic actions: fingerprint, logcat, bugreport, telemetry, battery,
reboot fastboot/recovery/edl, fastboot getvar all, unlock status check.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArsenalResult:
    action: str
    success: bool = False
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)


ARSENAL_ACTIONS: list[dict[str, Any]] = [
    {"id": "fingerprint", "title": "Deep Device Fingerprint",
     "desc": "SoC, memory, boot-status",
     "cmd": ["adb", "shell", "getprop"],
     "extract": ["ro.product.model", "ro.board.platform", "ro.build.version.release",
                 "ro.boot.verifiedbootstate", "ro.product.manufacturer"]},
    {"id": "logcat", "title": "Live Logcat Extraction",
     "desc": "Dump system logs to file",
     "cmd": ["adb", "logcat", "-d"]},
    {"id": "bugreport", "title": "Complete Bugreport",
     "desc": "Generate sysdump .zip",
     "cmd": ["adb", "bugreport", "lanfear_sysdump.zip"]},
    {"id": "telemetry", "title": "Baseband/Telecom Telemetry",
     "desc": "Network & SIM status",
     "cmd": ["adb", "shell", "dumpsys", "telephony.registry"]},
    {"id": "battery", "title": "Battery/Thermal Diagnostics",
     "desc": "Temperature & battery health",
     "cmd": ["adb", "shell", "dumpsys", "battery"]},
    {"id": "reboot_fastboot", "title": "Reboot to Fastboot",
     "desc": "adb reboot bootloader",
     "cmd": ["adb", "reboot", "bootloader"], "skip_output": True},
    {"id": "reboot_recovery", "title": "Reboot to Recovery",
     "desc": "adb reboot recovery",
     "cmd": ["adb", "reboot", "recovery"], "skip_output": True},
    {"id": "reboot_edl", "title": "Force EDL Reboot",
     "desc": "adb reboot edl",
     "cmd": ["adb", "reboot", "edl"], "skip_output": True},
    {"id": "fastboot_getvar", "title": "Fastboot: Get All Variables",
     "desc": "fastboot getvar all",
     "cmd": ["fastboot", "getvar", "all"], "requires_fastboot": True},
    {"id": "fastboot_unlock", "title": "Query Bootloader Unlock Status",
     "desc": "fastboot getvar unlocked",
     "cmd": ["fastboot", "getvar", "unlocked"], "requires_fastboot": True},
]


def run_action(action_id: str) -> ArsenalResult:
    """Run a single arsenal diagnostic action."""
    action = next((a for a in ARSENAL_ACTIONS if a["id"] == action_id), None)
    if action is None:
        return ArsenalResult(action=action_id, success=False, output=f"Unknown action: {action_id}")

    try:
        proc = subprocess.run(action["cmd"], capture_output=True, text=True, timeout=60)
        result = ArsenalResult(
            action=action_id, success=proc.returncode == 0,
            output=proc.stdout.strip()[:2000] or proc.stderr.strip()[:2000],
        )

        if "extract" in action and proc.returncode == 0:
            for line in proc.stdout.split("\n"):
                for key in action["extract"]:
                    if f"[{key}]:" in line:
                        val = line.split("]: [", 1)[-1].rstrip("]").strip()
                        result.data[key] = val
        return result
    except subprocess.TimeoutExpired:
        return ArsenalResult(action=action_id, success=False, output="Timed out")
    except Exception as e:
        return ArsenalResult(action=action_id, success=False, output=str(e))


def run_all() -> list[ArsenalResult]:
    """Run all 10 arsenal diagnostic actions."""
    return [run_action(a["id"]) for a in ARSENAL_ACTIONS]


def list_actions() -> list[dict[str, Any]]:
    return [{"id": a["id"], "title": a["title"], "desc": a["desc"],
             "requires_fastboot": a.get("requires_fastboot", False)} for a in ARSENAL_ACTIONS]

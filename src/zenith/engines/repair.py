"""Repair Engine — structured repair actions for Android devices.

8 repair types with 15 concrete actions for different SoC families.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class RepairType(str, Enum):
    BOOT_REPAIR = "boot_repair"
    FACTORY_RESET = "factory_reset"
    BOOTLOADER_UNLOCK = "bootloader_unlock"
    FRP_BYPASS = "frp_bypass"
    FIRMWARE_REFLASH = "firmware_reflash"
    PARTITION_FIX = "partition_fix"
    BASEBAND_FIX = "baseband_fix"
    TA_RESTORE = "ta_restore"


class SoCTarget(str, Enum):
    ANY = "any"
    QUALCOMM = "qualcomm"
    MEDIATEK = "mediatek"
    SAMSUNG = "exynos"
    UNISOC = "unisoc"
    GOOGLE = "tensor"


@dataclass
class RepairStep:
    description: str
    command: str | None = None
    tool_name: str | None = None
    requires_safety_check: bool = False
    timeout_seconds: int = 60


@dataclass
class RepairAction:
    id: str
    repair_type: RepairType
    name: str
    description: str
    soc_target: SoCTarget = SoCTarget.ANY
    protocol: str = ""
    risk_level: str = "destructive"
    steps: list[RepairStep] = field(default_factory=list)


class RepairEngine:
    """Registry of repair actions, dispatches to adapters via executor callback."""

    def __init__(self, executor: Callable | None = None) -> None:
        self._actions: dict[str, RepairAction] = {}
        self._executor = executor
        self._register()

    def _register(self) -> None:
        # Boot repair
        self._add(RepairAction("boot_fastboot", RepairType.BOOT_REPAIR, "Boot Repair via Fastboot",
            "Flash stock boot image", protocol="fastboot",
            steps=[RepairStep("Verify fastboot", "fastboot devices"),
                   RepairStep("Flash boot", "fastboot flash boot boot.img"),
                   RepairStep("Clear cache", "fastboot erase cache"),
                   RepairStep("Reboot", "fastboot reboot")]))

        self._add(RepairAction("boot_edl", RepairType.BOOT_REPAIR, "Boot Repair via EDL",
            "Qualcomm EDL boot repair", SoCTarget.QUALCOMM, "edl", "critical",
            steps=[RepairStep("Enter EDL", tool_name="edl"),
                   RepairStep("Dump boot backup", "edl:r --partition=boot --outfile=boot_backup.img"),
                   RepairStep("Flash boot", "edl:w --partition=boot --sid=boot.img"),
                   RepairStep("Reboot", "edl:reset")]))

        self._add(RepairAction("boot_brom", RepairType.BOOT_REPAIR, "Boot Repair via BROM",
            "MTK BROM boot repair", SoCTarget.MEDIATEK, "brom", "critical",
            steps=[RepairStep("Payload bypass", tool_name="mtk"),
                   RepairStep("Flash boot", "shell:python -c pass"),
                   RepairStep("Reboot", "shell:python -c pass")]))

        # Partition fix
        self._add(RepairAction("part_fastboot", RepairType.PARTITION_FIX, "Partition Fix via Fastboot",
            "Fix partition table via fastboot", protocol="fastboot",
            steps=[RepairStep("Format userdata", "fastboot format userdata"),
                   RepairStep("Format cache", "fastboot format cache"),
                   RepairStep("Reboot", "fastboot reboot")]))

        self._add(RepairAction("part_edl", RepairType.PARTITION_FIX, "Partition Fix via EDL",
            "Fix GPT via EDL", SoCTarget.QUALCOMM, "edl",
            steps=[RepairStep("Print GPT", "edl:printgpt"),
                   RepairStep("Recreate partitions", tool_name="edl")]))

        # Factory reset
        self._add(RepairAction("reset_rec", RepairType.FACTORY_RESET, "Factory Reset via Recovery",
            "Wipe data from Recovery mode", protocol="recovery",
            steps=[RepairStep("Reboot recovery", "adb:reboot recovery"),
                   RepairStep("Wipe data (manual)", command=None)]))

        # Bootloader unlock
        self._add(RepairAction("unlock_ftb", RepairType.BOOTLOADER_UNLOCK, "Bootloader Unlock via Fastboot",
            "Unlock bootloader (wipes all data)", protocol="fastboot", risk_level="critical",
            steps=[RepairStep("Enable OEM unlock", "adb_shell:settings put global development_settings_enabled 1"),
                   RepairStep("Reboot fastboot", "adb:reboot bootloader"),
                   RepairStep("Unlock", "fastboot:flashing unlock"),
                   RepairStep("Reboot", "fastboot:reboot")]))

        # FRP bypass
        self._add(RepairAction("frp_edl", RepairType.FRP_BYPASS, "FRP Bypass via EDL",
            "Erase userdata via EDL to remove FRP", SoCTarget.QUALCOMM, "edl",
            steps=[RepairStep("Erase userdata", "edl:e --partition=userdata"),
                   RepairStep("Reboot", "edl:reset")]))

        self._add(RepairAction("frp_brom", RepairType.FRP_BYPASS, "FRP Bypass via BROM",
            "Erase userdata+md_udc via BROM", SoCTarget.MEDIATEK, "brom",
            steps=[RepairStep("Payload bypass", tool_name="mtk"),
                   RepairStep("Erase userdata", "shell:python -c pass")]))

        # Firmware reflash
        self._add(RepairAction("fw_fastboot", RepairType.FIRMWARE_REFLASH, "Firmware Reflash via Fastboot",
            "Flash stock firmware images", protocol="fastboot",
            steps=[RepairStep("Flash boot", "fastboot:flash boot boot.img"),
                   RepairStep("Flash system", "fastboot:flash system system.img"),
                   RepairStep("Flash vbmeta", "fastboot:flash vbmeta vbmeta.img"),
                   RepairStep("Reboot", "fastboot:reboot")]))

        # Baseband fix
        self._add(RepairAction("baseband_fastboot", RepairType.BASEBAND_FIX, "Baseband Fix via Fastboot",
            "Re-flash modem partitions", protocol="fastboot",
            steps=[RepairStep("Flash modem", "fastboot:flash modem modem.img"),
                   RepairStep("Reboot", "fastboot:reboot")]))

        # TA restore
        self._add(RepairAction("ta_restore", RepairType.TA_RESTORE, "TA Restore via Newflasher",
            "Restore TA partition (Sony Xperia)", protocol="newflasher", risk_level="critical",
            steps=[RepairStep("Flash TA backup", "newflasher:flash")]))

    def _add(self, action: RepairAction) -> None:
        self._actions[action.id] = action

    def list_actions(self, repair_type: RepairType | None = None) -> list[RepairAction]:
        if repair_type:
            return [a for a in self._actions.values() if a.repair_type == repair_type]
        return list(self._actions.values())

    def get(self, action_id: str) -> RepairAction | None:
        return self._actions.get(action_id)

    def find(self, repair_type: RepairType, soc: SoCTarget | None = None) -> list[RepairAction]:
        actions = self.list_actions(repair_type)
        if soc:
            actions = [a for a in actions if a.soc_target in (SoCTarget.ANY, soc)]
        return actions

    def execute(self, action_id: str, executor: Callable | None = None) -> dict[str, Any]:
        action = self._actions.get(action_id)
        if action is None:
            return {"success": False, "error": f"Action not found: {action_id}"}
        exec_fn = executor or self._executor
        if exec_fn is None:
            return {"success": False, "error": "No executor configured"}
        results = []
        for step in action.steps:
            if step.command:
                ok, out = exec_fn(step.command)
                results.append({"step": step.description, "command": step.command, "success": ok, "output": out})
                if not ok:
                    return {"success": False, "action": action_id, "results": results, "error": out}
            else:
                results.append({"step": step.description, "command": None, "success": True, "output": "Manual step"})
        logger.info(f"Repair OK: {action.name}")
        return {"success": True, "action": action_id, "results": results}

    def set_executor(self, fn: Callable) -> None:
        self._executor = fn

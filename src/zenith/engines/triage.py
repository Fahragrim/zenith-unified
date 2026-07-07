"""Triage Engine — interactive diagnostic decision tree.

Ported from OpencodeDeviceTool's triage_engine.py.
Walks user through device symptoms → diagnosis → playbook recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TriageNodeType(str, Enum):
    QUESTION = "question"
    ACTION = "action"
    DIAGNOSIS = "diagnosis"
    RESULT = "result"


class DeviceSymptom(str, Enum):
    NO_POWER = "no_power"
    BOOTLOOP = "bootloop"
    STUCK_FASTBOOT = "stuck_fastboot"
    STUCK_RECOVERY = "stuck_recovery"
    NO_DETECTION = "no_detection"
    EDL_MODE = "edl_mode"
    BROM_MODE = "brom_mode"
    FRP_LOCKED = "frp_locked"
    BOOTLOADER_LOCKED = "bootloader_locked"
    SYSTEM_CRASH = "system_crash"
    OVERHEATING = "overheating"
    BATTERY_DRAIN = "battery_drain"


@dataclass
class TriageOption:
    text: str
    next_node_id: str
    symptom: str | None = None
    confidence: float = 1.0


@dataclass
class TriageNode:
    id: str
    question: str = ""
    node_type: TriageNodeType = TriageNodeType.QUESTION
    options: list[TriageOption] = field(default_factory=list)
    diagnosis: str = ""
    risk_level: str = "read_only"
    soc_family: str = ""
    protocol: str = ""
    playbook_id: str = ""


@dataclass
class TriageResult:
    path: list[str] = field(default_factory=list)
    symptoms_detected: list[str] = field(default_factory=list)
    soc_family: str = ""
    protocol: str = ""
    playbook_ids: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    risk_level: str = "low"
    diagnosis: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "symptoms": self.symptoms_detected, "soc_family": self.soc_family,
                "protocol": self.protocol, "playbook_ids": self.playbook_ids,
                "recommended_actions": self.recommended_actions, "risk_level": self.risk_level,
                "diagnosis": self.diagnosis}


class TriageEngine:
    def __init__(self) -> None:
        self._nodes: dict[str, TriageNode] = {}
        self._build()

    def _node(self, id: str, q: str = "", nt: TriageNodeType = TriageNodeType.QUESTION, **kw: Any) -> TriageNode:
        return TriageNode(id=id, question=q, node_type=nt, **kw)

    def _build(self) -> None:
        n = self._node
        self._nodes["start"] = n("start", "What issue is your device experiencing?",
            options=[TriageOption("No power / black screen", "no_power", "no_power"),
                     TriageOption("Bootloop / restarting", "bootloop_chk", "bootloop"),
                     TriageOption("Stuck in Fastboot", "fb_chk", "stuck_fastboot"),
                     TriageOption("Stuck in Recovery", "rec_chk", "stuck_recovery"),
                     TriageOption("FRP / Google locked", "frp_chk", "frp_locked"),
                     TriageOption("System crashes", "crash_chk", "system_crash"),
                     TriageOption("Overheating / battery", "heat_chk", "overheating")])

        self._nodes["no_power"] = n("no_power", "Any sign of life? (LED, vibration, screen flash)",
            options=[TriageOption("Completely dead", "dead"), TriageOption("LED/screen flash", "edl_chk")])

        self._nodes["dead"] = n("dead", nt=TriageNodeType.RESULT,
            diagnosis="Hardware failure or deeply discharged battery.", risk_level="high")

        self._nodes["edl_chk"] = n("edl_chk", "Computer detects device when USB connected?",
            options=[TriageOption("Qualcomm 9008 (EDL)", "edl_diag", "edl_mode"),
                     TriageOption("MediaTek VCOM (BROM)", "brom_diag", "brom_mode"),
                     TriageOption("No detection", "driver_chk")])

        self._nodes["edl_diag"] = n("edl_diag", nt=TriageNodeType.DIAGNOSIS,
            diagnosis="Qualcomm EDL mode. Recoverable with firehose programmer.",
            risk_level="destructive", soc_family="qualcomm", protocol="edl", playbook_id="hard-brick-qualcomm")

        self._nodes["brom_diag"] = n("brom_diag", nt=TriageNodeType.DIAGNOSIS,
            diagnosis="MediaTek BROM mode. Use mtkclient for bypass and recovery.",
            risk_level="destructive", soc_family="mediatek", protocol="brom", playbook_id="hard-brick-mediatek")

        self._nodes["driver_chk"] = n("driver_chk", "Install USB driver?",
            options=[TriageOption("Install Qualcomm driver", "edl_diag"),
                     TriageOption("Install MTK VCOM driver", "brom_diag"),
                     TriageOption("Already installed", "dead")])

        self._nodes["bootloop_chk"] = n("bootloop_chk", "Can you enter Recovery mode? (Vol Up + Power)",
            options=[TriageOption("Yes, Recovery works", "rec_diag", "bootloop"),
                     TriageOption("No, only Fastboot", "fb_diag", "stuck_fastboot")])

        self._nodes["rec_diag"] = n("rec_diag", nt=TriageNodeType.DIAGNOSIS,
            diagnosis="Bootloop. Wipe cache in Recovery. If fails: factory reset.",
            risk_level="medium", playbook_id="soft-brick-bootloop")

        self._nodes["fb_diag"] = n("fb_diag", nt=TriageNodeType.DIAGNOSIS,
            diagnosis="Stuck in Fastboot. Flash boot.img or full firmware.",
            risk_level="high", protocol="fastboot", playbook_id="soft-brick-bootloop")

        self._nodes["fb_chk"] = n("fb_chk", nt=TriageNodeType.DIAGNOSIS,
            diagnosis="Stuck in Fastboot. Run: fastboot getvar all.", protocol="fastboot")

        self._nodes["rec_chk"] = n("rec_chk", nt=TriageNodeType.DIAGNOSIS,
            diagnosis="Stuck in Recovery. Wipe data/factory reset from menu.")

        self._nodes["frp_chk"] = n("frp_chk", "Android version?",
            options=[TriageOption("Android 5-7", "frp_diag", "frp_locked"),
                     TriageOption("Android 8-10", "frp_diag", "frp_locked"),
                     TriageOption("Android 11+", "frp_diag", "frp_locked")])

        self._nodes["frp_diag"] = n("frp_diag", nt=TriageNodeType.DIAGNOSIS,
            diagnosis="FRP lock. Android 11+ requires EDL/BROM to format userdata.",
            risk_level="high", playbook_id="frp-bypass")

        self._nodes["crash_chk"] = n("crash_chk", nt=TriageNodeType.DIAGNOSIS,
            diagnosis="System crashes. Try: wipe cache, uninstall recent apps, factory reset.")

        self._nodes["heat_chk"] = n("heat_chk", nt=TriageNodeType.DIAGNOSIS,
            diagnosis="Overheating. Clean vents, reduce workload, check battery health.")

    def traverse(self, choices: list[str]) -> TriageResult:
        result = TriageResult()
        node = self._nodes.get("start")
        if not node:
            return result
        result.path.append(node.id)
        for choice in choices:
            matched = None
            for opt in node.options:
                if opt.text.lower() == choice.lower():
                    matched = opt
                    break
            if matched is None:
                result.path.append("_end")
                break
            if matched.symptom:
                result.symptoms_detected.append(matched.symptom)
            node = self._nodes.get(matched.next_node_id)
            if node is None:
                break
            result.path.append(node.id)
            if node.soc_family:
                result.soc_family = node.soc_family
            if node.protocol:
                result.protocol = node.protocol
            if node.playbook_id:
                result.playbook_ids.append(node.playbook_id)
            if node.diagnosis:
                result.diagnosis = node.diagnosis
            if node.risk_level:
                result.risk_level = node.risk_level
            if node.node_type in (TriageNodeType.DIAGNOSIS, TriageNodeType.RESULT):
                break
        if "edl_mode" in result.symptoms_detected or result.protocol == "edl":
            result.recommended_actions = ["Trigger EDL → flash via QFIL/edl.py"]
        elif "bootloop" in result.symptoms_detected:
            result.recommended_actions = ["Wipe cache from Recovery", "Flash stock boot.img via Fastboot"]
        elif "frp_locked" in result.symptoms_detected:
            result.recommended_actions = ["Format userdata via EDL/BROM"]
        return result

    def auto_detect(self, protocol: str) -> TriageResult:
        choices: list[str] = ["No power / black screen"]
        if protocol == "edl":
            choices = ["No power / black screen", "LED/screen flash", "Qualcomm 9008 (EDL)"]
        elif protocol == "brom":
            choices = ["No power / black screen", "LED/screen flash", "MediaTek VCOM (BROM)"]
        elif protocol == "fastboot":
            choices = ["Bootloop / restarting", "No, only Fastboot"]
        return self.traverse(choices)

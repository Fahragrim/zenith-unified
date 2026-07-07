"""Diagnostics Engine — Bayesian fault analysis + knowledge graph.

Combines lanfear-platform's BayesianFaultAnalyzer with OpencodeDeviceTool's triage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

BAYESIAN_PRIORS: dict[str, dict[str, float]] = {
    "bootloop": {"corrupt_boot": 0.25, "kernel_panic": 0.20, "corrupt_system": 0.15,
                 "battery_failure": 0.10, "pmic_instability": 0.10, "hardware_damage": 0.10, "overheating": 0.05, "unknown": 0.05},
    "hard-brick": {"corrupt_bootloader": 0.30, "corrupt_gpt": 0.15, "pmic_failure": 0.15,
                   "dead_battery": 0.10, "edl_not_triggering": 0.10, "emmc_ufs_dead": 0.10, "unknown": 0.10},
    "frp-lock": {"google_account": 0.60, "frp_bypass_needed": 0.30, "custom_rom_issue": 0.10},
    "no-charging": {"usb_port_damage": 0.25, "dead_battery": 0.20, "pmic_failure": 0.20,
                    "charging_ic_failure": 0.15, "software_bug": 0.10, "unknown": 0.10},
    "overheating": {"thermal_paste_degraded": 0.20, "heavy_workload": 0.20, "charging_while_using": 0.15,
                    "hardware_fault": 0.15, "software_bug": 0.10, "unknown": 0.10},
}

SYMPTOM_TESTS: dict[str, list[str]] = {
    "bootloop": ["Check Recovery Mode", "fastboot devices", "Read last_kmsg", "Wipe cache from Recovery"],
    "hard-brick": ["Check Device Manager for 9008/VCOM", "Try EDL test point", "Measure battery voltage (>3.0V)"],
    "frp-lock": ["Check Android version", "Verify Google account lock", "Test EDL/BROM access"],
}

SYMPTOM_FIXES: dict[str, list[str]] = {
    "bootloop": ["Wipe cache from Recovery", "Flash stock boot.img via Fastboot", "Factory reset from Recovery"],
    "hard-brick": ["Trigger EDL mode → flash via QFIL/edl.py", "Trigger BROM mode → use mtkclient"],
    "frp-lock": ["Format userdata via EDL: edl w z --partition=userdata", "Use SamFw Tool for Samsung FRP"],
}


@dataclass
class DiagnosisResult:
    diagnosis: str
    confidence: float = 0.0
    causes: dict[str, float] = field(default_factory=dict)
    tests: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)
    risk_level: str = "low"
    suggested_playbooks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagnosis": self.diagnosis, "confidence": self.confidence,
            "causes": self.causes, "tests": self.tests, "fixes": self.fixes,
            "risk_level": self.risk_level, "suggested_playbooks": self.suggested_playbooks,
        }


class DiagnosticsEngine:
    """Bayesian diagnostics with knowledge base integration."""

    def __init__(self, knowledge_base: Any = None) -> None:
        self.kb = knowledge_base

    def diagnose(self, symptoms: list[str]) -> DiagnosisResult:
        """Run Bayesian diagnosis from symptoms."""
        if not symptoms:
            return DiagnosisResult(diagnosis="No symptoms provided")

        primary = symptoms[0] if symptoms else "unknown"
        priors = BAYESIAN_PRIORS.get(primary, {"unknown": 1.0})
        total = sum(priors.values())
        distribution = {k.replace("_", " ").title(): v / total for k, v in priors.items()}

        best_cause = max(distribution, key=distribution.get)  # type: ignore[arg-type]
        best_prob = distribution[best_cause]
        tests = SYMPTOM_TESTS.get(primary, [])
        fixes = SYMPTOM_FIXES.get(primary, [])

        risk = "low"
        if primary in ("hard-brick", "brom-access", "dfu-mode"):
            risk = "critical"
        elif primary in ("bootloop", "no-charging"):
            risk = "high"
        elif primary in ("frp-lock", "bootloader-locked"):
            risk = "medium"

        # Find matching playbooks
        playbooks = []
        if self.kb:
            found = self.kb.find_playbook(primary)
            playbooks = [pb.id for pb in found]
        else:
            playbook_map = {"bootloop": ["soft-brick-bootloop"], "hard-brick": ["hard-brick-qualcomm", "hard-brick-mediatek"],
                           "frp-lock": ["frp-bypass"], "bootloader-locked": ["bootloader-unlock"]}
            playbooks = playbook_map.get(primary, [])

        logger.info(f"Diagnosis: {best_cause} ({best_prob:.0%})")
        return DiagnosisResult(
            diagnosis=f"{best_cause} ({best_prob:.0%} confidence)",
            confidence=best_prob, causes=distribution,
            tests=tests, fixes=fixes, risk_level=risk,
            suggested_playbooks=playbooks,
        )

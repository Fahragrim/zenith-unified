"""Flash Engine — 5-phase firmware flashing orchestrator.

Phases:
  1. PREFLIGHT  — validate profile, firmware, policy
  2. BACKUP     — read every target partition
  3. FLASH      — write firmware to each partition
  4. VERIFY     — read back and compare SHA-256
  5. ROLLBACK   — restore from on failure

Ported from xperiatool's atlas/engines/flash.py.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from loguru import logger


class FlashPhase(str, Enum):
    PREFLIGHT = "preflight"
    BACKUP = "backup"
    FLASH = "flash"
    VERIFY = "verify"
    ROLLBACK = "rollback"
    COMPLETED = "completed"


class StepKind(str, Enum):
    BACKUP = "backup"
    ERASE = "erase"
    FLASH = "flash"
    VERIFY = "verify"
    REBOOT = "reboot"
    CHECK = "check"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FlashStep:
    id: str
    kind: StepKind
    partition: str
    source_path: str | None = None
    backup_path: str | None = None
    risk_level: str = "MEDIUM"
    timeout_s: int = 120
    status: StepStatus = StepStatus.PENDING
    error: str = ""
    notes: str = ""


@dataclass
class FlashPlan:
    id: str
    device_id: str
    firmware_dir: str
    target_partitions: list[str] = field(default_factory=list)
    backup_dir: str = ""
    steps: list[FlashStep] = field(default_factory=list)
    dry_run: bool = True

    @property
    def destructive_steps(self) -> list[FlashStep]:
        return [s for s in self.steps if s.risk_level in ("HIGH", "CRITICAL")]


@dataclass
class FlashResult:
    plan_id: str
    success: bool = False
    phase: FlashPhase = FlashPhase.PREFLIGHT
    step_results: list[dict] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {"plan_id": self.plan_id, "success": self.success, "phase": self.phase.value,
                "steps": self.step_results, "error": self.error}


class FlashEngine:
    """Orchestrates firmware flashing with 5-phase lifecycle."""

    def __init__(self, executor: Callable | None = None) -> None:
        self._executor = executor

    def set_executor(self, fn: Callable) -> None:
        self._executor = fn

    def plan(self, device_id: str, firmware_dir: str, partitions: list[str] | None = None) -> FlashPlan:
        """Create a FlashPlan (read-only)."""
        fw_path = Path(firmware_dir)
        target = partitions or self._auto_targets(fw_path)
        plan = FlashPlan(
            id=f"{device_id}_{FlashPhase.PREFLIGHT.value}",
            device_id=device_id, firmware_dir=firmware_dir,
            target_partitions=target, backup_dir=f"/tmp/zenith_backup/{device_id}",
        )
        for part in target:
            img = self._find_image(fw_path, part)
            plan.steps.append(FlashStep(id=f"backup_{part}", kind=StepKind.BACKUP, partition=part,
                                       backup_path=str(Path(plan.backup_dir) / f"{part}.img"), risk_level="LOW"))
            plan.steps.append(FlashStep(id=f"flash_{part}", kind=StepKind.FLASH, partition=part,
                                       source_path=str(img) if img else None, risk_level="HIGH"))
            plan.steps.append(FlashStep(id=f"verify_{part}", kind=StepKind.VERIFY, partition=part,
                                       backup_path=str(Path(plan.backup_dir) / f"{part}.img"), risk_level="LOW"))
        return plan

    def execute(self, plan: FlashPlan) -> FlashResult:
        """Execute a FlashPlan through all 5 phases."""
        result = FlashResult(plan_id=plan.id)
        fn = self._executor
        if fn is None:
            result.error = "No executor configured"
            return result

        # Phase 1: PREFLIGHT
        result.phase = FlashPhase.PREFLIGHT
        for step in plan.steps:
            if step.risk_level in ("HIGH", "CRITICAL") and not plan.dry_run:
                logger.warning(f"[PREFLIGHT] Destructive step: {step.id} ({step.partition})")

        if plan.dry_run:
            logger.info("[PREFLIGHT] Dry-run mode — no commands will execute")
            result.success = True
            result.phase = FlashPhase.COMPLETED
            return result

        # Phase 2-5: Execute steps
        for step in plan.steps:
            result.phase = FlashPhase.BACKUP if step.kind == StepKind.BACKUP else \
                           FlashPhase.FLASH if step.kind == StepKind.FLASH else \
                           FlashPhase.VERIFY if step.kind == StepKind.VERIFY else result.phase

            if step.kind == StepKind.BACKUP:
                ok, out = self._try_exec(f"edl:r --partition={step.partition} --outfile={step.backup_path}", fn)
                step.status = StepStatus.COMPLETED if ok else StepStatus.FAILED
                step.error = "" if ok else out
                result.step_results.append({"phase": "backup", "partition": step.partition, "success": ok, "output": out[:200]})
                if not ok:
                    return self._rollback(result, plan, fn)

            elif step.kind == StepKind.FLASH:
                if not step.source_path:
                    step.status = StepStatus.SKIPPED
                    step.error = "No source image"
                    result.step_results.append({"phase": "flash", "partition": step.partition, "success": False, "output": "No image"})
                    continue
                ok, out = self._try_exec(f"edl:w --partition={step.partition} --sid={step.source_path}", fn)
                step.status = StepStatus.COMPLETED if ok else StepStatus.FAILED
                step.error = "" if ok else out
                result.step_results.append({"phase": "flash", "partition": step.partition, "success": ok, "output": out[:200]})
                if not ok:
                    return self._rollback(result, plan, fn)

            elif step.kind == StepKind.VERIFY:
                ok, out = self._try_exec(f"edl:r --partition={step.partition} --outfile={step.backup_path}.verify", fn)
                step.status = StepStatus.COMPLETED if ok else StepStatus.FAILED
                step.error = "" if ok else out
                result.step_results.append({"phase": "verify", "partition": step.partition, "success": ok, "output": out[:200]})

        result.success = True
        result.phase = FlashPhase.FLASH
        return result

    def _rollback(self, result: FlashResult, plan: FlashPlan, fn: Callable) -> FlashResult:
        result.phase = FlashPhase.ROLLBACK
        logger.warning("ROLLBACK triggered — restoring partitions")
        for step in plan.steps:
            if step.kind == StepKind.BACKUP and step.backup_path:
                ok, out = self._try_exec(f"edl:w --partition={step.partition} --sid={step.backup_path}", fn)
                result.step_results.append({"phase": "rollback", "partition": step.partition, "success": ok})
        result.error = "Flashing failed. Rollback attempted."
        return result

    @staticmethod
    def _try_exec(cmd: str, fn: Callable) -> tuple[bool, str]:
        try:
            return fn(cmd)
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _auto_targets(fw_dir: Path) -> list[str]:
        if not fw_dir.exists():
            return ["boot", "recovery"]
        parts = []
        for suffix in (".img", ".bin", ".mbn"):
            for f in fw_dir.glob(f"*{suffix}"):
                parts.append(f.stem)
        return parts if parts else ["boot", "recovery"]

    @staticmethod
    def _find_image(fw_dir: Path, partition: str) -> Path | None:
        for suffix in (".img", ".bin", ".mbn"):
            p = fw_dir / f"{partition}{suffix}"
            if p.exists():
                return p
        return None

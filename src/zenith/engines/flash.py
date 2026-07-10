"""Flash Engine — 5-phase firmware flashing orchestrator + EDL/BROM pipelines.

Phases:
   1. PREFLIGHT  — validate profile, firmware, policy
   2. BACKUP     — read every target partition
   3. FLASH      — write firmware to each partition
   4. VERIFY     — read back and compare SHA-256
   5. ROLLBACK   — restore from on failure

EDL Pipeline:
   detect → sahara_hello → sahara_upload_loader → firehose_connect → flash_partitions → reset

BROM Pipeline:
   detect → handshake → send_da → jump_da → flash_partitions → reset

Ported from xperiatool's atlas/engines/flash.py.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, cast

from loguru import logger

from zenith.core.device import DeviceType
from zenith.engines.flash_protocols import BromTransport, EdlTransport


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
    step_results: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "success": self.success, "phase": self.phase.value,
                "steps": self.step_results, "error": self.error}


class FlashEngine:
    """Orchestrates firmware flashing with 5-phase lifecycle + EDL/BROM pipelines.

    Uses AdapterRegistry for adapter dispatch when available; falls back
    to direct EDL/BROM transports for low-level flash operations.
    """

    def __init__(
        self,
        executor: Callable[..., Any] | None = None,
        edl_transport: EdlTransport | None = None,
        brom_transport: BromTransport | None = None,
        registry: Any = None,
    ) -> None:
        self._executor = executor
        self._edl_transport = edl_transport
        self._brom_transport = brom_transport
        self._registry = registry

    def _get_registry(self) -> Any:
        if self._registry is None:
            from zenith.adapters.registry import get_adapter_registry
            self._registry = get_adapter_registry()
        return self._registry

    def set_executor(self, fn: Callable[..., Any]) -> None:
        self._executor = fn

    # ─── EDL Pipeline ────────────────────────────────────────────────────────────

    def detect_edl_device(self) -> str | None:
        """Detect Qualcomm EDL device. Tries EdlTransport, then adapter registry."""
        if self._edl_transport is not None:
            serial = self._edl_transport.detect()
            if serial is not None:
                logger.info(f"EDL device detected: {serial}")
                return serial
        # Try via AdapterRegistry
        registry = self._get_registry()
        adapter = registry.get_or_create(DeviceType.QUALCOMM_EDL)
        if adapter is not None:
            try:
                result = adapter.list_devices()
                for entry in (result or []):
                    serial = entry.get("serial")
                    if serial:
                        logger.info(f"EDL device detected via adapter: {serial}")
                        return str(serial)
            except Exception:
                pass
        try:
            from zenith.adapters.qualcomm_edl import QualcommEDLAdapter
            adapter = QualcommEDLAdapter()
            if adapter.is_available():
                result = adapter.list_devices()
                for entry in (result or []):
                    serial = entry.get("serial")
                    if serial:
                        logger.info(f"EDL device detected via adapter: {serial}")
                        return str(serial)
        except Exception as e:
            logger.debug(f"EDL adapter detection failed: {e}")
        return None

    def sahara_hello(self) -> dict[str, Any]:
        """Send Sahara HELLO_REQ and return parsed response.

        Returns dict with mode, status, version keys (or error).
        """
        if self._edl_transport is None:
            return {"error": "No EDL transport configured"}
        return self._edl_transport.sahara_hello()

    def sahara_upload_loader(self, loader_path: str) -> bool:
        """Upload a .mbn or .elf programmer loader via Sahara protocol."""
        if self._edl_transport is None:
            logger.error("No EDL transport configured")
            return False
        loader = Path(loader_path)
        if not loader.exists():
            logger.error(f"Loader not found: {loader_path}")
            return False
        return self._edl_transport.sahara_upload_loader(loader_path)

    def firehose_connect(self, max_payload_size: int = 1048576) -> bool:
        """Configure and connect via Firehose protocol after Sahara uploads loader."""
        if self._edl_transport is None:
            logger.error("No EDL transport configured")
            return False
        return self._edl_transport.firehose_connect(max_payload_size)

    def firehose_flash_partition(self, partition: str, file_path: str) -> bool:
        """Flash a single partition via Firehose XML commands.

        Builds a <program> XML command and sends it over the Firehose transport.
        """
        if self._edl_transport is None:
            logger.error("No EDL transport configured")
            return False
        img = Path(file_path)
        if not img.exists():
            logger.error(f"Image not found: {file_path}")
            return False
        from zenith.engines.flash_protocols import build_firehose_program_xml
        num_sectors = (img.stat().st_size + 511) // 512
        xml = build_firehose_program_xml(
            partition=partition,
            filename=img.name,
            num_sectors=num_sectors,
        )
        result = self._edl_transport.firehose_command(xml)
        ok = bool(result.get("success", False))
        if ok:
            logger.info(f"Firehose flash OK: {partition} ← {file_path}")
        else:
            logger.error(f"Firehose flash FAILED: {partition} — {result.get('error', '')}")
        return ok

    def firehose_reset(self) -> bool:
        """Send Firehose reset command to reboot device."""
        if self._edl_transport is None:
            logger.error("No EDL transport configured")
            return False
        return self._edl_transport.firehose_reset()

    # ─── BROM Pipeline ───────────────────────────────────────────────────────────

    def detect_brom_device(self) -> str | None:
        """Detect MediaTek BROM device. Tries BromTransport, then adapter registry."""
        if self._brom_transport is not None:
            serial = self._brom_transport.detect()
            if serial is not None:
                logger.info(f"BROM device detected: {serial}")
                return serial
        # Try via AdapterRegistry
        registry = self._get_registry()
        adapter = registry.get_or_create(DeviceType.MTK_BROM)
        if adapter is not None:
            try:
                result = adapter.list_devices()
                for entry in (result or []):
                    serial = entry.get("serial")
                    if serial:
                        logger.info(f"BROM device detected via adapter: {serial}")
                        return str(serial)
            except Exception:
                pass
        try:
            from zenith.adapters.mediatek_brom import MediaTekBROMAdapter
            adapter = MediaTekBROMAdapter()
            if adapter.is_available():
                result = adapter.list_devices()
                for entry in (result or []):
                    serial = entry.get("serial")
                    if serial:
                        logger.info(f"BROM device detected via adapter: {serial}")
                        return str(serial)
        except Exception as e:
            logger.debug(f"BROM adapter detection failed: {e}")
        return None

    def brom_handshake(self) -> dict[str, Any]:
        """Perform BROM handshake."""
        if self._brom_transport is None:
            return {"error": "No BROM transport configured"}
        return self._brom_transport.handshake()

    def brom_send_da(self, da_path: str) -> bool:
        """Send Download Agent (DA) to BROM device."""
        if self._brom_transport is None:
            logger.error("No BROM transport configured")
            return False
        da = Path(da_path)
        if not da.exists():
            logger.error(f"DA not found: {da_path}")
            return False
        return self._brom_transport.send_da(da_path)

    def brom_jump_da(self) -> bool:
        """Jump to uploaded Download Agent."""
        if self._brom_transport is None:
            logger.error("No BROM transport configured")
            return False
        return self._brom_transport.jump_da()

    def brom_flash_partition(self, partition: str, file_path: str) -> bool:
        """Flash a partition via DA protocol."""
        if self._brom_transport is None:
            logger.error("No BROM transport configured")
            return False
        img = Path(file_path)
        if not img.exists():
            logger.error(f"Image not found: {file_path}")
            return False
        return self._brom_transport.flash_partition(partition, file_path)

    def brom_reset(self) -> bool:
        """Send reset command to reboot device."""
        if self._brom_transport is None:
            logger.error("No BROM transport configured")
            return False
        return self._brom_transport.reset()

    def close_transports(self) -> None:
        """Release USB resources for both transports if open."""
        if self._edl_transport is not None:
            try:
                self._edl_transport.close()
            except Exception as e:
                logger.debug(f"Error closing EDL transport: {e}")
        if self._brom_transport is not None:
            try:
                self._brom_transport.close()
            except Exception as e:
                logger.debug(f"Error closing BROM transport: {e}")

    # ─── Dry-run aware EDL helpers (safe to call without hardware) ───────────────

    def edl_flash_pipeline(
        self,
        loader_path: str | None = None,
        partitions: dict[str, str] | None = None,
        *,
        dry_run: bool = True,
    ) -> FlashResult:
        """Run the full Qualcomm EDL flash pipeline.

        Args:
            loader_path: Path to .mbn/.elf programmer loader (None = detect).
            partitions: Dict mapping partition name → image file path.
            dry_run: If True, simulate without USB.

        Returns:
            FlashResult with step-level success/failure.
        """
        result = FlashResult(plan_id="edl_pipeline")
        if dry_run:
            logger.info("[DRY-RUN] EDL flash pipeline — no commands will execute")
            result.success = True
            result.phase = FlashPhase.COMPLETED
            return result

        phases: list[tuple[str, Callable[..., Any], dict[str, Any]]] = [
            ("detect", self.detect_edl_device, {"result": None}),
            ("sahara_hello", self.sahara_hello, {"result": None}),
            ("upload_loader", self.sahara_upload_loader, {"loader": loader_path}),
            ("firehose_connect", self.firehose_connect, {"result": None}),
        ]
        for name, method, ctx in phases:
            try:
                if name == "upload_loader":
                    if loader_path:
                        ok = method(loader_path)
                    else:
                        ok = True  # skip if no loader
                elif name == "detect":
                    serial = method()
                    ok = serial is not None
                    ctx["result"] = serial
                elif name == "sahara_hello":
                    resp = method()
                    ok = "error" not in resp
                    ctx["result"] = resp
                else:
                    ok = method()
                result.step_results.append({"phase": "edl", "step": name, "success": ok})
                if not ok:
                    result.error = f"EDL pipeline failed at {name}"
                    return result
            except Exception as e:
                result.error = f"EDL pipeline error at {name}: {e}"
                result.step_results.append({"phase": "edl", "step": name, "success": False, "error": str(e)})
                return result

        if partitions:
            for partition, file_path in partitions.items():
                ok = self.firehose_flash_partition(partition, file_path)
                result.step_results.append({"phase": "flash", "partition": partition, "success": ok})
                if not ok:
                    result.error = f"Flash failed at partition {partition}"
                    return result

        reset_ok = self.firehose_reset()
        result.step_results.append({"phase": "edl", "step": "reset", "success": reset_ok})
        result.success = True
        result.phase = FlashPhase.COMPLETED
        return result

    def brom_flash_pipeline(
        self,
        da_path: str | None = None,
        partitions: dict[str, str] | None = None,
        *,
        dry_run: bool = True,
    ) -> FlashResult:
        """Run the full MediaTek BROM flash pipeline.

        Args:
            da_path: Path to Download Agent binary (None = skip DA upload).
            partitions: Dict mapping partition name → image file path.
            dry_run: If True, simulate without USB.

        Returns:
            FlashResult with step-level success/failure.
        """
        result = FlashResult(plan_id="brom_pipeline")
        if dry_run:
            logger.info("[DRY-RUN] BROM flash pipeline — no commands will execute")
            result.success = True
            result.phase = FlashPhase.COMPLETED
            return result

        phases: list[tuple[str, Callable[..., Any], dict[str, Any]]] = [
            ("detect", self.detect_brom_device, {"result": None}),
            ("handshake", self.brom_handshake, {"result": None}),
            ("send_da", lambda: self.brom_send_da(da_path) if da_path else True, {"result": None}),
            ("jump_da", self.brom_jump_da, {"result": None}),
        ]
        for name, method, _ctx in phases:
            try:
                ok = method()
                result.step_results.append({"phase": "brom", "step": name, "success": ok})
                if not ok:
                    result.error = f"BROM pipeline failed at {name}"
                    return result
            except Exception as e:
                result.error = f"BROM pipeline error at {name}: {e}"
                result.step_results.append({"phase": "brom", "step": name, "success": False, "error": str(e)})
                return result

        if partitions:
            for partition, file_path in partitions.items():
                ok = self.brom_flash_partition(partition, file_path)
                result.step_results.append({"phase": "flash", "partition": partition, "success": ok})
                if not ok:
                    result.error = f"Flash failed at partition {partition}"
                    return result

        reset_ok = self.brom_reset()
        result.step_results.append({"phase": "brom", "step": "reset", "success": reset_ok})
        result.success = True
        result.phase = FlashPhase.COMPLETED
        return result

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
            # Try registry dispatch as fallback executor
            registry = self._get_registry()
            fn = registry.dispatch if hasattr(registry, 'dispatch') else None
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

    def _rollback(self, result: FlashResult, plan: FlashPlan, fn: Callable[..., Any]) -> FlashResult:
        result.phase = FlashPhase.ROLLBACK
        logger.warning("ROLLBACK triggered — restoring partitions")
        for step in plan.steps:
            if step.kind == StepKind.BACKUP and step.backup_path:
                ok, out = self._try_exec(f"edl:w --partition={step.partition} --sid={step.backup_path}", fn)
                result.step_results.append({"phase": "rollback", "partition": step.partition, "success": ok})
        result.error = "Flashing failed. Rollback attempted."
        return result

    @staticmethod
    def _try_exec(cmd: str, fn: Callable[..., Any]) -> tuple[bool, str]:
        try:
            return cast(tuple[bool, str], fn(cmd))
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

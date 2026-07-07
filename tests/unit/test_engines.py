"""Unit tests for engines and deep adapters."""

from __future__ import annotations

import pytest

from zenith.adapters.diag_at import DiagATAdapter
from zenith.adapters.mediatek_brom import MediaTekBROMAdapter
from zenith.adapters.qualcomm_edl import QualcommEDLAdapter
from zenith.core.device import DeviceType
from zenith.engines.diagnostics import DiagnosisResult, DiagnosticsEngine
from zenith.engines.playbook_executor import PlaybookExecutor, PlaybookRunResult
from zenith.engines.repair import RepairEngine, RepairType, SoCTarget
from zenith.engines.triage import TriageEngine


# ─── Deep Adapters ────────────────────────────────────────────────────────


class TestQualcommEDLAdapter:
    def test_name(self) -> None:
        a = QualcommEDLAdapter()
        assert a.name == "qualcomm_edl"
        assert DeviceType.QUALCOMM_EDL in a.supported_types

    def test_methods_exist(self) -> None:
        a = QualcommEDLAdapter()
        assert hasattr(a, "printgpt")
        assert hasattr(a, "dump_partition")
        assert hasattr(a, "flash_partition")
        assert hasattr(a, "erase_partition")
        assert hasattr(a, "safe_firehose_flash")
        assert hasattr(a, "sahara_ping")


class TestMediaTekBROMAdapter:
    def test_name(self) -> None:
        a = MediaTekBROMAdapter()
        assert a.name == "mediatek_brom"
        assert DeviceType.MTK_BROM in a.supported_types

    def test_methods_exist(self) -> None:
        a = MediaTekBROMAdapter()
        assert hasattr(a, "payload")
        assert hasattr(a, "printgpt")
        assert hasattr(a, "dump_partition")
        assert hasattr(a, "flash_partition")
        assert hasattr(a, "erase_partition")
        assert hasattr(a, "erase_multiple")
        assert hasattr(a, "handshake")
        assert hasattr(a, "bypass_sec_cfg")


class TestDiagATAdapter:
    def test_name(self) -> None:
        a = DiagATAdapter()
        assert a.name == "diag_at"
        assert DeviceType.DIAG in a.supported_types

    def test_scan_ports(self) -> None:
        a = DiagATAdapter()
        ports = a.scan_ports()
        assert isinstance(ports, list)

    def test_panic_payloads(self) -> None:
        assert len(DiagATAdapter.CRASH_PAYLOADS) >= 4


# ─── Triage Engine ──────────────────────────────────────────────────────────


class TestTriageEngine:
    def test_builds_tree(self) -> None:
        engine = TriageEngine()
        assert "start" in engine._nodes
        assert len(engine._nodes) >= 15

    def test_traverse_basic(self) -> None:
        engine = TriageEngine()
        result = engine.traverse(["No power / black screen", "Completely dead"])
        assert result.symptoms_detected == ["no_power"]
        assert "dead" in result.path

    def test_traverse_edl(self) -> None:
        engine = TriageEngine()
        result = engine.traverse(["No power / black screen", "LED/screen flash",
                                  "Qualcomm 9008 (EDL)"])
        assert "edl_mode" in result.symptoms_detected
        assert result.soc_family == "qualcomm"
        assert result.protocol == "edl"
        assert "hard-brick-qualcomm" in result.playbook_ids

    def test_traverse_bootloop(self) -> None:
        engine = TriageEngine()
        result = engine.traverse(["Bootloop / restarting", "Yes, Recovery works"])
        assert "bootloop" in result.symptoms_detected
        assert "soft-brick-bootloop" in result.playbook_ids

    def test_traverse_frp(self) -> None:
        engine = TriageEngine()
        result = engine.traverse(["FRP / Google locked", "Android 11+"])
        assert "frp_locked" in result.symptoms_detected
        assert "frp-bypass" in result.playbook_ids

    def test_auto_detect_edl(self) -> None:
        engine = TriageEngine()
        result = engine.auto_detect("edl")
        assert result.protocol == "edl"
        assert len(result.recommended_actions) > 0

    def test_to_dict(self) -> None:
        engine = TriageEngine()
        result = engine.traverse(["FRP / Google locked", "Android 11+"])
        d = result.to_dict()
        assert "playbook_ids" in d
        assert "frp-bypass" in d["playbook_ids"]


# ─── Repair Engine ──────────────────────────────────────────────────────────


class TestRepairEngine:
    def test_registers_actions(self) -> None:
        engine = RepairEngine()
        assert len(engine._actions) >= 8

    def test_list_by_type(self) -> None:
        engine = RepairEngine()
        boot_actions = engine.list_actions(RepairType.BOOT_REPAIR)
        assert len(boot_actions) >= 3

    def test_get_action(self) -> None:
        engine = RepairEngine()
        action = engine.get("boot_fastboot")
        assert action is not None
        assert action.name == "Boot Repair via Fastboot"
        assert action.protocol == "fastboot"

    def test_find_by_soc(self) -> None:
        engine = RepairEngine()
        edl_actions = engine.find(RepairType.BOOT_REPAIR, SoCTarget.QUALCOMM)
        assert any(a.id == "boot_edl" for a in edl_actions)

    def test_frp_actions_by_soc(self) -> None:
        engine = RepairEngine()
        qc = engine.find(RepairType.FRP_BYPASS, SoCTarget.QUALCOMM)
        mtk = engine.find(RepairType.FRP_BYPASS, SoCTarget.MEDIATEK)
        assert len(qc) >= 1
        assert len(mtk) >= 1

    def test_execute_with_stub_executor(self) -> None:
        engine = RepairEngine()
        calls = []

        def stub_exec(cmd: str) -> tuple[bool, str]:
            calls.append(cmd)
            return True, "OK"

        result = engine.execute("boot_fastboot", stub_exec)
        assert result["success"] is True
        assert len(calls) == 4

    def test_all_types_have_actions(self) -> None:
        engine = RepairEngine()
        for rt in RepairType:
            actions = engine.list_actions(rt)
            assert len(actions) >= 1, f"No actions for {rt.value}"


# ─── Playbook Executor (shell=False) ────────────────────────────────────────


class TestPlaybookExecutorSafety:
    def test_dry_run(self) -> None:
        executor = PlaybookExecutor()
        executor.dry_run = True
        pb = {"id": "test", "title": "Test", "steps": [{"step_number": 1, "description": "Test", "command": "shell:echo hello"}]}
        result = executor.execute(pb)
        assert result.success is True
        assert result.results[0].output.startswith("[dry-run]")

    def test_executes_without_shell_true(self) -> None:
        executor = PlaybookExecutor()
        pb = {"id": "test", "title": "Test", "steps": [{"step_number": 1, "description": "Echo", "command": "shell:python -c print(1)"}]}
        result = executor.execute(pb)
        assert result.success is True

    def test_to_dict(self) -> None:
        result = PlaybookRunResult(playbook_id="test", title="Test", success=True, steps_completed=1, total_steps=1)
        d = result.to_dict()
        assert d["playbook_id"] == "test"
        assert d["success"] is True


# ─── Diagnostics Engine ─────────────────────────────────────────────────────
class TestDiagnosticsEngine:
    def test_diagnose_bootloop(self) -> None:
        engine = DiagnosticsEngine()
        result = engine.diagnose(["bootloop"])
        assert result.confidence > 0
        assert result.risk_level == "high"

    def test_diagnose_hard_brick(self) -> None:
        engine = DiagnosticsEngine()
        result = engine.diagnose(["hard-brick"])
        assert result.risk_level == "critical"

    def test_diagnose_frp(self) -> None:
        engine = DiagnosticsEngine()
        result = engine.diagnose(["frp-lock"])
        assert result.risk_level == "medium"

    def test_no_symptoms(self) -> None:
        engine = DiagnosticsEngine()
        result = engine.diagnose([])
        assert result.diagnosis == "No symptoms provided"

    def test_to_dict(self) -> None:
        engine = DiagnosticsEngine()
        result = engine.diagnose(["bootloop"])
        d = result.to_dict()
        assert "diagnosis" in d
        assert "confidence" in d
        assert "causes" in d

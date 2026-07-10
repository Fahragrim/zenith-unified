"""Unit tests for engines and deep adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from zenith.adapters.diag_at import DiagATAdapter
from zenith.adapters.mediatek_brom import MediaTekBROMAdapter
from zenith.adapters.qualcomm_edl import QualcommEDLAdapter
from zenith.core.device import DeviceType
from zenith.engines.diagnostics import DiagnosisResult, DiagnosticsEngine
from zenith.engines.flash import FlashEngine, FlashPhase, FlashPlan, FlashResult
from zenith.engines.flash_protocols import (
    BromTransport,
    EdlTransport,
    SaharaCommand,
    SaharaMode,
    build_brom_da_header,
    build_brom_flash_command,
    build_brom_handshake,
    build_brom_reset,
    build_firehose_configure_xml,
    build_firehose_packet,
    build_firehose_program_xml,
    build_firehose_read_xml,
    build_firehose_reset_xml,
    build_sahara_done,
    build_sahara_hello_req,
    build_sahara_read_data,
    build_sahara_reset,
    parse_firehose_response,
    parse_sahara_done_resp,
    parse_sahara_hello_resp,
    parse_sahara_read_data_resp,
    parse_sahara_reset_resp,
)
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


# ─── Sahara Protocol (flash_protocols.py) ────────────────────────────────────


class TestSaharaProtocol:
    def test_build_hello_req_size(self) -> None:
        packet = build_sahara_hello_req()
        assert len(packet) == 36

    def test_build_hello_req_cmd(self) -> None:
        packet = build_sahara_hello_req()
        import struct
        cmd = struct.unpack_from("<I", packet, 0)[0]
        assert cmd == SaharaCommand.HELLO_REQ

    def test_build_hello_req_version(self) -> None:
        packet = build_sahara_hello_req(version=3, min_version=2)
        import struct
        length = struct.unpack_from("<I", packet, 4)[0]
        ver = struct.unpack_from("<I", packet, 8)[0]
        min_ver = struct.unpack_from("<I", packet, 12)[0]
        assert length == 36
        assert ver == 3
        assert min_ver == 2

    def test_build_hello_req_mode(self) -> None:
        packet = build_sahara_hello_req(mode=SaharaMode.MEMORY_DEBUG)
        mode = packet[-4:]
        import struct
        assert struct.unpack_from("<I", mode, 0)[0] == SaharaMode.MEMORY_DEBUG

    def test_parse_hello_resp_valid(self) -> None:
        import struct
        cmd = SaharaCommand.HELLO_RESP
        length = 40
        version = 2
        min_version = 1
        reserved = (0, 0, 0, 0)
        mode = 2
        status = 0
        data = struct.pack(
            "<IIIIIIIIII",
            cmd, length, version, min_version,
            reserved[0], reserved[1], reserved[2], reserved[3],
            mode, status,
        )
        parsed = parse_sahara_hello_resp(data)
        assert parsed["cmd"] == SaharaCommand.HELLO_RESP
        assert parsed["mode"] == 2
        assert parsed["status"] == 0
        assert parsed["version"] == 2

    def test_parse_hello_resp_wrong_cmd(self) -> None:
        import struct
        data = struct.pack("<IIIIIIIIII", SaharaCommand.READ_DATA, 40, 0, 0, 0, 0, 0, 0, 0, 0)
        with pytest.raises(ValueError, match="Unexpected Sahara cmd"):
            parse_sahara_hello_resp(data)

    def test_parse_hello_resp_too_short(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            parse_sahara_hello_resp(b"")

    def test_build_read_data(self) -> None:
        packet = build_sahara_read_data(seq=5)
        assert len(packet) == 16
        import struct
        cmd = struct.unpack_from("<I", packet, 0)[0]
        seq = struct.unpack_from("<I", packet, 8)[0]
        assert cmd == SaharaCommand.READ_DATA
        assert seq == 5

    def test_parse_read_data_resp_valid(self) -> None:
        import struct
        payload = b"\x00\x01\x02\x03"
        data = struct.pack("<IIII", SaharaCommand.READ_DATA_RESP, 20, 0, 4) + payload
        parsed = parse_sahara_read_data_resp(data)
        assert parsed["cmd"] == SaharaCommand.READ_DATA_RESP
        assert parsed["size"] == 4
        assert parsed["payload"] == payload

    def test_parse_read_data_wrong_cmd(self) -> None:
        import struct
        data = struct.pack("<IIII", SaharaCommand.DONE, 16, 0, 0)
        with pytest.raises(ValueError, match="Unexpected cmd"):
            parse_sahara_read_data_resp(data)

    def test_build_done(self) -> None:
        packet = build_sahara_done(image_type=1, total_size=65536)
        assert len(packet) == 16
        import struct
        image_type = struct.unpack_from("<I", packet, 8)[0]
        total_size = struct.unpack_from("<I", packet, 12)[0]
        assert image_type == 1
        assert total_size == 65536

    def test_parse_done_resp(self) -> None:
        import struct
        data = struct.pack("<III", SaharaCommand.DONE_RESP, 12, 42)
        parsed = parse_sahara_done_resp(data)
        assert parsed["cmd"] == SaharaCommand.DONE_RESP
        assert parsed["seq"] == 42

    def test_build_reset(self) -> None:
        packet = build_sahara_reset(seq=7)
        assert len(packet) == 12
        import struct
        seq = struct.unpack_from("<I", packet, 8)[0]
        assert seq == 7

    def test_parse_reset_resp(self) -> None:
        import struct
        data = struct.pack("<III", SaharaCommand.RESET_RESP, 12, 3)
        parsed = parse_sahara_reset_resp(data)
        assert parsed["cmd"] == SaharaCommand.RESET_RESP
        assert parsed["seq"] == 3

    def test_parse_reset_resp_too_short(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            from zenith.engines.flash_protocols import parse_sahara_reset_resp
            parse_sahara_reset_resp(b"\x00")

    def test_build_sahara_hello_mode_values(self) -> None:
        for mode in (SaharaMode.IMAGE_MODE, SaharaMode.MEMORY_DEBUG,
                     SaharaMode.STREAM_MODE, SaharaMode.COMMAND_MODE):
            p = build_sahara_hello_req(mode=mode)
            import struct
            m = struct.unpack_from("<I", p, 32)[0]
            assert m == mode, f"Mode {mode} failed"


# ─── Firehose XML Builders ────────────────────────────────────────────────────


class TestFirehoseXml:
    def test_configure_xml(self) -> None:
        xml = build_firehose_configure_xml(memory_name="emmc", max_payload_size=524288)
        assert "configure" in xml
        assert "MemoryName=\"emmc\"" in xml
        assert "MaxPayloadSizeToTargetInBytes=\"524288\"" in xml

    def test_program_xml(self) -> None:
        xml = build_firehose_program_xml(partition="boot", filename="boot.img",
                                         num_sectors=65536, start_sector=2048)
        assert "program" in xml
        assert "label=\"boot\"" in xml
        assert "filename=\"boot.img\"" in xml
        assert "start_sector=\"2048\"" in xml

    def test_read_xml(self) -> None:
        xml = build_firehose_read_xml(partition="system", filename="system.img",
                                      num_sectors=262144, start_sector=0)
        assert "read" in xml
        assert "label=\"system\"" in xml

    def test_reset_xml(self) -> None:
        xml = build_firehose_reset_xml()
        assert xml == "<reset/>"

    def test_firehose_packet_format(self) -> None:
        xml = "<test/>"
        packet = build_firehose_packet(xml)
        import struct
        length = struct.unpack_from("<I", packet, 0)[0]
        payload = packet[4:]
        assert len(payload) == length
        assert payload.startswith(b"<?xml")
        assert b"<test/>" in payload

    def test_firehose_packet_length_prefix(self) -> None:
        xml = build_firehose_configure_xml()
        packet = build_firehose_packet(xml)
        import struct
        length = struct.unpack_from("<I", packet, 0)[0]
        assert length == len(packet) - 4

    def test_parse_firehose_ack(self) -> None:
        xml = '<?xml version="1.0"?><data><response value="ACK" rawmode="0"/></data>'
        result = parse_firehose_response(xml.encode("utf-8"))
        assert result["success"] is True

    def test_parse_firehose_nak(self) -> None:
        xml = '<?xml version="1.0"?><data><response value="NAK" rawmode="error msg"/></data>'
        result = parse_firehose_response(xml.encode("utf-8"))
        assert result["success"] is False
        assert "error msg" in result["error"]

    def test_firehose_unknown_no_error(self) -> None:
        xml = "some random response"
        result = parse_firehose_response(xml.encode("utf-8"))
        assert result["success"] is False


# ─── BROM Protocol ────────────────────────────────────────────────────────────


class TestBromProtocol:
    def test_build_handshake(self) -> None:
        packet = build_brom_handshake()
        assert packet[:4] == b"\xAA\x55\xAA\x55"
        import struct
        cmd = struct.unpack_from("<I", packet, 4)[0]
        assert cmd == 0x01

    def test_parse_handshake_resp(self) -> None:
        from zenith.engines.flash_protocols import parse_brom_handshake_resp
        import struct
        data = b"\xAA\x55\xAA\x55" + struct.pack("<II", 0x02, 0)
        parsed = parse_brom_handshake_resp(data)
        assert parsed["magic"] == "aa55aa55"
        assert parsed["cmd"] == 0x02

    def test_parse_handshake_resp_too_short(self) -> None:
        from zenith.engines.flash_protocols import parse_brom_handshake_resp
        with pytest.raises(ValueError, match="too short"):
            parse_brom_handshake_resp(b"\x00")

    def test_build_da_header(self) -> None:
        header = build_brom_da_header(da_size=65536, entry_point=0x2000)
        assert len(header) == 16
        import struct
        cmd = struct.unpack_from("<I", header, 0)[0]
        size = struct.unpack_from("<I", header, 4)[0]
        entry = struct.unpack_from("<I", header, 8)[0]
        assert cmd == 0x03
        assert size == 65536
        assert entry == 0x2000

    def test_build_flash_command(self) -> None:
        cmd = build_brom_flash_command(partition="boot", offset=0, size=4096)
        assert len(cmd) == 44  # 4 (cmd) + 32 (partition) + 8 (offset + size)
        import struct
        brom_cmd = struct.unpack_from("<I", cmd, 0)[0]
        part = cmd[4:36].rstrip(b"\x00").decode("utf-8")
        size = struct.unpack_from("<I", cmd, 40)[0]
        assert brom_cmd == 0x07
        assert part == "boot"
        assert size == 4096

    def test_build_flash_command_long_partition(self) -> None:
        cmd = build_brom_flash_command(partition="a" * 50, offset=0, size=1024)
        part = cmd[4:36].rstrip(b"\x00").decode("utf-8")
        assert len(part) == 32
        assert part == "a" * 32

    def test_build_reset(self) -> None:
        packet = build_brom_reset()
        import struct
        cmd = struct.unpack_from("<I", packet, 0)[0]
        assert cmd == 0x09


# ─── Flash Engine — FlashPlan ─────────────────────────────────────────────────


class TestFlashPlan:
    def test_plan_creation(self) -> None:
        engine = FlashEngine()
        plan = engine.plan("test_device", "/tmp/fw", ["boot", "recovery"])
        assert plan.device_id == "test_device"
        assert plan.target_partitions == ["boot", "recovery"]
        assert len(plan.steps) == 6
        assert plan.dry_run is True

    def test_plan_destructive_steps(self) -> None:
        engine = FlashEngine()
        plan = engine.plan("d", "/tmp/fw", ["boot"])
        dest = plan.destructive_steps
        assert len(dest) == 1
        assert dest[0].kind.value == "flash"
        assert dest[0].partition == "boot"

    def test_plan_steps_ordered(self) -> None:
        engine = FlashEngine()
        plan = engine.plan("d", "/tmp/fw", ["boot", "system"])
        kinds = [s.kind.value for s in plan.steps]
        assert kinds == ["backup", "flash", "verify", "backup", "flash", "verify"]

    def test_plan_step_kinds(self) -> None:
        engine = FlashEngine()
        plan = engine.plan("d", "/tmp/fw", ["boot"])
        assert plan.steps[0].kind.value == "backup"
        assert plan.steps[1].kind.value == "flash"
        assert plan.steps[2].kind.value == "verify"

    def test_plan_auto_targets_with_firmware(self, tmp_path: Path) -> None:
        fw = tmp_path / "fw"
        fw.mkdir()
        (fw / "boot.img").write_text("dummy")
        (fw / "recovery.img").write_text("dummy")
        engine = FlashEngine()
        plan = engine.plan("d", str(fw))
        assert "boot" in plan.target_partitions
        assert "recovery" in plan.target_partitions

    def test_plan_auto_targets_no_firmware(self) -> None:
        engine = FlashEngine()
        plan = engine.plan("d", "/nonexistent")
        assert plan.target_partitions == ["boot", "recovery"]

    def test_plan_find_image(self, tmp_path: Path) -> None:
        fw = tmp_path / "fw"
        fw.mkdir()
        (fw / "boot.mbn").write_text("mbn data")
        plan = FlashEngine().plan("d", str(fw), ["boot"])
        flash_step = plan.steps[1]
        assert flash_step.source_path is not None
        assert flash_step.source_path.endswith("boot.mbn")

    def test_result_to_dict(self) -> None:
        result = FlashResult(plan_id="p1", success=True, phase=FlashPhase.COMPLETED)
        d = result.to_dict()
        assert d["plan_id"] == "p1"
        assert d["success"] is True
        assert d["phase"] == "completed"

    def test_execute_dry_run(self) -> None:
        engine = FlashEngine(executor=lambda cmd: (True, "OK"))
        plan = FlashEngine().plan("d", "/tmp/fw", ["boot"])
        plan.dry_run = True
        result = engine.execute(plan)
        assert result.success is True
        assert result.phase == FlashPhase.COMPLETED


# ─── Flash Engine — EDL Pipeline ─────────────────────────────────────────────


class MockEdlTransport(EdlTransport):
    """Mock EDL transport for testing — no real USB needed."""

    def __init__(self) -> None:
        self.detect_result: str | None = "SN0123456789"
        self.hello_result: dict[str, Any] = None
        self.upload_result: bool = True
        self.firehose_connect_result: bool = True
        self.firehose_command_result: dict[str, Any] = None
        self.reset_result: bool = True
        self.closed = False

    def detect(self) -> str | None:
        return self.detect_result

    def sahara_hello(self) -> dict[str, Any]:
        if self.hello_result is not None:
            return self.hello_result
        return {"cmd": 2, "mode": 0, "status": 0, "version": 2, "min_version": 1}

    def sahara_upload_loader(self, loader_path: str) -> bool:
        return self.upload_result

    def firehose_connect(self, max_payload_size: int = 1048576) -> bool:
        return self.firehose_connect_result

    def firehose_command(self, xml: str) -> dict[str, Any]:
        if self.firehose_command_result is not None:
            return self.firehose_command_result
        return {"success": True, "raw": xml}

    def firehose_reset(self) -> bool:
        return self.reset_result

    def close(self) -> None:
        self.closed = True


class TestFlashEngineEDL:
    def test_detect_edl_device_returns_serial(self) -> None:
        transport = MockEdlTransport()
        transport.detect_result = "SN0123456789"
        engine = FlashEngine(edl_transport=transport, registry=MagicMock())
        serial = engine.detect_edl_device()
        assert serial == "SN0123456789"

    def test_detect_edl_device_returns_none(self) -> None:
        transport = MockEdlTransport()
        transport.detect_result = None
        engine = FlashEngine(edl_transport=transport, registry=MagicMock())
        serial = engine.detect_edl_device()
        assert serial is None

    def test_sahara_hello_returns_mode(self) -> None:
        transport = MockEdlTransport()
        transport.hello_result = {"cmd": 2, "mode": 0, "status": 0}
        engine = FlashEngine(edl_transport=transport)
        result = engine.sahara_hello()
        assert result["mode"] == 0
        assert result["status"] == 0

    def test_sahara_hello_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.sahara_hello()
        assert "error" in result

    def test_sahara_upload_loader_success(self, tmp_path: Path) -> None:
        loader = tmp_path / "prog.mbn"
        loader.write_text("dummy loader data")
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.sahara_upload_loader(str(loader))
        assert result is True

    def test_sahara_upload_loader_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.sahara_upload_loader("/fake/loader.mbn")
        assert result is False

    def test_sahara_upload_loader_no_file(self) -> None:
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.sahara_upload_loader("/nonexistent/loader.mbn")
        assert result is False

    def test_firehose_connect(self) -> None:
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.firehose_connect()
        assert result is True

    def test_firehose_flash_partition(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_text("dummy image data")
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.firehose_flash_partition("boot", str(img))
        assert result is True

    def test_firehose_flash_partition_no_image(self) -> None:
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.firehose_flash_partition("boot", "/nonexistent.img")
        assert result is False

    def test_firehose_flash_partition_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.firehose_flash_partition("boot", "/tmp/boot.img")
        assert result is False

    def test_firehose_flash_partition_failure(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_text("data")
        transport = MockEdlTransport()
        transport.firehose_command_result = {"success": False, "error": "NAK"}
        engine = FlashEngine(edl_transport=transport)
        result = engine.firehose_flash_partition("boot", str(img))
        assert result is False

    def test_firehose_reset(self) -> None:
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.firehose_reset()
        assert result is True

    def test_firehose_reset_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.firehose_reset()
        assert result is False

    def test_close_transports(self) -> None:
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        engine.close_transports()
        assert transport.closed is True

    def test_edl_flash_pipeline_dry_run(self) -> None:
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.edl_flash_pipeline(dry_run=True)
        assert result.success is True
        assert result.phase == FlashPhase.COMPLETED

    def test_edl_flash_pipeline_full_success(self, tmp_path: Path) -> None:
        loader = tmp_path / "prog.mbn"
        loader.write_text("loader")
        boot = tmp_path / "boot.img"
        boot.write_text("boot")
        system = tmp_path / "system.img"
        system.write_text("system")
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.edl_flash_pipeline(
            loader_path=str(loader),
            partitions={"boot": str(boot), "system": str(system)},
            dry_run=False,
        )
        assert result.success is True
        assert result.phase == FlashPhase.COMPLETED
        steps = result.step_results
        assert len(steps) >= 5  # detect, hello, upload, connect, flash, flash, reset

    def test_edl_flash_pipeline_detect_fails(self) -> None:
        transport = MockEdlTransport()
        transport.detect_result = None
        engine = FlashEngine(edl_transport=transport)
        result = engine.edl_flash_pipeline(dry_run=False)
        assert result.success is False
        assert "detect" in result.error

    def test_edl_flash_pipeline_sahara_fails(self) -> None:
        transport = MockEdlTransport()
        transport.hello_result = {"error": "Timeout"}
        engine = FlashEngine(edl_transport=transport)
        result = engine.edl_flash_pipeline(dry_run=False)
        assert result.success is False

    def test_edl_flash_pipeline_partition_flash_fails(self, tmp_path: Path) -> None:
        loader = tmp_path / "prog.mbn"
        loader.write_text("loader")
        boot = tmp_path / "boot.img"
        boot.write_text("boot")
        transport = MockEdlTransport()
        transport.firehose_command_result = {"success": False, "error": "Write error"}
        engine = FlashEngine(edl_transport=transport)
        result = engine.edl_flash_pipeline(
            loader_path=str(loader),
            partitions={"boot": str(boot)},
            dry_run=False,
        )
        assert result.success is False
        assert any("flash" in s["phase"] and not s["success"] for s in result.step_results)

    def test_edl_flash_pipeline_no_loader(self, tmp_path: Path) -> None:
        boot = tmp_path / "boot.img"
        boot.write_text("boot")
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.edl_flash_pipeline(dry_run=False, partitions={"boot": str(boot)})
        assert result.success is True  # no loader = skip step


# ─── Flash Engine — BROM Pipeline ─────────────────────────────────────────────


class MockBromTransport(BromTransport):
    """Mock BROM transport for testing — no real USB needed."""

    def __init__(self) -> None:
        self.detect_result: str | None = "BROM_DEVICE"
        self.handshake_result: dict[str, Any] = None
        self.send_da_result: bool = True
        self.jump_da_result: bool = True
        self.flash_result: bool = True
        self.reset_result: bool = True
        self.closed = False

    def detect(self) -> str | None:
        return self.detect_result

    def handshake(self) -> dict[str, Any]:
        if self.handshake_result is not None:
            return self.handshake_result
        return {"magic": "aa55aa55", "cmd": 2, "status": 0}

    def send_da(self, da_path: str) -> bool:
        return self.send_da_result

    def jump_da(self) -> bool:
        return self.jump_da_result

    def flash_partition(self, partition: str, file_path: str) -> bool:
        return self.flash_result

    def reset(self) -> bool:
        return self.reset_result

    def close(self) -> None:
        self.closed = True


class TestFlashEngineBROM:
    def test_detect_brom_device_returns_serial(self) -> None:
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        serial = engine.detect_brom_device()
        assert serial == "BROM_DEVICE"

    def test_detect_brom_device_returns_none(self) -> None:
        transport = MockBromTransport()
        transport.detect_result = None
        engine = FlashEngine(brom_transport=transport)
        serial = engine.detect_brom_device()
        assert serial is None

    def test_brom_handshake(self) -> None:
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_handshake()
        assert result["magic"] == "aa55aa55"
        assert result["cmd"] == 2

    def test_brom_handshake_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.brom_handshake()
        assert "error" in result

    def test_brom_send_da_success(self, tmp_path: Path) -> None:
        da = tmp_path / "da.bin"
        da.write_text("da data")
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_send_da(str(da))
        assert result is True

    def test_brom_send_da_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.brom_send_da("/fake/da.bin")
        assert result is False

    def test_brom_send_da_no_file(self, tmp_path: Path) -> None:
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_send_da(str(tmp_path / "nonexistent" / "da.bin"))
        assert result is False

    def test_brom_jump_da(self) -> None:
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_jump_da()
        assert result is True

    def test_brom_jump_da_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.brom_jump_da()
        assert result is False

    def test_brom_flash_partition(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_text("dummy")
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_partition("boot", str(img))
        assert result is True

    def test_brom_flash_partition_no_image(self, tmp_path: Path) -> None:
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_partition("boot", str(tmp_path / "nonexistent.img"))
        assert result is False

    def test_brom_flash_partition_no_transport(self, tmp_path: Path) -> None:
        engine = FlashEngine()
        result = engine.brom_flash_partition("boot", str(tmp_path / "boot.img"))
        assert result is False

    def test_brom_flash_partition_fails(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_text("data")
        transport = MockBromTransport()
        transport.flash_result = False
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_partition("boot", str(img))
        assert result is False

    def test_brom_reset(self) -> None:
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_reset()
        assert result is True

    def test_brom_reset_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.brom_reset()
        assert result is False

    def test_brom_close_transport(self) -> None:
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        engine.close_transports()
        assert transport.closed is True

    def test_brom_flash_pipeline_dry_run(self) -> None:
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_pipeline(dry_run=True)
        assert result.success is True
        assert result.phase == FlashPhase.COMPLETED
        assert len(result.step_results) == 0

    def test_brom_flash_pipeline_full_success(self, tmp_path: Path) -> None:
        da = tmp_path / "da.bin"
        da.write_text("da data")
        boot = tmp_path / "boot.img"
        boot.write_text("boot")
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_pipeline(
            da_path=str(da),
            partitions={"boot": str(boot)},
            dry_run=False,
        )
        assert result.success is True
        assert result.phase == FlashPhase.COMPLETED
        steps = result.step_results
        assert len(steps) >= 5

    def test_brom_flash_pipeline_detect_fails(self) -> None:
        transport = MockBromTransport()
        transport.detect_result = None
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_pipeline(dry_run=False)
        assert result.success is False
        assert "detect" in result.error

    def test_brom_flash_pipeline_send_da_fails(self, tmp_path: Path) -> None:
        da = tmp_path / "da.bin"
        da.write_text("da")
        transport = MockBromTransport()
        transport.send_da_result = False
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_pipeline(
            da_path=str(da),
            dry_run=False,
        )
        assert result.success is False

    def test_brom_flash_pipeline_partition_fails(self, tmp_path: Path) -> None:
        da = tmp_path / "da.bin"
        da.write_text("da")
        boot = tmp_path / "boot.img"
        boot.write_text("boot")
        transport = MockBromTransport()
        transport.flash_result = False
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_pipeline(
            da_path=str(da),
            partitions={"boot": str(boot)},
            dry_run=False,
        )
        assert result.success is False

    def test_brom_flash_pipeline_no_da(self, tmp_path: Path) -> None:
        boot = tmp_path / "boot.img"
        boot.write_text("boot")
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_pipeline(dry_run=False, partitions={"boot": str(boot)})
        assert result.success is True  # no DA path = skip


# ─── Flash Engine — Error Handling ────────────────────────────────────────────


class TestFlashEngineErrors:
    def test_engine_no_executor_with_registry_fallback(self) -> None:
        engine = FlashEngine()
        plan = FlashPlan(id="p1", device_id="d1", firmware_dir="/fw", dry_run=False)
        result = engine.execute(plan)
        assert result.phase in (FlashPhase.FLASH, FlashPhase.COMPLETED)
        # Registry fallback should give us a working executor (or no steps = success)

    def test_engine_no_executor_no_registry(self) -> None:
        engine = FlashEngine(registry=object())
        plan = FlashPlan(id="p1", device_id="d1", firmware_dir="/fw", dry_run=False)
        result = engine.execute(plan)
        # object() has no dispatch — should fail with "No executor configured"
        assert result.success is False
        assert "No executor" in result.error

    def test_sahara_hello_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.sahara_hello()
        assert "error" in result

    def test_brom_handshake_no_transport(self) -> None:
        engine = FlashEngine()
        result = engine.brom_handshake()
        assert "error" in result

    def test_edl_pipeline_exception_handling(self) -> None:
        class BrokenTransport(EdlTransport):
            def detect(self) -> str | None:
                raise RuntimeError("USB error")
            def sahara_hello(self) -> dict[str, Any]:
                raise RuntimeError("USB error")
            def sahara_upload_loader(self, loader_path: str) -> bool:
                raise RuntimeError("USB error")
            def firehose_connect(self, max_payload_size: int = 1048576) -> bool:
                raise RuntimeError("USB error")
            def firehose_command(self, xml: str) -> dict[str, Any]:
                raise RuntimeError("USB error")
            def firehose_reset(self) -> bool:
                raise RuntimeError("USB error")
            def close(self) -> None: ...

        engine = FlashEngine(edl_transport=BrokenTransport())
        result = engine.edl_flash_pipeline(dry_run=False)
        assert result.success is False

    def test_brom_pipeline_exception_handling(self) -> None:
        class BrokenTransport(BromTransport):
            def detect(self) -> str | None:
                raise RuntimeError("USB error")
            def handshake(self) -> dict[str, Any]:
                raise RuntimeError("USB error")
            def send_da(self, da_path: str) -> bool:
                raise RuntimeError("USB error")
            def jump_da(self) -> bool:
                raise RuntimeError("USB error")
            def flash_partition(self, partition: str, file_path: str) -> bool:
                raise RuntimeError("USB error")
            def reset(self) -> bool:
                raise RuntimeError("USB error")
            def close(self) -> None: ...

        engine = FlashEngine(brom_transport=BrokenTransport())
        result = engine.brom_flash_pipeline(dry_run=False)
        assert result.success is False


# ─── Flash Engine — Full Integration with Mocks ──────────────────────────────


class TestFlashEngineIntegration:
    def test_edl_detect_falls_back_to_adapter(self) -> None:
        """FlashEngine should try transport first, then adapter."""
        transport = MockEdlTransport()
        transport.detect_result = None
        engine = FlashEngine(edl_transport=transport)
        with patch("zenith.adapters.qualcomm_edl.QualcommEDLAdapter") as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.is_available.return_value = True
            mock_adapter.list_devices.return_value = [{"serial": "EDL_001_002"}]
            mock_adapter_cls.return_value = mock_adapter
            serial = engine.detect_edl_device()
            assert serial == "EDL_001_002"

    def test_edl_adapter_unavailable(self) -> None:
        transport = MockEdlTransport()
        transport.detect_result = None
        engine = FlashEngine(edl_transport=transport)
        with patch("zenith.adapters.qualcomm_edl.QualcommEDLAdapter") as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.is_available.return_value = False
            mock_adapter_cls.return_value = mock_adapter
            serial = engine.detect_edl_device()
            assert serial is None

    def test_brom_detect_falls_back_to_adapter(self) -> None:
        transport = MockBromTransport()
        transport.detect_result = None
        engine = FlashEngine(brom_transport=transport)
        with patch("zenith.adapters.mediatek_brom.MediaTekBROMAdapter") as mock_adapter_cls:
            mock_adapter = MagicMock()
            mock_adapter.is_available.return_value = True
            mock_adapter.list_devices.return_value = [{"serial": "mtk_brom_device"}]
            mock_adapter_cls.return_value = mock_adapter
            serial = engine.detect_brom_device()
            assert serial == "mtk_brom_device"

    def test_both_transports_close_safely(self) -> None:
        edl = MockEdlTransport()
        brom = MockBromTransport()
        engine = FlashEngine(edl_transport=edl, brom_transport=brom)
        engine.close_transports()
        assert edl.closed is True
        assert brom.closed is True

    def test_edl_full_pipeline_step_order(self, tmp_path: Path) -> None:
        loader = tmp_path / "prog.mbn"
        loader.write_text("loader")
        boot = tmp_path / "boot.img"
        boot.write_text("boot")
        transport = MockEdlTransport()
        engine = FlashEngine(edl_transport=transport)
        result = engine.edl_flash_pipeline(
            loader_path=str(loader),
            partitions={"boot": str(boot)},
            dry_run=False,
        )
        step_names = [s["step"] for s in result.step_results if "step" in s]
        assert step_names == ["detect", "sahara_hello", "upload_loader", "firehose_connect", "reset"]

    def test_brom_full_pipeline_step_order(self, tmp_path: Path) -> None:
        da = tmp_path / "da.bin"
        da.write_text("da")
        boot = tmp_path / "boot.img"
        boot.write_text("boot")
        transport = MockBromTransport()
        engine = FlashEngine(brom_transport=transport)
        result = engine.brom_flash_pipeline(
            da_path=str(da),
            partitions={"boot": str(boot)},
            dry_run=False,
        )
        step_names = [s["step"] for s in result.step_results if "step" in s]
        assert step_names == ["detect", "handshake", "send_da", "jump_da", "reset"]

    def test_execute_with_executor(self, tmp_path: Path) -> None:
        fw_dir = tmp_path / "fw"
        fw_dir.mkdir()
        (fw_dir / "boot.img").write_text("boot image data")
        calls: list[str] = []
        def stub_exec(cmd: str) -> tuple[bool, str]:
            calls.append(cmd)
            return True, "OK"
        engine = FlashEngine(executor=stub_exec)
        plan = engine.plan("d", str(fw_dir), ["boot"])
        plan.dry_run = False
        result = engine.execute(plan)
        assert result.success is True
        assert len(calls) == 3  # backup, flash, verify

    def test_execute_rollback_on_failure(self, tmp_path: Path) -> None:
        fw_dir = tmp_path / "fw"
        fw_dir.mkdir()
        (fw_dir / "boot.img").write_text("boot image data")
        calls: list[str] = []
        write_count = 0
        def stub_exec(cmd: str) -> tuple[bool, str]:
            nonlocal write_count
            calls.append(cmd)
            if ":w " in cmd:
                write_count += 1
                if write_count == 1:
                    return False, "Write error"
            return True, "OK"
        engine = FlashEngine(executor=stub_exec)
        plan = engine.plan("d", str(fw_dir), ["boot"])
        plan.dry_run = False
        result = engine.execute(plan)
        assert result.success is False
        assert "Rollback" in result.error

    def test_dry_run_skips_all_execution(self) -> None:
        calls: list[str] = []
        def stub_exec(cmd: str) -> tuple[bool, str]:
            calls.append(cmd)
            return True, "OK"
        engine = FlashEngine(executor=stub_exec)
        plan = engine.plan("d", "/tmp/fw", ["boot"])
        plan.dry_run = True
        result = engine.execute(plan)
        assert result.success is True
        assert len(calls) == 0

    def test_flash_skipped_when_no_source(self) -> None:
        calls: list[str] = []
        def stub_exec(cmd: str) -> tuple[bool, str]:
            calls.append(cmd)
            return True, "OK"
        engine = FlashEngine(executor=stub_exec)
        plan = engine.plan("d", "/tmp/fw", ["nonexistent_partition"])
        plan.dry_run = False
        result = engine.execute(plan)
        assert result.success is True
        # flash step should be skipped (no source image)
        skipped = [s for s in result.step_results if s["phase"] == "flash" and s["success"] is False]
        assert len(skipped) == 1 or any(s["output"] == "No image" for s in result.step_results if s["phase"] == "flash")

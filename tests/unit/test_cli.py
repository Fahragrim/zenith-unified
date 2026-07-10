"""Unit tests for zenith CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from zenith.cli.main import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_kb(tmp_path: Path) -> Path:
    atlas = tmp_path / "DEEP_ATLAS.md"
    atlas.write_text("# Test atlas\n## Qualcomm Snapdragon\n- EDL Mode\n## hard-brick-qualcomm\n- Symptom: hard-brick\n- Risk: high\n")
    return atlas


class TestMainEntry:
    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Zenith Unified" in result.output

    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output.lower() or "0." in result.output


class TestVersionCommand:
    def test_version_output(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "Zenith Unified" in result.output


class TestPlaybooksCommand:
    @patch("zenith.knowledge.knowledge_base.KnowledgeBase")
    def test_list_playbooks(self, mock_kb_cls: MagicMock, runner: CliRunner) -> None:
        from zenith.knowledge.atlas_parser import Playbook

        mock_inst = MagicMock()
        mock_inst.find_playbook.return_value = [
            Playbook(id="test-1", title="Test PB", symptom="bootloop", risk_level="medium", steps=[{"step": 1, "desc": "test"}]),
        ]
        mock_kb_cls.return_value = mock_inst

        from zenith.knowledge import knowledge_base
        old = knowledge_base._kb_instance
        knowledge_base._kb_instance = mock_inst
        try:
            result = runner.invoke(main, ["playbooks", "--soc", "qualcomm"])
            assert result.exit_code == 0
            assert "Test PB" in result.output
        finally:
            knowledge_base._kb_instance = old


class TestRepairCommand:
    @patch("zenith.knowledge.knowledge_base.KnowledgeBase")
    @patch("zenith.engines.playbook_executor.PlaybookExecutor")
    def test_repair_playbook_not_found(
        self, mock_exec_cls: MagicMock, mock_kb_cls: MagicMock, runner: CliRunner
    ) -> None:
        mock_inst = MagicMock()
        mock_inst.get_playbook.return_value = None
        mock_kb_cls.return_value = mock_inst

        from zenith.knowledge import knowledge_base
        old = knowledge_base._kb_instance
        knowledge_base._kb_instance = mock_inst
        try:
            result = runner.invoke(main, ["repair", "nonexistent"])
            assert "not found" in result.output.lower()
        finally:
            knowledge_base._kb_instance = old

    @patch("zenith.knowledge.knowledge_base.KnowledgeBase")
    @patch("zenith.engines.playbook_executor.PlaybookExecutor")
    def test_repair_dry_run(
        self, mock_exec_cls: MagicMock, mock_kb_cls: MagicMock, runner: CliRunner
    ) -> None:
        from zenith.knowledge.atlas_parser import Playbook

        pb = Playbook(id="test-pb", title="Test Repair", symptom="bootloop", risk_level="low", steps=[])
        mock_inst = MagicMock()
        mock_inst.get_playbook.return_value = pb
        mock_kb_cls.return_value = mock_inst

        mock_exec = MagicMock()
        mock_exec.execute.return_value = MagicMock(
            success=True, steps_completed=0, total_steps=0, results=[], error=""
        )
        mock_exec_cls.return_value = mock_exec

        from zenith.knowledge import knowledge_base
        old = knowledge_base._kb_instance
        knowledge_base._kb_instance = mock_inst
        try:
            result = runner.invoke(main, ["repair", "test-pb", "--dry-run"])
            assert result.exit_code == 0
            assert "DRY RUN" in result.output
        finally:
            knowledge_base._kb_instance = old


class TestArsenalCommand:
    @patch("zenith.knowledge.knowledge_base.KnowledgeBase")
    def test_arsenal(self, mock_kb_cls: MagicMock, runner: CliRunner) -> None:
        from zenith.knowledge.atlas_parser import AtlasData, SOCInfo

        data = AtlasData()
        data.socs["qualcomm"] = SOCInfo(name="Qualcomm Snapdragon", manufacturer="Qualcomm")
        mock_inst = MagicMock()
        mock_inst.data = data
        mock_kb_cls.return_value = mock_inst

        from zenith.knowledge import knowledge_base
        old = knowledge_base._kb_instance
        knowledge_base._kb_instance = mock_inst
        try:
            result = runner.invoke(main, ["arsenal"])
            assert result.exit_code == 0
            assert "qualcomm" in result.output.lower()
        finally:
            knowledge_base._kb_instance = old


class TestDiscoverCommand:
    @patch("zenith.core.discovery.run_discovery")
    def test_discover(self, mock_disc: MagicMock, runner: CliRunner) -> None:
        mock_result = MagicMock()
        mock_result.summary_lines = ["=== ZENITH DEVICE DISCOVERY ===", "", "[ADB]", "  emulator-5554  device"]
        mock_disc.return_value = mock_result
        result = runner.invoke(main, ["discover", "--no-color"])
        assert result.exit_code == 0
        assert "device" in result.output.lower()

    @patch("zenith.core.discovery.run_discovery", side_effect=RuntimeError("ADB not found"))
    def test_discover_error(self, mock_disc: MagicMock, runner: CliRunner) -> None:
        result = runner.invoke(main, ["discover"])
        assert result.exit_code == 1
        assert "Discovery error" in result.output


class TestAuditCommands:
    @patch("zenith.core.audit.AuditLog")
    def test_audit_show(self, mock_log_cls: MagicMock, runner: CliRunner) -> None:
        mock_inst = MagicMock()
        mock_inst.tail.return_value = []
        mock_log_cls.return_value = mock_inst
        result = runner.invoke(main, ["audit", "show"])
        assert result.exit_code == 0

    @patch("zenith.core.audit.AuditLog")
    def test_audit_verify_ok(self, mock_log_cls: MagicMock, runner: CliRunner) -> None:
        mock_inst = MagicMock()
        mock_inst.verify_chain.return_value = True
        mock_log_cls.return_value = mock_inst
        result = runner.invoke(main, ["audit", "verify"])
        assert result.exit_code == 0

    @patch("zenith.core.audit.AuditLog")
    def test_audit_verify_broken(self, mock_log_cls: MagicMock, runner: CliRunner) -> None:
        mock_inst = MagicMock()
        mock_inst.verify_chain.return_value = False
        mock_log_cls.return_value = mock_inst
        result = runner.invoke(main, ["audit", "verify"])
        assert result.exit_code == 0
        assert "BROKEN" in result.output


class TestMCPCommand:
    @patch("zenith.ai.mcp.list_tools", return_value=["tool1", "tool2"])
    def test_mcp(self, mock_list: MagicMock, runner: CliRunner) -> None:
        result = runner.invoke(main, ["mcp"])
        assert result.exit_code == 0
        assert "2" in result.output or "tools" in result.output.lower()


class TestServerCommand:
    def test_server(self, runner: CliRunner) -> None:
        import sys
        from unittest.mock import MagicMock, patch

        mock_uvicorn = MagicMock()
        with patch.dict(sys.modules, {"uvicorn": mock_uvicorn}):
            result = runner.invoke(main, ["server", "--host", "127.0.0.1", "--port", "9999"])
        assert result.exit_code == 0


class TestVerboseFlag:
    def test_verbose(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--verbose", "version"])
        assert result.exit_code == 0

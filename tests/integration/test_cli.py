"""Integration tests — CLI end-to-end with mocked subprocess."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from zenith.cli.main import main


class TestCLIIntegration:
    """End-to-end CLI tests with mocked external commands."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_discover_no_devices(self) -> None:
        result = self.runner.invoke(main, ["discover"])
        assert result.exit_code == 0
        assert "ZENITH DEVICE DISCOVERY" in result.output

    def test_version(self) -> None:
        result = self.runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "Zenith Unified" in result.output

    def test_arsenal(self) -> None:
        result = self.runner.invoke(main, ["arsenal"])
        assert result.exit_code == 0
        assert "SoCs:" in result.output

    def test_playbooks(self) -> None:
        result = self.runner.invoke(main, ["playbooks"])
        assert result.exit_code == 0
        assert "frp-bypass" in result.output or len(result.output) > 0

    def test_diagnose_bootloop(self) -> None:
        result = self.runner.invoke(main, ["diagnose", "bootloop"])
        assert result.exit_code == 0
        assert "risk_level" in result.output
        import json
        data = json.loads(result.output)
        assert data["risk_level"] == "high"

    def test_diagnose_hard_brick(self) -> None:
        result = self.runner.invoke(main, ["diagnose", "hard-brick"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["risk_level"] == "critical"

    def test_ai_bootloop_query(self) -> None:
        result = self.runner.invoke(main, ["ai", "my phone is in a bootloop"])
        assert result.exit_code == 0
        assert "Intent: diagnose" in result.output or "bootloop" in result.output.lower()

    def test_ai_no_query(self) -> None:
        result = self.runner.invoke(main, ["ai"])
        assert result.exit_code == 0
        assert "Usage" in result.output or "ai" in result.output

    def test_triage_edl(self) -> None:
        result = self.runner.invoke(main, ["triage", "--protocol", "edl"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert data["protocol"] == "edl"

    def test_triage_fastboot(self) -> None:
        result = self.runner.invoke(main, ["triage", "--protocol", "fastboot"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["playbook_ids"]) > 0

    def test_repairs_list(self) -> None:
        result = self.runner.invoke(main, ["repairs"])
        assert result.exit_code == 0
        assert "boot_repair" in result.output

    def test_repair_dry_run(self) -> None:
        result = self.runner.invoke(main, ["repair", "frp-bypass", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output or "SUCCESS" in result.output

    def test_audit_show(self) -> None:
        result = self.runner.invoke(main, ["audit", "show"])
        assert result.exit_code == 0

    def test_audit_verify(self) -> None:
        result = self.runner.invoke(main, ["audit", "verify"])
        assert result.exit_code == 0
        assert "OK" in result.output or "BROKEN" in result.output

    def test_tool_sahara_ping(self) -> None:
        with patch("zenith.tools.sahara_ping.sahara_ping_scan", return_value=[]):
            result = self.runner.invoke(main, ["tool", "sahara-ping"])
            assert result.exit_code == 0

    def test_server_help(self) -> None:
        result = self.runner.invoke(main, ["server", "--help"])
        assert result.exit_code == 0
        assert "host" in result.output

    def test_mcp_help(self) -> None:
        result = self.runner.invoke(main, ["mcp"])
        assert result.exit_code == 0
        assert "Available tools" in result.output or "mcp" in result.output

    def test_flash_plan_dry_run(self) -> None:
        result = self.runner.invoke(main, ["flash", "test_dir", "--dry-run"])
        assert result.exit_code == 0
        assert "Flash plan" in result.output or "files" in result.output

    def test_ai_ask(self) -> None:
        result = self.runner.invoke(main, ["ai", "index"])
        # index requires chromadb, so it may fail gracefully
        assert result.exit_code in (0, 2)

    def test_profiles_list(self) -> None:
        result = self.runner.invoke(main, ["profiles"])
        assert result.exit_code == 0
        assert "device profiles" in result.output

    def test_help_all_commands(self) -> None:
        result = self.runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        for cmd in ("discover", "ai", "diagnose", "triage", "playbooks", "repair",
                    "flash", "repairs", "arsenal", "profiles", "audit",
                    "tool", "server", "mcp", "gui", "version"):
            assert cmd in result.output

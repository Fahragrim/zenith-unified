"""Unit tests for zenith/ai/mcp/__init__.py — MCP tool definitions and dispatch."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from zenith.ai.mcp import MCPTool, call_tool, list_tools

MCP_TOOL_NAMES = [
    "discover_devices",
    "diagnose",
    "search_knowledge",
    "list_playbooks",
    "execute_playbook",
    "run_adb",
    "run_fastboot",
    "sahara_ping",
    "fastboot_fuzz",
]


class TestMCPTool:
    """Tests for the MCPTool dataclass."""

    def test_creation(self) -> None:
        tool = MCPTool("test_tool", "Does something", {"type": "object", "properties": {}})
        assert tool.name == "test_tool"
        assert tool.description == "Does something"
        assert tool.schema == {"type": "object", "properties": {}}


class TestMCPTools:
    """Tests for the MCP_TOOLS list."""

    def test_has_nine_tools(self) -> None:
        from zenith.ai.mcp import MCP_TOOLS

        assert len(MCP_TOOLS) == 9

    def test_contains_all_names(self) -> None:
        from zenith.ai.mcp import MCP_TOOLS

        names = {t.name for t in MCP_TOOLS}
        assert names == set(MCP_TOOL_NAMES)

    def test_each_tool_has_required_fields(self) -> None:
        from zenith.ai.mcp import MCP_TOOLS

        for tool in MCP_TOOLS:
            assert isinstance(tool.name, str)
            assert isinstance(tool.description, str)
            assert isinstance(tool.schema, dict)

    def test_discover_devices_schema(self) -> None:
        from zenith.ai.mcp import MCP_TOOLS

        tool = next(t for t in MCP_TOOLS if t.name == "discover_devices")
        assert tool.schema["required"] == []

    def test_diagnose_requires_symptom(self) -> None:
        from zenith.ai.mcp import MCP_TOOLS

        tool = next(t for t in MCP_TOOLS if t.name == "diagnose")
        assert "symptom" in tool.schema["required"]

    def test_execute_playbook_requires_playbook_id(self) -> None:
        from zenith.ai.mcp import MCP_TOOLS

        tool = next(t for t in MCP_TOOLS if t.name == "execute_playbook")
        assert "playbook_id" in tool.schema["required"]

    def test_run_adb_requires_command(self) -> None:
        from zenith.ai.mcp import MCP_TOOLS

        tool = next(t for t in MCP_TOOLS if t.name == "run_adb")
        assert "command" in tool.schema["required"]


class TestListTools:
    """Tests for the list_tools() function."""

    def test_returns_list_of_dicts(self) -> None:
        result = list_tools()
        assert isinstance(result, list)
        assert len(result) == 9

    def test_each_entry_has_expected_keys(self) -> None:
        result = list_tools()
        for entry in result:
            assert "name" in entry
            assert "description" in entry
            assert "inputSchema" in entry

    def test_names_match_mcp_tools(self) -> None:
        result = list_tools()
        names = [e["name"] for e in result]
        assert names == MCP_TOOL_NAMES


class TestCallTool:
    """Tests for the call_tool() dispatch function."""

    def test_unknown_tool_returns_error(self) -> None:
        result = call_tool("nonexistent", {})
        assert result["content"][0]["text"] == "Unknown tool: nonexistent"

    def test_none_arguments_defaults_to_empty(self) -> None:
        result = call_tool("nonexistent", None)
        assert result["content"][0]["text"] == "Unknown tool: nonexistent"

    # ── discover_devices ──────────────────────────────────────────────

    def test_discover_devices(self) -> None:
        mock_result = MagicMock()
        mock_result.to_display_text.return_value = "Device: emulator-5554"

        with patch("zenith.core.discovery.run_discovery", return_value=mock_result):
            result = call_tool("discover_devices", {})

        assert result["content"][0]["text"] == "Device: emulator-5554"

    # ── diagnose ──────────────────────────────────────────────────────

    def test_diagnose(self) -> None:
        mock_diag_result = MagicMock()
        mock_diag_result.to_dict.return_value = {"diagnosis": "bootloop", "confidence": 0.9}

        mock_engine = MagicMock()
        mock_engine.diagnose.return_value = mock_diag_result

        with patch("zenith.engines.diagnostics.DiagnosticsEngine", return_value=mock_engine):
            result = call_tool("diagnose", {"symptom": "bootloop"})

        expected = json.dumps({"diagnosis": "bootloop", "confidence": 0.9}, ensure_ascii=False)
        assert result["content"][0]["text"] == expected
        mock_engine.diagnose.assert_called_once_with(["bootloop"])

    def test_diagnose_default_symptom(self) -> None:
        mock_diag_result = MagicMock()
        mock_diag_result.to_dict.return_value = {"diagnosis": "bootloop"}

        mock_engine = MagicMock()
        mock_engine.diagnose.return_value = mock_diag_result

        with patch("zenith.engines.diagnostics.DiagnosticsEngine", return_value=mock_engine):
            result = call_tool("diagnose", {})

        mock_engine.diagnose.assert_called_once_with(["bootloop"])

    # ── search_knowledge ──────────────────────────────────────────────

    def test_search_knowledge(self) -> None:
        mock_kb = MagicMock()
        mock_kb.search.return_value = [{"title": "FRP Bypass"}]

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            result = call_tool("search_knowledge", {"query": "frp"})

        expected = json.dumps([{"title": "FRP Bypass"}], ensure_ascii=False)
        assert result["content"][0]["text"] == expected
        mock_kb.search.assert_called_once_with("frp")

    def test_search_knowledge_default_query(self) -> None:
        mock_kb = MagicMock()
        mock_kb.search.return_value = []

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            result = call_tool("search_knowledge", {})

        mock_kb.search.assert_called_once_with("")

    # ── list_playbooks ────────────────────────────────────────────────

    def test_list_playbooks(self) -> None:
        mock_pb1 = MagicMock()
        mock_pb1.id = "pb1"
        mock_pb1.title = "FRP Bypass"
        mock_pb1.symptom = "frp-lock"
        mock_pb1.risk_level = "high"

        mock_kb = MagicMock()
        mock_kb.list_playbooks.return_value = [mock_pb1]

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            result = call_tool("list_playbooks", {})

        expected = json.dumps(
            [{"id": "pb1", "title": "FRP Bypass", "symptom": "frp-lock", "risk": "high"}],
            ensure_ascii=False,
        )
        assert result["content"][0]["text"] == expected

    # ── execute_playbook ──────────────────────────────────────────────

    def test_execute_playbook_high_risk_requires_consent(self) -> None:
        """High-risk playbooks must be blocked by ConsentGate (safety-by-design)."""
        mock_pb = MagicMock()
        mock_pb.id = "pb1"
        mock_pb.title = "FRP Bypass"
        mock_pb.symptom = "frp-lock"
        mock_pb.steps = []
        mock_pb.risk_level = "high"

        mock_kb = MagicMock()
        mock_kb.get_playbook.return_value = mock_pb

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            result = call_tool("execute_playbook", {"playbook_id": "pb1", "device_serial": "123"})

        text = result["content"][0]["text"]
        # Must NOT execute — consent is required for high-risk playbooks
        assert "Consent required" in text or "Policy denied" in text

    def test_execute_playbook_not_found(self) -> None:
        mock_kb = MagicMock()
        mock_kb.get_playbook.return_value = None

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            result = call_tool("execute_playbook", {"playbook_id": "missing"})

        assert result["content"][0]["text"] == "Playbook not found: missing"

    # ── run_adb ───────────────────────────────────────────────────────

    def test_run_adb(self) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout = "list of devices"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            result = call_tool("run_adb", {"command": "devices"})

        assert "list of devices" in result["content"][0]["text"]
        mock_run.assert_called_once()
        # Must use an arg list, not a shell string
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "adb"
        assert "devices" in call_args
        # Must NOT use shell=True
        assert mock_run.call_args.kwargs.get("shell", False) is False

    def test_run_adb_with_serial(self) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout = "device info"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            result = call_tool("run_adb", {"command": "getprop", "serial": "123"})

        assert "device info" in result["content"][0]["text"]
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "adb"
        assert "-s" in call_args
        assert "123" in call_args
        assert "getprop" in call_args

    def test_run_adb_no_stdout_falls_back_to_stderr(self) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout = ""
        mock_proc.stderr = "error: no devices"

        with patch("subprocess.run", return_value=mock_proc):
            result = call_tool("run_adb", {"command": "devices"})

        assert result["content"][0]["text"] == "error: no devices"

    def test_run_adb_empty_command_returns_error(self) -> None:
        result = call_tool("run_adb", {"command": ""})
        assert "required" in result["content"][0]["text"]

    def test_run_adb_rejects_shell_injection(self) -> None:
        """Shell metacharacters must be treated as literal args, not executed."""
        mock_proc = MagicMock()
        mock_proc.stdout = ""
        mock_proc.stderr = "error"

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            call_tool("run_adb", {"command": "devices; rm -rf /"})

        call_args = mock_run.call_args[0][0]
        # shlex.split("devices; rm -rf /") → ["devices;", "rm", "-rf", "/"]
        # The malicious commands are split into separate literal args, NOT executed by a shell
        assert "rm" in call_args, "The malicious command parts must appear as literal args"
        assert "-rf" in call_args
        assert "/" in call_args
        assert mock_run.call_args.kwargs.get("shell", False) is False

    # ── run_fastboot ──────────────────────────────────────────────────

    def test_run_fastboot(self) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout = "fastboot devices"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            result = call_tool("run_fastboot", {"command": "devices"})

        assert result["content"][0]["text"] == "fastboot devices"
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "fastboot"
        assert "devices" in call_args
        assert mock_run.call_args.kwargs.get("shell", False) is False

    def test_run_fastboot_empty_command_returns_error(self) -> None:
        result = call_tool("run_fastboot", {"command": ""})
        assert "required" in result["content"][0]["text"]

    # ── sahara_ping ──────────────────────────────────────────────────

    def test_sahara_ping(self) -> None:
        with patch("zenith.tools.sahara_ping.sahara_ping_scan", return_value=[{"port": "COM3", "found": True}]) as mock_fn:
            result = call_tool("sahara_ping", {})

        expected = json.dumps([{"port": "COM3", "found": True}], ensure_ascii=False)
        assert result["content"][0]["text"] == expected
        mock_fn.assert_called_once()

    # ── fastboot_fuzz ────────────────────────────────────────────────

    def test_fastboot_fuzz(self) -> None:
        with patch("zenith.tools.fastboot_fuzz.fuzz_oem_commands", return_value=[{"cmd": "oem unlock", "output": "OK"}]) as mock_fn:
            result = call_tool("fastboot_fuzz", {})

        expected = json.dumps([{"cmd": "oem unlock", "output": "OK"}], ensure_ascii=False)
        assert result["content"][0]["text"] == expected
        mock_fn.assert_called_once()

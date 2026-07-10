"""Unit tests for the CLI dashboard (zenith.cli.dashboard)."""

from __future__ import annotations

import builtins as builtins_module
from io import StringIO
from unittest.mock import MagicMock, patch

from rich.console import Console
from rich.columns import Columns
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from zenith.cli.dashboard import Dashboard


def _render(renderable: object) -> str:
    """Render a rich object to plain text for assertion."""
    console = Console(file=StringIO(), force_terminal=False, width=120, color_system=None)
    console.print(renderable)
    return console.file.getvalue()


class TestDashboardInit:
    def test_init(self) -> None:
        dash = Dashboard()
        assert isinstance(dash.layout, Layout)
        # Verify named sections exist via getitem
        assert isinstance(dash.layout["header"], Layout)
        assert isinstance(dash.layout["body"], Layout)
        assert isinstance(dash.layout["quick_actions"], Layout)
        assert isinstance(dash.layout["audit_log"], Layout)
        assert isinstance(dash.layout["body"]["devices"], Layout)
        assert isinstance(dash.layout["body"]["system"], Layout)


class TestBuildHeaderPanel:
    def test_returns_panel(self) -> None:
        panel = Dashboard()._build_header_panel()
        assert isinstance(panel, Panel)
        title = panel.title
        assert isinstance(title, Text)
        assert "ZENITH" in str(title)


class TestBuildDevicePanel:
    @patch("zenith.core.discovery.run_discovery")
    def test_no_devices(self, mock_discovery: MagicMock) -> None:
        result = MagicMock()
        result.adb_devices = []
        result.fastboot_devices = []
        result.usb_hits = []
        result.serial_ports = []
        result.primary_mode = MagicMock()
        result.primary_mode.value = "unknown"
        result.suggested_playbook = ""
        mock_discovery.return_value = result

        panel = Dashboard()._build_device_panel()
        assert isinstance(panel, Panel)
        text = _render(panel)
        assert "No devices found" in text

    @patch("zenith.core.discovery.run_discovery")
    def test_with_devices(self, mock_discovery: MagicMock) -> None:
        result = MagicMock()
        result.adb_devices = [{"serial": "abc123", "state": "device"}]
        result.fastboot_devices = ["fb_serial"]
        result.usb_hits = [MagicMock()]
        result.serial_ports = []
        result.primary_mode = MagicMock()
        result.primary_mode.value = "adb"
        result.suggested_playbook = "test-pb"
        mock_discovery.return_value = result

        panel = Dashboard()._build_device_panel()
        assert isinstance(panel, Panel)
        assert isinstance(panel.renderable, Table)
        text = _render(panel)
        assert "1" in text
        assert "adb" in text.lower()

    @patch("zenith.core.discovery.run_discovery", side_effect=RuntimeError("fail"))
    def test_discovery_error(self, mock_discovery: MagicMock) -> None:
        panel = Dashboard()._build_device_panel()
        assert isinstance(panel, Panel)
        text = _render(panel)
        assert "Error" in text


class TestBuildSystemPanel:
    @patch("zenith.cli.dashboard.shutil.which")
    def test_all_missing(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None

        original_import = builtins_module.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "usb.core":
                raise ImportError("No module named usb.core")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins_module, "__import__", side_effect=mock_import):
            panel = Dashboard()._build_system_panel()
            assert isinstance(panel, Panel)
            text = _render(panel)
            assert "not found" in text.lower() or "not" in text.lower()

    @patch("zenith.cli.dashboard.shutil.which")
    def test_all_available(self, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda x: f"/usr/bin/{x}"

        original_import = builtins_module.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "usb.core":
                return MagicMock()
            return original_import(name, *args, **kwargs)

        with patch.object(builtins_module, "__import__", side_effect=mock_import):
            panel = Dashboard()._build_system_panel()
            assert isinstance(panel, Panel)
            text = _render(panel)
            assert "available" in text

    def test_pyusb_not_installed(self) -> None:
        original_import = builtins_module.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "usb.core":
                raise ImportError("No module named usb.core")
            return original_import(name, *args, **kwargs)

        with patch("zenith.cli.dashboard.shutil.which", return_value=None):
            with patch.object(builtins_module, "__import__", side_effect=mock_import):
                panel = Dashboard()._build_system_panel()
                text = _render(panel)
                assert "not" in text


class TestBuildActionsPanel:
    def test_returns_columns_panel(self) -> None:
        panel = Dashboard()._build_actions_panel()
        assert isinstance(panel, Panel)
        assert isinstance(panel.renderable, Columns)
        text = _render(panel)
        assert "Discover" in text
        assert "Triage" in text
        assert "Arsenal" in text
        assert "Playbooks" in text
        assert "Server" in text
        assert "Audit" in text


class TestBuildAuditPanel:
    @patch("zenith.core.audit.AuditLog")
    def test_with_entries(self, mock_audit_cls: MagicMock) -> None:
        mock_log = MagicMock()
        entry = MagicMock()
        entry.seq = 42
        entry.timestamp = "2026-07-07T12:00:01"
        entry.action_level = "read"
        entry.summary = "dashboard launched"
        mock_log.tail.return_value = [entry]
        mock_audit_cls.return_value = mock_log

        panel = Dashboard()._build_audit_panel()
        assert isinstance(panel, Panel)
        assert isinstance(panel.renderable, Table)
        text = _render(panel)
        assert "42" in text
        assert "dashboard launched" in text

    @patch("zenith.core.audit.AuditLog")
    def test_no_entries(self, mock_audit_cls: MagicMock) -> None:
        mock_log = MagicMock()
        mock_log.tail.return_value = []
        mock_audit_cls.return_value = mock_log

        panel = Dashboard()._build_audit_panel()
        assert isinstance(panel, Panel)
        text = _render(panel)
        assert "No audit entries" in text

    @patch("zenith.core.audit.AuditLog")
    def test_error(self, mock_audit_cls: MagicMock) -> None:
        mock_audit_cls.side_effect = RuntimeError("fail")

        panel = Dashboard()._build_audit_panel()
        assert isinstance(panel, Panel)
        text = _render(panel)
        assert "unavailable" in text.lower()


class TestRefresh:
    @patch("zenith.cli.dashboard.Dashboard._build_header_panel")
    @patch("zenith.cli.dashboard.Dashboard._build_device_panel")
    @patch("zenith.cli.dashboard.Dashboard._build_system_panel")
    @patch("zenith.cli.dashboard.Dashboard._build_actions_panel")
    @patch("zenith.cli.dashboard.Dashboard._build_audit_panel")
    def test_calls_all_builders(
        self,
        mock_audit: MagicMock,
        mock_actions: MagicMock,
        mock_system: MagicMock,
        mock_device: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        for m in (mock_header, mock_device, mock_system, mock_actions, mock_audit):
            m.return_value = Panel("dummy")

        dash = Dashboard()
        dash._refresh()

        mock_header.assert_called_once()
        mock_device.assert_called_once()
        mock_system.assert_called_once()
        mock_actions.assert_called_once()
        mock_audit.assert_called_once()


class TestRun:
    @patch("zenith.cli.dashboard.Dashboard._refresh")
    @patch("zenith.cli.dashboard.Live")
    @patch("zenith.cli.dashboard.time.sleep", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt(
        self,
        mock_sleep: MagicMock,
        mock_live_cls: MagicMock,
        mock_refresh: MagicMock,
    ) -> None:
        mock_live = MagicMock()
        mock_live.__enter__.return_value = mock_live
        mock_live_cls.return_value = mock_live

        with patch("rich.console.Console") as mock_console_cls:
            dash = Dashboard()
            dash.run()

        mock_live_cls.assert_called_once()
        mock_refresh.assert_called_once()
        mock_console_cls.return_value.print.assert_called_once()

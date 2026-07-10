"""Tests for PySide6 GUI components."""

from __future__ import annotations

import os
from typing import Any

import pytest

# Must be set before any Qt imports
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp() -> Any:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestMainWindow:
    def test_create(self, qapp):
        from zenith import __version__
        from zenith.gui.pyside6.main_window import ZenithMainWindow
        win = ZenithMainWindow()
        assert win.windowTitle() == f"Zenith Unified v{__version__}"
        assert win._tabs is not None
        assert "dashboard" in win._tabs
        assert "diagnostics" in win._tabs
        assert "repair" in win._tabs
        assert "arsenal" in win._tabs

    def test_tabs_are_widgets(self, qapp):
        from zenith.gui.pyside6.main_window import ZenithMainWindow
        win = ZenithMainWindow()
        for name, tab in win._tabs.items():
            assert tab is not None, f"Tab {name} is None"

    def test_statusbar(self, qapp):
        from zenith.gui.pyside6.main_window import ZenithMainWindow
        win = ZenithMainWindow()
        win.log("test message")
        assert win.status_lbl.text() == "test message"


class TestDashboardTab:
    def test_create(self, qapp):
        from zenith.gui.pyside6.tabs.dashboard import DashboardTab
        tab = DashboardTab()
        assert hasattr(tab, "device_list")
        assert hasattr(tab, "profile_tree")
        assert hasattr(tab, "log")
        assert hasattr(tab, "refresh_btn")

    def test_refresh_no_devices(self, qapp, monkeypatch):
        from zenith.gui.pyside6.tabs.dashboard import DashboardTab
        from zenith.core.discovery import DiscoveryResult
        empty = DiscoveryResult(
            adb_devices=[], fastboot_devices=[], usb_hits=[], serial_ports=[],
            primary_mode=None,
        )
        monkeypatch.setattr("zenith.core.discovery.run_discovery", lambda: empty)
        tab = DashboardTab()
        tab._refresh()
        assert tab.device_list.count() > 0

    def test_refresh_with_devices(self, qapp, monkeypatch):
        from zenith.gui.pyside6.tabs.dashboard import DashboardTab
        from zenith.core.discovery import DiscoveryResult, ConnectionMode
        from zenith.knowledge.device_registry import DeviceProfileRegistry
        result = DiscoveryResult(
            adb_devices=[{"serial": "emulator-5554", "model": "Pixel 7", "state": "device"}],
            fastboot_devices=[],
            usb_hits=[],
            serial_ports=[],
            primary_mode=ConnectionMode.ADB,
        )
        monkeypatch.setattr("zenith.core.discovery.run_discovery", lambda: result)
        monkeypatch.setattr(
            "zenith.knowledge.device_registry.get_device_profile_registry",
            lambda: DeviceProfileRegistry(),
        )
        tab = DashboardTab()
        tab._refresh()
        assert tab.device_list.count() > 0
        assert "[ADB]" in tab.device_list.item(0).text()


class TestDiagnosticsTab:
    def test_create(self, qapp):
        from zenith.gui.pyside6.tabs.diagnostics import DiagnosticsTab
        tab = DiagnosticsTab()
        assert hasattr(tab, "symptom_combo")
        assert hasattr(tab, "result_text")
        assert hasattr(tab, "diag_btn")

    def test_symptoms_list(self, qapp):
        from zenith.gui.pyside6.tabs.diagnostics import SYMPTOMS
        assert "bootloop" in SYMPTOMS
        assert "frp-lock" in SYMPTOMS
        assert len(SYMPTOMS) >= 6


class TestRepairTab:
    def test_create(self, qapp):
        from zenith.gui.pyside6.tabs.repair import RepairTab
        tab = RepairTab()
        assert hasattr(tab, "executor")
        assert hasattr(tab, "log")
        assert hasattr(tab, "result_text")


class TestArsenalTab:
    def test_create(self, qapp):
        from zenith.gui.pyside6.tabs.arsenal import ArsenalTab
        tab = ArsenalTab()
        assert hasattr(tab, "tree")
        assert hasattr(tab, "detail")
        assert hasattr(tab, "search_input")


class TestTheme:
    def test_apply_theme(self, qapp):
        from zenith.gui.pyside6.theme import apply_theme
        app = qapp
        apply_theme(app)
        assert app.styleSheet() is not None
        assert len(app.styleSheet()) > 100
        assert "#1e1e2e" in app.styleSheet()


class TestPWA:
    def test_no_shell_true(self):
        from zenith.gui.pwa import launch_pwa
        import inspect
        source = inspect.getsource(launch_pwa)
        assert "shell=True" not in source, "PWA must not use shell=True"

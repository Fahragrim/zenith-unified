"""Live terminal dashboard for Zenith Unified.

Uses the rich library to display a live-updating grid of device, system,
quick-action, and audit-log panels.  Refresh interval: 2.5 seconds.
"""

from __future__ import annotations

import platform
import shutil
import sys
import time
from datetime import datetime

from rich.columns import Columns
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class Dashboard:
    """Live terminal dashboard that monitors devices, system status, and audit log."""

    def __init__(self) -> None:
        self.layout = Layout()
        self._init_layout()

    # ── layout structure ──────────────────────────────────────────────────

    def _init_layout(self) -> None:
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="quick_actions", size=5),
            Layout(name="audit_log", size=7),
        )
        self.layout["body"].split_row(
            Layout(name="devices"),
            Layout(name="system"),
        )

    # ── panel builders ────────────────────────────────────────────────────

    def _build_header_panel(self) -> Panel:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return Panel(
            "",
            title=Text("ZENITH UNIFIED DASHBOARD", style="bold cyan"),
            subtitle=now,
            style="bright_blue",
        )

    def _build_device_panel(self) -> Panel:
        try:
            from zenith.core.discovery import run_discovery

            result = run_discovery()
        except Exception:
            return Panel("Error querying devices", title="DEVICES", border_style="red")

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("key", style="bold")
        table.add_column("value")

        adb_count = len(result.adb_devices)
        fb_count = len(result.fastboot_devices)
        usb_count = len(result.usb_hits)
        serial_count = len([p for p in result.serial_ports if p.get("mode", "") != "unknown"])

        total = adb_count + fb_count + usb_count + serial_count

        if total == 0:
            return Panel("No devices found", title="DEVICES", border_style="dim")

        table.add_row("ADB devices", str(adb_count))
        table.add_row("Fastboot devices", str(fb_count))
        table.add_row("USB modes", str(usb_count))
        table.add_row("Serial ports", str(serial_count))

        if result.primary_mode and result.primary_mode.value != "unknown":
            table.add_row("Primary mode", result.primary_mode.value)
        if result.suggested_playbook:
            table.add_row("Suggested PB", result.suggested_playbook)

        return Panel(table, title="DEVICES", border_style="green")

    def _build_system_panel(self) -> Panel:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("key", style="bold")
        table.add_column("value")

        # ADB
        adb_path = shutil.which("adb")
        table.add_row("ADB", "[\u2713] available" if adb_path else "[\u2717] not found")

        # Fastboot
        fb_path = shutil.which("fastboot")
        table.add_row("Fastboot", "[\u2713] available" if fb_path else "[\u2717] not found")

        # pyusb
        try:
            __import__("usb.core")
            table.add_row("pyusb", "[\u2713] installed")
        except ImportError:
            table.add_row("pyusb", "[\u2717] not installed")

        table.add_row("Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        table.add_row("Platform", platform.system())

        return Panel(table, title="SYSTEM", border_style="blue")

    def _build_actions_panel(self) -> Panel:
        actions = Columns(
            [
                "[bold][1][/] Discover Devices",
                "[bold][2][/] Triage",
                "[bold][3][/] Arsenal",
                "[bold][4][/] List Playbooks",
                "[bold][5][/] Server",
                "[bold][6][/] Audit",
            ],
            equal=True,
            expand=True,
        )
        return Panel(actions, title="QUICK ACTIONS", border_style="yellow")

    def _build_audit_panel(self) -> Panel:
        try:
            from zenith.core.audit import AuditLog

            entries = AuditLog().tail(5)
        except Exception:
            return Panel("Audit log unavailable", title="AUDIT LOG", border_style="red")

        if not entries:
            return Panel("No audit entries", title="AUDIT LOG", border_style="dim")

        table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        table.add_column("seq", style="dim", no_wrap=True)
        table.add_column("time", style="dim", no_wrap=True)
        table.add_column("level", no_wrap=True)
        table.add_column("summary")

        for e in entries:
            level_style = {
                "destructive": "bold red",
                "write": "bold yellow",
                "read": "dim",
            }.get(e.action_level, "")
            table.add_row(
                str(e.seq),
                e.timestamp[:19] if e.timestamp else "",
                Text(e.action_level, style=level_style) if level_style else e.action_level,
                e.summary[:80],
            )

        return Panel(table, title="AUDIT LOG (last 5)", border_style="magenta")

    # ── live refresh ──────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self.layout["header"].update(self._build_header_panel())
        self.layout["devices"].update(self._build_device_panel())
        self.layout["system"].update(self._build_system_panel())
        self.layout["quick_actions"].update(self._build_actions_panel())
        self.layout["audit_log"].update(self._build_audit_panel())

    def run(self) -> None:
        """Start the live dashboard loop.  Press Ctrl+C to exit."""
        try:
            with Live(self.layout, refresh_per_second=0.5, screen=True):
                while True:
                    self._refresh()
                    time.sleep(2.5)
        except KeyboardInterrupt:
            msg = Panel(
                "[yellow]Dashboard closed.  Use the commands above to run actions.[/]",
                border_style="yellow",
                padding=(1, 2),
            )
            from rich.console import Console
            Console().print(msg)

"""Dashboard tab — device discovery, USB monitoring, profile details, quick actions."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from zenith.gui.pyside6.widgets.log_widgets import LogConsole, UsbPortMonitor


class DashboardTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh_devices)
        self._refresh_timer.start(5000)

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("Device Dashboard")
        title.setProperty("class", "title")
        layout.addWidget(title)

        bar = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Devices")
        self.refresh_btn.clicked.connect(self._refresh)
        bar.addWidget(self.refresh_btn)
        bar.addStretch()
        layout.addLayout(bar)

        # Splitter: device info (top) + USB monitor + log (bottom)
        splitter = QSplitter()
        splitter.setOrientation(Qt.Vertical)

        # Top section: device list + profiles
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)

        grp = QGroupBox("Connected Devices")
        gl = QVBoxLayout(grp)
        self.device_list = QListWidget()
        gl.addWidget(self.device_list)
        top_layout.addWidget(grp, 1)

        grp2 = QGroupBox("Matched Device Profiles")
        gl2 = QVBoxLayout(grp2)
        self.profile_tree = QTreeWidget()
        self.profile_tree.setHeaderLabels(["Profile", "SoC", "Modes"])
        self.profile_tree.setColumnCount(3)
        gl2.addWidget(self.profile_tree)
        top_layout.addWidget(grp2, 1)
        splitter.addWidget(top)

        # Bottom section: USB monitor + log console
        bottom = QWidget()
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.usb_monitor = UsbPortMonitor()
        self.usb_monitor.setMinimumWidth(300)
        self.usb_monitor.device_detected.connect(self._on_usb_device)
        bottom_layout.addWidget(self.usb_monitor)

        self.log = LogConsole()
        bottom_layout.addWidget(self.log, 1)
        splitter.addWidget(bottom)

        splitter.setSizes([300, 200])
        layout.addWidget(splitter, 1)

        # Quick actions
        grp3 = QGroupBox("Quick Actions")
        gl3 = QHBoxLayout(grp3)
        self.diag_btn = QPushButton("Run Diagnostics")
        gl3.addWidget(self.diag_btn)
        self.repair_btn = QPushButton("Open Repair Tab")
        gl3.addWidget(self.repair_btn)
        gl3.addStretch()
        layout.addWidget(grp3)

        self._refresh()

    def _auto_refresh_devices(self) -> None:
        """Periodic refresh to catch newly connected devices."""
        prev_count = self.device_list.count()
        self._refresh()
        if self.device_list.count() > prev_count:
            self.log.append(f"New device detected ({self.device_list.count()} total)")

    def _on_usb_device(self, info: dict) -> None:
        self.log.append(f"USB: {info.get('vid', '?')}:{info.get('pid', '?')} bus={info.get('bus', '?')}")

    def _refresh(self) -> None:
        self.device_list.clear()
        self.profile_tree.clear()
        try:
            from zenith.core.discovery import run_discovery
            result = run_discovery()
            count = 0
            for d in result.adb_devices:
                serial = d.get("serial", "?")
                model = d.get("model", d.get("product", ""))
                self.device_list.addItem(f"[ADB]      {serial}  {model}".strip())
                count += 1
            for s in result.fastboot_devices:
                self.device_list.addItem(f"[FASTBOOT] {s}")
                count += 1
            for u in result.usb_hits:
                self.device_list.addItem(f"[{u.mode.value}] VID={u.vid:04X} PID={u.pid:04X} — {u.label}")
                count += 1
            for p in result.serial_ports:
                self.device_list.addItem(f"[SERIAL]   {p.get('device', '?')} — {p.get('description', '')}")
                count += 1
            if count == 0:
                self.device_list.addItem("No devices detected")
            self.log.append(f"Discovery: {count} device(s) found")
        except Exception as e:
            self.device_list.addItem(f"Error: {e}")

        try:
            from zenith.knowledge.device_registry import get_device_profile_registry
            reg = get_device_profile_registry()
            for p in reg.list_all():
                item = QTreeWidgetItem([p.id, p.soc_name, f"{len(p.modes)} modes"])
                self.profile_tree.addTopLevelItem(item)
        except Exception:
            pass

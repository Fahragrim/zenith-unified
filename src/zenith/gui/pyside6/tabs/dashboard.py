"""Dashboard tab — device discovery, USB status, quick actions."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class DashboardTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header
        title = QLabel("Device Dashboard")
        title.setProperty("class", "title")
        layout.addWidget(title)

        # Refresh bar
        bar = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Devices")
        self.refresh_btn.clicked.connect(self._refresh)
        bar.addWidget(self.refresh_btn)
        bar.addStretch()
        layout.addLayout(bar)

        # Device list
        grp = QGroupBox("Connected Devices")
        gl = QVBoxLayout(grp)
        self.device_list = QListWidget()
        gl.addWidget(self.device_list)
        layout.addWidget(grp, 1)

        # Log output
        grp2 = QGroupBox("Discovery Log")
        gl2 = QVBoxLayout(grp2)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(200)
        gl2.addWidget(self.log)
        layout.addWidget(grp2)

        # Auto-refresh
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(5000)
        self._refresh()

    def _refresh(self) -> None:
        try:
            from zenith.core.discovery import run_discovery
            result = run_discovery()
            self.log.setText(result.to_display_text())

            self.device_list.clear()
            for d in result.adb_devices:
                self.device_list.addItem(f"[ADB] {d.get('serial', '?')}  {d.get('model', '')}  ({d.get('state', '?')})")
            for s in result.fastboot_devices:
                self.device_list.addItem(f"[FASTBOOT] {s}")
            for h in result.usb_hits:
                self.device_list.addItem(f"[USB] {h.label} ({h.vid:04X}:{h.pid:04X})")
            if result.matched_profiles:
                for p in result.matched_profiles:
                    self.device_list.addItem(f"[PROFILE] {p}")
            if not result.adb_devices and not result.fastboot_devices and not result.usb_hits:
                self.device_list.addItem("No devices detected. Connect a device and click Refresh.")
        except Exception as e:
            self.log.setText(f"Discovery error: {e}")

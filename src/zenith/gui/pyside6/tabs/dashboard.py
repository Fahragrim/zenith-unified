"""Dashboard tab — device discovery, USB status, profile details, quick actions."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
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

        title = QLabel("Device Dashboard")
        title.setProperty("class", "title")
        layout.addWidget(title)

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

        # Matched profiles
        grp2 = QGroupBox("Matched Device Profiles")
        gl2 = QVBoxLayout(grp2)
        self.profile_tree = QTreeWidget()
        self.profile_tree.setHeaderLabels(["Profile", "SoC", "FRP Methods", "Modes"])
        self.profile_tree.setColumnWidth(0, 200)
        self.profile_tree.setColumnWidth(1, 180)
        self.profile_tree.itemClicked.connect(self._on_profile_clicked)
        gl2.addWidget(self.profile_tree, 2)

        self.profile_detail = QTextEdit()
        self.profile_detail.setReadOnly(True)
        self.profile_detail.setMaximumHeight(150)
        gl2.addWidget(self.profile_detail)
        layout.addWidget(grp2, 1)

        # Log
        grp3 = QGroupBox("Discovery Log")
        gl3 = QVBoxLayout(grp3)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        gl3.addWidget(self.log)
        layout.addWidget(grp3)

        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(5000)
        self._refresh()

    def _refresh(self) -> None:
        try:
            from zenith.core.discovery import run_discovery
            from zenith.knowledge.device_registry import get_device_profile_registry

            result = run_discovery()
            self.log.setText(result.to_display_text())

            self.device_list.clear()
            for d in result.adb_devices:
                self.device_list.addItem(f"[ADB] {d.get('serial', '?')}  {d.get('model', '')}  ({d.get('state', '?')})")
            for s in result.fastboot_devices:
                self.device_list.addItem(f"[FASTBOOT] {s}")
            for h in result.usb_hits:
                self.device_list.addItem(f"[USB] {h.label} ({h.vid:04X}:{h.pid:04X})")

            # Match profiles from registry
            self.profile_tree.clear()
            reg = get_device_profile_registry()
            matched = reg.match_by_discovery(result)
            if not matched:
                QTreeWidgetItem(self.profile_tree, ["No profiles matched — connect a device"])
            for profile in matched:
                frp_count = len(profile.frp_methods)
                mode_count = len(profile.modes)
                item = QTreeWidgetItem(self.profile_tree, [
                    profile.display_name, profile.soc_name,
                    f"{frp_count} FRP methods", f"{mode_count} modes"
                ])
                item.setData(0, 1, profile.id)  # Store profile ID

            if not result.adb_devices and not result.fastboot_devices and not result.usb_hits:
                self.device_list.addItem("No devices detected. Connect a device and click Refresh.")
        except Exception as e:
            self.log.setText(f"Discovery error: {e}")

    def _on_profile_clicked(self, item: QTreeWidgetItem, col: int) -> None:
        profile_id = item.data(0, 1)
        if not profile_id:
            return
        try:
            from zenith.knowledge.device_registry import get_device_profile_registry
            reg = get_device_profile_registry()
            profile = reg.get(profile_id)
            if profile is None:
                return

            lines = [
                f"=== {profile.display_name} ===",
                f"SoC: {profile.soc_name} ({profile.soc_vendor})",
                f"Android: {profile.android_version}",
                f"Storage: {profile.storage_type}",
                f"Bootloader locked: {profile.bootloader_locked}",
                "",
                "MODES:",
            ]
            for m in profile.modes:
                lines.append(f"  {m.name}: {m.display_name} ({len(m.entry_methods)} entry methods)")
                for e in m.entry_methods[:2]:
                    lines.append(f"    → {e}")

            if profile.frp_methods:
                lines.append("\nFRP METHODS:")
                for f in profile.frp_methods:
                    lines.append(f"  {f.id}: {f.name} (success: {f.success_rate:.0%}, risk: {f.risk_level})")

            if profile.unlock_methods:
                lines.append("\nUNLOCK METHODS:")
                for u in profile.unlock_methods:
                    official = " [OFFICIAL]" if u.official else ""
                    lines.append(f"  {u.id}: {u.name}{official} (success: {u.success_rate:.0%})")

            if profile.test_points:
                lines.append("\nTEST POINTS:")
                for tp in profile.test_points:
                    extra = f" ({tp.coordinates})" if tp.coordinates else ""
                    lines.append(f"  {tp.label}: {tp.location}{extra}")

            if profile.at_commands:
                lines.append(f"\nAT COMMANDS ({len(profile.at_commands)}):")
                for a in profile.at_commands[:5]:
                    risk = f" [{a.risk_level}]" if a.modifies_nvram else ""
                    lines.append(f"  {a.command}{risk}: {a.description[:80]}")

            if profile.partitions:
                lines.append(f"\nPARTITIONS ({len(profile.partitions)}):")
                for p in profile.partitions[:10]:
                    frp = " [FRP-RELEVANT]" if p.frp_relevant else ""
                    lines.append(f"  {p.name}{frp}: {p.purpose}")

            self.profile_detail.setText("\n".join(lines))
        except Exception as e:
            self.profile_detail.setText(f"Profile detail error: {e}")

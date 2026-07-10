"""Repair tab — interactive step-by-step playbook execution.

Uses StepByStepExecutor for per-step control with pause/skip/fallback.
AdapterRegistry dispatch for ADB/Fastboot/EDL/BROM commands.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from zenith.gui.pyside6.widgets.log_widgets import LogConsole, StepByStepExecutor


class RepairTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Repair Playbooks", objectName="title"))

        # Top bar: playbook selector + serial
        grp = QGroupBox("Select Playbook")
        gl = QVBoxLayout(grp)
        row = QHBoxLayout()
        row.addWidget(QLabel("Playbook:"))
        self.playbook_combo = QComboBox()
        self.playbook_combo.setMinimumWidth(300)
        self.playbook_combo.currentIndexChanged.connect(self._preview)
        row.addWidget(self.playbook_combo, 1)
        row.addStretch()
        gl.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Device serial:"))
        self.serial_input = QLineEdit()
        self.serial_input.setPlaceholderText("Optional")
        row2.addWidget(self.serial_input)
        self.load_btn = QPushButton("Load Playbook")
        self.load_btn.clicked.connect(self._load_selected)
        row2.addWidget(self.load_btn)
        gl.addLayout(row2)
        layout.addWidget(grp)

        # Splitter: executor (top) + log (bottom)
        splitter = QSplitter()
        splitter.setOrientation(Qt.Vertical)

        # Interactive step-by-step executor
        self.executor = StepByStepExecutor()
        self.executor.playbook_finished.connect(self._on_finished)
        splitter.addWidget(self.executor)

        # Console log
        self.log = LogConsole()
        splitter.addWidget(self.log)
        splitter.setSizes([400, 150])

        layout.addWidget(splitter, 1)

        # Results area
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(120)
        layout.addWidget(self.result_text)

        self._load_playbooks()

    def _load_playbooks(self) -> None:
        self.playbook_combo.clear()
        try:
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            for pb in kb.list_playbooks():
                self.playbook_combo.addItem(f"{pb.title} [{pb.risk_level}]", pb.id)
        except Exception as e:
            self.playbook_combo.addItem(f"Error: {e}")

    def _preview(self) -> None:
        """Show steps preview when playbook is selected."""
        pid = self.playbook_combo.currentData()
        if not pid:
            return
        try:
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            pb = kb.get_playbook(pid)
            if pb:
                self.log.append(f"Playbook loaded: {pb.title} ({len(pb.steps)} steps)")
        except Exception:
            pass

    def _load_selected(self) -> None:
        pid = self.playbook_combo.currentData()
        if not pid:
            self.log.append("No playbook selected", "WARNING")
            return
        serial = self.serial_input.text().strip()
        try:
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            pb = kb.get_playbook(pid)
            if pb is None:
                self.log.append(f"Playbook not found: {pid}", "ERROR")
                return
            steps = pb.steps if hasattr(pb, 'steps') else []
            risk_level = getattr(pb, 'risk_level', '')
            if not steps:
                self.log.append("Playbook has no steps", "WARNING")
                return
            self.executor.load_playbook(pid, steps, serial, risk_level=risk_level)
            self.log.append(f"Loaded: {pb.title} ({len(steps)} steps, risk={risk_level})")
            self.result_text.clear()
        except Exception as e:
            self.log.append(f"Error loading playbook: {e}", "ERROR")

    def _on_finished(self, data: dict) -> None:
        import json
        self.result_text.setText(json.dumps(data, indent=2, ensure_ascii=False))
        status = "PASSED" if data.get("success") else "FAILED"
        self.log.append(f"Playbook {data.get('playbook_id', '?')}: {status} "
                        f"({data.get('steps_completed', 0)}/{data.get('total_steps', 0)})",
                        "INFO" if data.get("success") else "ERROR")

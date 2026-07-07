"""Repair tab — playbook selection and execution."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class _PlaybookWorker(QThread):
    finished = Signal(dict)

    def __init__(self, playbook_id: str, serial: str) -> None:
        super().__init__()
        self._id = playbook_id
        self._serial = serial

    def run(self) -> None:
        try:
            from zenith.engines.playbook_executor import PlaybookExecutor
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            pb = kb.get_playbook(self._id)
            if pb is None:
                self.finished.emit({"error": f"Playbook not found: {self._id}"})
                return
            pbd = {"id": pb.id, "title": pb.title, "symptom": pb.symptom, "steps": pb.steps, "risk_level": pb.risk_level}
            executor = PlaybookExecutor()
            result = executor.execute(pbd, self._serial)
            self.finished.emit(result.to_dict())
        except Exception as e:
            self.finished.emit({"error": str(e)})


class RepairTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup()
        self._worker: _PlaybookWorker | None = None

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Repair Playbooks", objectName="title"))

        # Playbook selector
        grp = QGroupBox("Select Playbook")
        gl = QVBoxLayout(grp)
        row = QHBoxLayout()
        row.addWidget(QLabel("Playbook:"))
        self.playbook_combo = QComboBox()
        self.playbook_combo.setMinimumWidth(300)
        row.addWidget(self.playbook_combo, 1)
        row.addStretch()
        gl.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Device serial:"))
        self.serial_input = QLineEdit()
        self.serial_input.setPlaceholderText("Optional")
        row2.addWidget(self.serial_input)
        gl.addLayout(row2)
        self.exec_btn = QPushButton("Execute Playbook")
        self.exec_btn.clicked.connect(self._execute)
        gl.addWidget(self.exec_btn)
        layout.addWidget(grp)

        # Steps preview
        grp2 = QGroupBox("Playbook Steps")
        gl2 = QVBoxLayout(grp2)
        self.steps_list = QListWidget()
        self.steps_list.setMaximumHeight(150)
        gl2.addWidget(self.steps_list)
        layout.addWidget(grp2)

        # Results
        grp3 = QGroupBox("Execution Results")
        gl3 = QVBoxLayout(grp3)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        gl3.addWidget(self.result_text)
        layout.addWidget(grp3, 1)

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

        self.playbook_combo.currentIndexChanged.connect(self._preview)

    def _preview(self) -> None:
        self.steps_list.clear()
        pid = self.playbook_combo.currentData()
        if not pid:
            return
        try:
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            pb = kb.get_playbook(pid)
            if pb:
                for s in pb.steps:
                    desc = s.get("description", s.get("desc", ""))
                    cmd = s.get("command", "")
                    if cmd:
                        self.steps_list.addItem(f"{desc}  →  {cmd}")
                    else:
                        self.steps_list.addItem(desc)
        except Exception:
            pass

    def _execute(self) -> None:
        pid = self.playbook_combo.currentData()
        if not pid:
            self.result_text.setText("Select a playbook first.")
            return
        serial = self.serial_input.text().strip()
        self.exec_btn.setEnabled(False)
        self.exec_btn.setText("Executing...")
        self.result_text.setText("Running...")
        self._worker = _PlaybookWorker(pid, serial)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, data: dict) -> None:
        self.exec_btn.setEnabled(True)
        self.exec_btn.setText("Execute Playbook")
        if "error" in data:
            self.result_text.setText(f"Error: {data['error']}")
            return
        import json
        self.result_text.setText(json.dumps(data, indent=2, ensure_ascii=False))

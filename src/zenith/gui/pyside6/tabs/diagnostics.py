"""Diagnostics tab — symptom input, Bayesian analysis, triage."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

SYMPTOMS = ["bootloop", "hard-brick", "frp-lock", "bootloader-locked",
            "no-charging", "overheating", "stuck_fastboot", "system_crash"]


class DiagnosticsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        title_lbl = QLabel("Diagnostics Engine")
        title_lbl.setProperty("class", "title")
        layout.addWidget(title_lbl)
        subtitle_lbl = QLabel("Bayesian fault analysis with DEEP_ATLAS knowledge base.")
        subtitle_lbl.setProperty("class", "class")
        layout.addWidget(subtitle_lbl)

        # Symptom input
        grp = QGroupBox("Select Symptom")
        gl = QVBoxLayout(grp)
        input_row = QHBoxLayout()
        self.symptom_combo = QComboBox()
        self.symptom_combo.addItems(SYMPTOMS)
        self.symptom_combo.setEditable(True)
        input_row.addWidget(QLabel("Symptom:"))
        input_row.addWidget(self.symptom_combo, 1)
        gl.addLayout(input_row)
        self.diag_btn = QPushButton("Run Diagnostics")
        self.diag_btn.clicked.connect(self._run_diagnostics)
        gl.addWidget(self.diag_btn)
        layout.addWidget(grp)

        # Triage
        grp2 = QGroupBox("Triage Tree")
        gl2 = QVBoxLayout(grp2)
        triage_row = QHBoxLayout()
        self.triage_combo = QComboBox()
        self.triage_combo.addItems(["edl", "brom", "fastboot", "adb"])
        triage_row.addWidget(QLabel("Protocol:"))
        triage_row.addWidget(self.triage_combo)
        triage_row.addStretch()
        gl2.addLayout(triage_row)
        self.triage_btn = QPushButton("Auto-Detect Path")
        self.triage_btn.clicked.connect(self._run_triage)
        gl2.addWidget(self.triage_btn)
        layout.addWidget(grp2)

        # Results
        grp3 = QGroupBox("Results")
        gl3 = QVBoxLayout(grp3)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(300)
        gl3.addWidget(self.result_text)
        layout.addWidget(grp3, 1)

    def _run_diagnostics(self) -> None:
        symptom = self.symptom_combo.currentText().strip()
        if not symptom:
            return
        try:
            from zenith.engines.diagnostics import DiagnosticsEngine
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            engine = DiagnosticsEngine(kb)
            result = engine.diagnose([symptom])
            lines = [f"Diagnosis: {result.diagnosis}", f"Confidence: {result.confidence:.0%}",
                     f"Risk Level: {result.risk_level}", "",
                     "Possible causes:"]
            for cause, prob in sorted(result.causes.items(), key=lambda x: -x[1]):
                lines.append(f"  {cause}: {prob:.0%}")
            if result.tests:
                lines.extend(["", "Suggested tests:"])
                for t in result.tests:
                    lines.append(f"  • {t}")
            if result.fixes:
                lines.extend(["", "Recommended actions:"])
                for f in result.fixes:
                    lines.append(f"  • {f}")
            if result.suggested_playbooks:
                lines.extend(["", "Matching playbooks:"])
                for pid in result.suggested_playbooks:
                    pb = kb.get_playbook(pid)
                    if pb:
                        lines.append(f"  • {pb.title}")
            self.result_text.setText("\n".join(lines))
        except Exception as e:
            self.result_text.setText(f"Diagnostics error: {e}")

    def _run_triage(self) -> None:
        protocol = self.triage_combo.currentText()
        try:
            from zenith.engines.triage import TriageEngine
            engine = TriageEngine()
            result = engine.auto_detect(protocol)
            import json
            self.result_text.setText(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        except Exception as e:
            self.result_text.setText(f"Triage error: {e}")

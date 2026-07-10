"""GUI widgets: LogConsole, USB Port Monitor, Step-by-Step Executor."""

from __future__ import annotations

import queue

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ─── 2.3 Integrated Log Console ─────────────────────────────────────────────


class LogConsole(QWidget):
    """Color-coded log console that captures Loguru output in real-time."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._sink_id: int | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._flush_queue)
        self._timer.start(200)
        self._setup()
        self._start_loguru_capture()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        title = QLabel("Console Log")
        title.setProperty("class", "subtitle")
        header.addWidget(title)
        header.addStretch()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self.clear)
        self._clear_btn.setFixedWidth(60)
        header.addWidget(self._clear_btn)
        layout.addLayout(header)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setMaximumBlockCount(5000)
        self._output.setMinimumHeight(120)
        layout.addWidget(self._output)

    def _start_loguru_capture(self) -> None:
        try:
            from loguru import logger

            def sink(msg):
                record = msg.record
                level = record["level"].name
                text = record["message"]
                self._queue.put_nowait((text, level))

            self._sink_id = logger.add(
                sink,
                level="DEBUG",
                format="{message}",
                colorize=False,
            )
        except Exception:
            pass

    def _flush_queue(self) -> None:
        while not self._queue.empty():
            try:
                text, level = self._queue.get_nowait()
                self._append_internal(text, level)
            except queue.Empty:
                break

    def _append_internal(self, text: str, level: str = "INFO") -> None:
        colors = {"DEBUG": "#6c7086", "INFO": "#cdd6f4", "WARNING": "#f9e2af",
                  "ERROR": "#f38ba8", "CRITICAL": "#f38ba8"}
        color = colors.get(level.upper(), "#cdd6f4")
        tag = level.upper().ljust(8)
        self._output.appendHtml(f'<span style="color:{color}">[{tag}] {text}</span>')

    def append(self, text: str, level: str = "INFO") -> None:
        self._queue.put_nowait((text, level))

    def stop_capture(self) -> None:
        if self._sink_id is not None:
            try:
                from loguru import logger
                logger.remove(self._sink_id)
            except Exception:
                pass
            self._sink_id = None

    def clear(self) -> None:
        self._output.clear()

    def __del__(self) -> None:
        self.stop_capture()


# ─── 2.2 Live USB Port Monitor ──────────────────────────────────────────────


class UsbPortMonitor(QWidget):
    """Monitors USB bus in background and detects device connection events."""

    device_detected = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._known: set[str] = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scan)
        self._setup()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        title = QLabel("USB Port Monitor")
        title.setProperty("class", "subtitle")
        header.addWidget(title)
        header.addStretch()
        self._start_btn = QPushButton("Start Monitor")
        self._start_btn.clicked.connect(self.toggle)
        self._start_btn.setFixedWidth(110)
        header.addWidget(self._start_btn)
        layout.addLayout(header)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setMaximumHeight(100)
        layout.addWidget(self._output)

    def toggle(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._start_btn.setText("Start Monitor")
            self._append_log("Monitor stopped")
        else:
            self._known.clear()
            self._timer.start(2000)
            self._start_btn.setText("Stop Monitor")
            self._append_log("Monitor started (scanning every 2s)")

    def _scan(self) -> None:
        try:
            import usb.core
            for dev in usb.core.find(find_all=True):
                vid = dev.idVendor
                pid = dev.idProduct
                key = f"{vid:04X}:{pid:04X}"
                if key not in self._known:
                    self._known.add(key)
                    info = {"vid": f"0x{vid:04X}", "pid": f"0x{pid:04X}",
                            "bus": dev.bus, "address": dev.address}
                    self.device_detected.emit(info)
                    self._detect_device_type(info)
        except ImportError:
            pass
        except Exception:
            pass

    def _detect_device_type(self, info: dict) -> None:
        from zenith.core.device import detect_device_type_from_usb
        vid = int(info["vid"], 16) if isinstance(info["vid"], str) else info["vid"]
        pid = int(info["pid"], 16) if isinstance(info["pid"], str) else info["pid"]
        dtype = detect_device_type_from_usb(vid, pid)
        self._append_log(f"Device connected: {info['vid']}:{info['pid']} -> {dtype.value}")

    def _append_log(self, text: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._output.append(f"[{ts}] {text}")

    def stop(self) -> None:
        self._timer.stop()
        self._start_btn.setText("Start Monitor")


# ─── Step Executor Widget ───────────────────────────────────────────────────


class StepItem(QWidget):
    """A single step widget showing description, status icon, and controls."""

    def __init__(self, step_number: int, description: str, command: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.step_number = step_number
        self.description = description
        self.command = command
        self._status: str = "pending"
        self._output_text = ""
        self._setup()

    def _setup(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        self._icon = QLabel("○")
        self._icon.setFixedWidth(20)
        layout.addWidget(self._icon)
        desc = self.description[:60] + ("..." if len(self.description) > 60 else "")
        self._desc_label = QLabel(f"Step {self.step_number}: {desc}")
        layout.addWidget(self._desc_label, 1)
        if self.command:
            cmd = self.command[:40] + ("..." if len(self.command) > 40 else "")
            layout.addWidget(QLabel(f"→ {cmd}"))

    def set_status(self, status: str, output: str = "") -> None:
        self._status = status
        self._output_text = output
        icons = {"pending": "○", "running": "◌", "completed": "✓", "failed": "✗", "skipped": "–"}
        colors = {"pending": "#6c7086", "running": "#f9e2af", "completed": "#a6e3a1",
                  "failed": "#f38ba8", "skipped": "#585b70"}
        self._icon.setText(icons.get(status, "○"))
        self._icon.setStyleSheet(f"color: {colors.get(status, '#6c7086')}; font-size: 16px;")

    @property
    def status(self) -> str:
        return self._status

    @property
    def output_text(self) -> str:
        return self._output_text


class StepByStepExecutor(QWidget):
    """Interactive step-by-step playbook executor with per-step controls."""

    step_completed = Signal(int, bool, str)
    playbook_finished = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._steps: list[StepItem] = []
        self._current_step = 0
        self._results: list[dict] = []
        self._running = False
        self._playbook_id = ""
        self._serial = ""
        self._risk_level = ""
        self._setup()

    def _setup(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Controls
        ctrl = QHBoxLayout()
        self._run_btn = QPushButton("▶ Run All")
        self._run_btn.clicked.connect(self.run_all)
        ctrl.addWidget(self._run_btn)
        self._step_btn = QPushButton("▶ Run Next Step")
        self._step_btn.clicked.connect(self.run_next_step)
        self._step_btn.setEnabled(False)
        ctrl.addWidget(self._step_btn)
        self._skip_btn = QPushButton("Skip Step")
        self._skip_btn.clicked.connect(self.skip_step)
        self._skip_btn.setEnabled(False)
        ctrl.addWidget(self._skip_btn)
        self._pause_btn = QPushButton("⏸ Pause")
        self._pause_btn.clicked.connect(self.pause)
        self._pause_btn.setEnabled(False)
        ctrl.addWidget(self._pause_btn)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Step list
        self._step_container = QVBoxLayout()
        layout.addLayout(self._step_container)
        layout.addStretch()

    def load_playbook(self, playbook_id: str, steps: list[dict], serial: str = "",
                      risk_level: str = "") -> None:
        self._playbook_id = playbook_id
        self._serial = serial
        self._risk_level = risk_level
        self._clear_steps()
        for s in steps:
            desc = s.get("description", s.get("desc", f"Step {s.get('step_number', s.get('step', 0))}"))
            cmd = s.get("command", "")
            step_num = s.get("step_number", s.get("step", 0))
            if isinstance(step_num, dict):
                step_num = step_num.get("number", 0)
            item = StepItem(int(step_num) if step_num else 0, str(desc), str(cmd))
            self._steps.append(item)
            self._step_container.addWidget(item)
        self._current_step = 0
        self._results = []
        self._running = False
        self._update_buttons()

    def _clear_steps(self) -> None:
        for item in self._steps:
            self._step_container.removeWidget(item)
            item.deleteLater()
        self._steps.clear()

    def run_all(self) -> None:
        if not self._steps:
            return
        if self._risk_level == "critical":
            reply = QMessageBox.warning(
                self, "Safety Confirmation",
                "⚠ This action requires safety confirmation.\n\n"
                f"Playbook risk level: {self._risk_level}\n"
                "This may permanently brick the device, wipe all data, or void warranty.\n\n"
                "Proceed?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self._running = True
        self._progress.setVisible(True)
        self._progress.setMaximum(len(self._steps))
        self._progress.setValue(0)
        self._update_buttons()
        self._execute_next()

    def run_next_step(self) -> None:
        if self._current_step >= len(self._steps):
            return
        self._running = True
        self._update_buttons()
        self._execute_current()

    def skip_step(self) -> None:
        if self._current_step >= len(self._steps):
            return
        step = self._steps[self._current_step]
        step.set_status("skipped")
        self._results.append({"step": step.step_number, "description": step.description,
                             "command": step.command, "success": True, "output": "Skipped"})
        self._current_step += 1
        self._progress.setValue(self._current_step)
        self.step_completed.emit(step.step_number, True, "Skipped")
        if self._running and self._current_step < len(self._steps):
            self._execute_next()
        else:
            self._finish()

    def pause(self) -> None:
        self._running = False
        self._update_buttons()

    def _execute_next(self) -> None:
        if self._current_step < len(self._steps) and self._running:
            self._execute_current()

    def _execute_current(self) -> None:
        step = self._steps[self._current_step]
        step.set_status("running")
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        if not step.command:
            step.set_status("completed", "Manual step (no command)")
            self._results.append({"step": step.step_number, "description": step.description,
                                 "command": "", "success": True, "output": "Manual step"})
            self._current_step += 1
            self._progress.setValue(self._current_step)
            self.step_completed.emit(step.step_number, True, "Manual step")
            if self._running and self._current_step < len(self._steps):
                self._execute_next()
            else:
                self._finish()
            return

        try:
            from zenith.adapters.registry import get_adapter_registry
            registry = get_adapter_registry()
            ok, out = registry.dispatch(step.command, self._serial)
            step.set_status("completed" if ok else "failed", out)
            self._results.append({"step": step.step_number, "description": step.description,
                                 "command": step.command, "success": ok, "output": out[:200]})
            self._current_step += 1
            self._progress.setValue(self._current_step)
            self.step_completed.emit(step.step_number, ok, out[:80])
            if ok and self._running and self._current_step < len(self._steps):
                self._execute_next()
            elif not ok:
                self._running = False
                self._update_buttons()
            else:
                self._finish()
        except Exception as e:
            step.set_status("failed", str(e))
            self._results.append({"step": step.step_number, "description": step.description,
                                 "command": step.command, "success": False, "output": str(e)})
            self._current_step += 1
            self._progress.setValue(self._current_step)
            self.step_completed.emit(step.step_number, False, str(e))
            self._running = False
            self._update_buttons()

    def _finish(self) -> None:
        self._running = False
        self._update_buttons()
        total = len(self._results)
        ok = sum(1 for r in self._results if r["success"])
        self.playbook_finished.emit({"playbook_id": self._playbook_id,
                                     "success": ok == total,
                                     "steps_completed": ok,
                                     "total_steps": total,
                                     "results": self._results})

    def _update_buttons(self) -> None:
        has_steps = len(self._steps) > 0
        all_done = self._current_step >= len(self._steps)
        self._run_btn.setEnabled(has_steps and not self._running and not all_done)
        self._step_btn.setEnabled(has_steps and not self._running and not all_done)
        self._skip_btn.setEnabled(has_steps and self._running and self._current_step < len(self._steps))
        self._pause_btn.setEnabled(self._running)

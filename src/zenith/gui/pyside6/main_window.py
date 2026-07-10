"""Zenith Unified — PySide6 Desktop GUI.

Dashboard · Diagnostics · Repair · Arsenal · Settings
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from zenith import __version__
from zenith.gui.pyside6.tabs.arsenal import ArsenalTab
from zenith.gui.pyside6.tabs.dashboard import DashboardTab
from zenith.gui.pyside6.tabs.diagnostics import DiagnosticsTab
from zenith.gui.pyside6.tabs.repair import RepairTab
from zenith.gui.pyside6.theme import apply_theme


class ZenithMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Zenith Unified v{__version__}")
        self.resize(1300, 900)
        self.setMinimumSize(1000, 700)

        self._tabs: dict[str, QWidget] = {}
        self._setup_ui()
        self._setup_statusbar()
        apply_theme(self)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)

        self._tabs["dashboard"] = DashboardTab()
        self._tabs["diagnostics"] = DiagnosticsTab()
        self._tabs["repair"] = RepairTab()
        self._tabs["arsenal"] = ArsenalTab()

        self.tab_widget.addTab(self._tabs["dashboard"], "Dashboard")
        self.tab_widget.addTab(self._tabs["diagnostics"], "Diagnostics")
        self.tab_widget.addTab(self._tabs["repair"], "Repair")
        self.tab_widget.addTab(self._tabs["arsenal"], "Arsenal")

        # Wire dashboard repair button to repair tab
        dash = self._tabs["dashboard"]
        if hasattr(dash, "repair_btn"):
            dash.repair_btn.clicked.connect(lambda: self.tab_widget.setCurrentIndex(2))

        layout.addWidget(self.tab_widget)

    def _setup_statusbar(self) -> None:
        self.status = QStatusBar()
        self.status_lbl = QLabel("Ready")
        self.status.addWidget(self.status_lbl)
        self.setStatusBar(self.status)

    def log(self, msg: str) -> None:
        self.status_lbl.setText(msg)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Zenith Unified")
    window = ZenithMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

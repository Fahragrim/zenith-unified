"""Catppuccin theme for PySide6 — ported from OpencodeDeviceTool theme_manager.py."""

from __future__ import annotations

from typing import Any

CATPPUCCIN_MOCHA = """
QMainWindow { background-color: #1e1e2e; }
QWidget { color: #cdd6f4; font-family: 'Segoe UI'; font-size: 13px; }
QPushButton { background-color: #89b4fa; color: #1e1e2e; border: none; padding: 7px 16px; border-radius: 6px; font-weight: 600; }
QPushButton:hover { background-color: #74c7ec; }
QPushButton:pressed { background-color: #1e66f5; }
QPushButton:disabled { background-color: #585b70; color: #6c7086; }
QPushButton.danger { background-color: #f38ba8; }
QPushButton.success { background-color: #a6e3a1; }
QPushButton.warning { background-color: #f9e2af; color: #1e1e2e; }

QTableWidget { background-color: #313244; gridline-color: #45475a; border: 1px solid #45475a; border-radius: 4px; }
QHeaderView::section { background-color: #45475a; padding: 6px; font-weight: bold; border: none; }
QTableWidget::item:selected { background-color: #89b4fa; color: #1e1e2e; }

QTextEdit, QPlainTextEdit, QLineEdit {
    background-color: #181825; color: #cdd6f4; border: 1px solid #45475a;
    border-radius: 4px; padding: 6px; font-family: 'Consolas', 'Courier New', monospace;
}

QGroupBox { border: 1px solid #45475a; border-radius: 8px; margin-top: 10px; font-weight: bold; padding-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }

QTabWidget::pane { border: 1px solid #45475a; }
QTabBar::tab { background: #313244; color: #cdd6f4; padding: 8px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #1e1e2e; border-bottom: 2px solid #89b4fa; }
QTabBar::tab:hover { background: #45475a; }

QTreeWidget { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; }
QTreeWidget::item:hover { background-color: #45475a; }
QTreeWidget::item:selected { background-color: #89b4fa; color: #1e1e2e; }

QProgressBar { border: 1px solid #45475a; border-radius: 4px; text-align: center; background-color: #313244; color: #cdd6f4; }
QProgressBar::chunk { background-color: #89b4fa; border-radius: 3px; }

QMenuBar { background-color: #181825; color: #cdd6f4; }
QMenuBar::item:selected { background-color: #45475a; }
QMenu { background-color: #313244; border: 1px solid #45475a; color: #cdd6f4; }
QMenu::item:selected { background-color: #89b4fa; color: #1e1e2e; }

QComboBox { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 4px 8px; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background-color: #313244; color: #cdd6f4; selection-background-color: #89b4fa; border: 1px solid #45475a; }

QSpinBox { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 4px; }

QScrollBar:vertical { background-color: #181825; width: 10px; }
QScrollBar::handle:vertical { background-color: #45475a; border-radius: 5px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QListWidget { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; }
QListWidget::item:hover { background-color: #45475a; }
QListWidget::item:selected { background-color: #89b4fa; color: #1e1e2e; }

QSplitter::handle { background-color: #45475a; width: 2px; }

QLabel.title { font-size: 16px; font-weight: bold; color: #89b4fa; }
QLabel.subtitle { font-size: 12px; color: #a6adc8; }
QLabel.success { color: #a6e3a1; }
QLabel.error { color: #f38ba8; }
QLabel.warning { color: #f9e2af; }

QStatusBar { background-color: #181825; color: #6c7086; }
"""


def apply_theme(app: Any) -> None:
    app.setStyleSheet(CATPPUCCIN_MOCHA)

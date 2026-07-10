# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Zenith Unified.

Build commands:
    py -3.12 -m PyInstaller zenith.spec              # CLI .exe
    py -3.12 -m PyInstaller zenith.spec -- --gui      # GUI .exe

Requires Python >= 3.10.
Run in a clean venv with: pip install .[dev,gui,server]
"""
import sys
from pathlib import Path

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

datas = []
binaries = []
excludes = [
    "tkinter", "matplotlib", "scipy", "PIL", "Pillow",
    "notebook", "jupyter", "numpy", "pandas",
    "sentence_transformers", "chromadb", "mistralai",
    "uvicorn", "fastapi", "websockets",
]

# ── Data files ────────────────────────────────────────────────────────────
datas += collect_data_files("zenith")
datas += [
    ("src\\zenith\\data\\playbooks", "zenith\\data\\playbooks"),
    ("src\\zenith\\data\\devices", "zenith\\data\\devices"),
    ("src\\zenith\\data\\DEEP_ATLAS.md", "zenith\\data"),
]

hiddenimports = [
    "click", "loguru", "rich", "yaml", "pydantic", "pydantic_settings",
    "packaging", "psutil", "requests", "httpx", "zeroconf",
    "cryptography", "fpdf2", "adbutils", "serial", "usb",
    "zenith.adapters.adb", "zenith.adapters.fastboot",
    "zenith.adapters.qualcomm_edl", "zenith.adapters.mediatek_brom",
    "zenith.adapters.unisoc_sprd", "zenith.adapters.samsung_odin",
    "zenith.adapters.sony_s1", "zenith.adapters.rockchip",
    "zenith.adapters.allwinner_fel", "zenith.adapters.apple_dfu",
    "zenith.adapters.diag_at", "zenith.adapters.uart",
    "zenith.engines.flash", "zenith.engines.flash_protocols",
    "zenith.engines.repair", "zenith.engines.playbook_executor",
    "zenith.engines.diagnostics", "zenith.engines.triage",
    "zenith.knowledge.knowledge_base", "zenith.knowledge.atlas_parser",
    "zenith.knowledge.device_profile", "zenith.knowledge.device_registry",
    "zenith.core.discovery", "zenith.core.device", "zenith.core.audit",
    "zenith.cli.commands", "zenith.cli.utils",
    "zenith.tools.sahara_ping", "zenith.tools.token_hunter",
    "zenith.tools.vcc_matrix", "zenith.tools.panic_inject",
    "zenith.tools.arsenal_shell",
    "zenith.ai.intent", "zenith.ai.mcp",
]

gui_hiddenimports = hiddenimports + [
    "PySide6", "PySide6.QtCore", "PySide6.QtWidgets",
    "PySide6.QtGui", "PySide6.QtSvg", "PySide6.QtNetwork",
    "qtawesome",
]

def make_analysis(script, extra_hidden=None, extra_excludes=None):
    a = Analysis(
        [script],
        pathex=["src"],
        binaries=binaries,
        datas=datas,
        hiddenimports=extra_hidden or [],
        hookspath=[],
        runtime_hooks=[],
        excludes=excludes + (extra_excludes or []),
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        cipher=block_cipher,
        noarchive=False,
    )
    return a

# ── CLI build (default) ───────────────────────────────────────────────────
a_cli = make_analysis("src\\zenith\\cli\\main.py", hiddenimports)
pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    a_cli.binaries,
    a_cli.zipfiles,
    a_cli.datas,
    [],
    name="zenith",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# ── GUI build (when --gui flag passed) ───────────────────────────────────
if "--gui" in sys.argv:
    a_gui = make_analysis("src\\zenith\\gui\\pyside6\\main_window.py", gui_hiddenimports)
    pyz_gui = PYZ(a_gui.pure, a_gui.zipped_data, cipher=block_cipher)
    exe_gui = EXE(
        pyz_gui,
        a_gui.scripts,
        a_gui.binaries,
        a_gui.zipfiles,
        a_gui.datas,
        [],
        name="zenith-gui",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )

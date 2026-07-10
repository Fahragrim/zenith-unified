# Zenith Unified

**AI-powered USB/ADB tool for Android phone repair, data recovery, diagnostics, and flashing.**

[![CI](https://github.com/lanfear/zenith-unified/actions/workflows/ci.yml/badge.svg)](https://github.com/lanfear/zenith-unified/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/lanfear-zenith)](https://pypi.org/project/lanfear-zenith/)
[![Docker](https://img.shields.io/docker/v/lanfear/zenith-unified?label=docker)](https://hub.docker.com/r/lanfear/zenith-unified)
[![Python](https://img.shields.io/pypi/pyversions/lanfear-zenith)](https://pypi.org/project/lanfear-zenith/)
[![License](https://img.shields.io/pypi/l/lanfear-zenith)](LICENSE)

Requires **Python >= 3.10**.

```bash
# Install from PyPI
pip install lanfear-zenith

# Or from source
pip install -e .

# With extras
pip install lanfear-zenith[gui]     # Desktop GUI
pip install lanfear-zenith[ai]      # AI assistant
pip install lanfear-zenith[server]  # FastAPI server

# Quick start
zenith discover          # Connected devices
zenith diagnose bootloop # Bayesian diagnostics
zenith triage --protocol edl  # Interactive troubleshooting
zenith frp-bypass        # FRP bypass
zenith gui               # Desktop GUI (PySide6)
```

## Arkitektur

```
zenith/
├── core/          Device ABC, event bus, policy engine, audit log, consent gate, backup manager, discovery
├── adapters/      13 adapters + AdapterRegistry (auto-registration, dispatch)
├── knowledge/     DEEP_ATLAS.md parser, SoC-profiler, 14 YAML playbooks, device profiles, secret codes
├── engines/       Bayesian diagnostics, triage tree (17 nodes), repair engine (10 actions), playbook executor (adapter-aware), flash engine (EDL/BROM pipelines)
├── ai/            Provider abstraction (Ollama / LM Studio / Mistral), intent parser, RAG (ChromaDB), MCP server
├── tools/         Sahara ping, fastboot OEM fuzzer, token hunter, panic injector, VCC matrix, arsenal shell
├── cli/           14 Click commands: discover, ai, diagnose, triage, playbooks, repair, flash, arsenal, audit, server, mcp, gui, version, profiles
├── gui/           PySide6 desktop (Dashboard, Diagnostics, Repair, Arsenal) — Catppuccin Mocha dark theme
└── server/        FastAPI, MCP tool-calling protocol
```

## Installation

```bash
git clone https://github.com/Fahragrim/zenith-unified.git
cd zenith-unified
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### Beroenden

- **Core**: `pydantic`, `click`, `loguru`, `rich`, `pyyaml`, `pyusb`, `pyserial`
- **GUI**: `PySide6`, `qtawesome`
- **AI** (valfritt): `chromadb`, `sentence-transformers`, `ollama`
- **Server**: `fastapi`, `uvicorn`, `websockets`

## Kommandon

| Kommando | Funktion |
|---|---|
| `zenith discover` | Upptäck ADB/Fastboot/USB/serial-enheter |
| `zenith ai "bootloop"` | AI-diagnostik (intent → Bayesian → playbook) |
| `zenith diagnose bootloop` | Bayesian felfinnare |
| `zenith triage --protocol edl` | Interaktivt felsökningsträd |
| `zenith playbooks` | Lista tillgängliga spelböcker |
| `zenith repair frp-bypass` | Kör reparationsspelbok |
| `zenith arsenal` | Bläddra DEEP_ATLAS-kunskapsbas |
| `zenith tool sahara-ping` | Sök Qualcomm EDL (COM-port) |
| `zenith tool token-hunt` | Scanna logcat för JWT/tokens |
| `zenith audit show` | Visa hash-kedjad revisionslogg |
| `zenith server` | Starta FastAPI |
| `zenith mcp` | MCP-server för AI-agenter |
| `zenith gui` | Desktop GUI (PySide6) |

## GUI (PySide6)

### Dashboard
Auto-refresh (5s). Visar ADB/Fastboot/USB-enheter med matchade profiler.

### Diagnostics
Välj symptom → Bayesian diagnos med confidens, orsaker, tester, rekommenderade spelböcker. Triage auto-detect från protocol.

### Repair
Spelboks-väljare med steg-preview. Thread-exekvering (GUI fryser inte). Resultat per steg.

### Arsenal
Trädvy: SoCs → Protocols → Playbooks → Tools → Secret Codes. Sök i hela DEEP_ATLAS. Klicka för detaljer.

## Adapter-översikt

| Adapter | DeviceType | Protokoll |
|---|---|---|
| `ADBAdapter` | ADB, ANDROID | adbutils + subprocess fallback, wireless |
| `FastbootAdapter` | FASTBOOT | OEM fuzzer (15 kommandon), getvar, flash |
| `QualcommEDLAdapter` | QUALCOMM_EDL | Sahara+Firehose (bkerler/edl), safe_firehose_flash |
| `MediaTekBROMAdapter` | MTK_BROM | Payload bypass (mtkclient), dump/flash, multi-erase |
| `UnisocSPRDAdapter` | UNISOC_SPD | Native Python HDLC + Socrates via pyusb, .pac flashing |
| `SamsungOdinAdapter` | SAMSUNG_ODIN | Heimdall wrapper |
| `SonyS1Adapter` | QUALCOMM_EDL | Newflasher wrapper |
| `DiagATAdapter` | DIAG | AT-commands, panic inject, COM port scan |
| `UARTAdapter` | UART | Serial port scanner |
| `AppleDFUAdapter` | APPLE_DFU | libimobiledevice wrapper |
| `RockchipAdapter` | ROCKCHIP_MASKROM | rkdeveloptool wrapper |
| `AllwinnerFELAdapter` | ALLWINNER_FEL | sunxi-fel wrapper |

## Spelböcker (13 st)

Filnamn | Symptom | SoC | Risk
---|---|---|---
`hard-brick---qualcomm.yaml` | hard-brick | qualcomm | high
`hard-brick---mediatek.yaml` | hard-brick | mediatek | high
`soft-brick---bootloop.yaml` | bootloop | any | medium
`frp-bypass.yaml` | frp-lock | any | high
`bootloader-unlock.yaml` | bootloader-locked | any | medium
`apple-dfu-triage.yaml` | dfu-mode | apple | high
`samsung-odin-firmware-rescue.yaml` | firmware-corruption | exynos | high
`mtk-brom-bypass.yaml` | brom-access | mediatek | high
`sony-xz2-frp-adb.yaml` | frp-lock | sony | medium
`sony-xz2-frp-edl.yaml` | frp-lock | sony | high
`sony-xz2-frp-fastboot.yaml` | frp-lock | sony | medium
`sony-xz2-frp-newflasher.yaml` | frp-lock | sony | medium
`nokia-c32-frp-bypass.yaml` | frp-lock | unisoc | high

## PyInstaller (Windows .exe)

Requires Python >= 3.10.

```bash
# Using Python 3.12 (recommended):
py -3.12 -m pip install .[dev,gui]
py -3.12 scripts/build_exe.py          # CLI .exe (dist/zenith.exe)
py -3.12 scripts/build_exe.py --gui    # GUI .exe (dist/zenith-gui.exe)

# Or if python3 points to 3.10+:
python3 scripts/build_exe.py
```

## Docker

```bash
docker compose -f docker/docker-compose.yml run --rm zenith --help
docker compose -f docker/docker-compose.yml run --rm zenith discover
docker compose -f docker/docker-compose.yml --profile gui up zenith-gui
```

Or build & publish to GHCR:
```bash
docker build -f docker/Dockerfile -t ghcr.io/lanfear/zenith-unified:latest .
docker run --rm -it --device /dev/bus/usb ghcr.io/lanfear/zenith-unified discover
```

## Test

```bash
pytest tests/unit/       # 476 unit tests
ruff check src/          # Linting
mypy src/                # Type check
```

## Licens

MIT

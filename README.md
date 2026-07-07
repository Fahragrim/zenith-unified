# Zenith Unified

**AI-powered USB/ADB tool for Android phone repair, data recovery, diagnostics, and flashing.**

```bash
pip install -e .
zenith discover          # Alla anslutna enheter
zenith diagnose bootloop # Bayesian diagnostik
zenith triage --protocol edl  # Interaktivt felsökningsträd
zenith frp-bypass        # FRP-bypass (EDL/BROM)
zenith gui               # Desktop GUI (PySide6)
```

## Arkitektur

```
zenith/
├── core/          Device ABC, event bus, policy engine, audit log, consent gate, backup manager, discovery
├── adapters/      13 transportadaptrar: ADB, Fastboot, Qualcomm EDL, MTK BROM, Unisoc SPRD (native HDLC), Samsung Odin, Sony S1, Diag/AT, UART, Apple DFU, Rockchip, Allwinner FEL
├── knowledge/     DEEP_ATLAS.md parser, SoC-profiler, 13 YAML-reparationsspelböcker, secret codes, tool matrix
├── engines/       Bayesian diagnostics, interaktivt triage-träd (17 noder), repair engine (10 actions), playbook executor (7 kommandoprefix)
├── ai/            Provider abstraction (Ollama / LM Studio / Mistral), intent parser, RAG (ChromaDB), MCP server (9 tools)
├── tools/         Sahara ping, fastboot OEM fuzzer, token hunter (logcat)
├── cli/           12 Click-kommandon: discover, ai, diagnose, triage, playbooks, repair, arsenal, audit, server, mcp, gui, version
├── gui/           PySide6 desktop (Dashboard, Diagnostics, Repair, Arsenal) — Catppuccin Mocha dark theme
└── server/        FastAPI (6 endpoints), MCP tool-calling protokoll
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

## Test

```bash
pytest tests/           # 136 tester
ruff check src/         # Linting (0 errors)
mypy src/               # Type check
```

## Licens

MIT

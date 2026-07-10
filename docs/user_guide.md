# User Guide — Zenith Unified v0.4.0

## Installation

Requires **Python >= 3.10**.

```bash
# Core (CLI only, ~30 MB)
pip install lanfear-zenith

# With GUI (PySide6, ~200 MB)
pip install lanfear-zenith[gui]

# With AI assistant (ChromaDB + embeddings, ~500 MB)
pip install lanfear-zenith[ai]

# With server (FastAPI + WebSocket)
pip install lanfear-zenith[server]

# Everything
pip install lanfear-zenith[gui,ai,server]

# Or from source
pip install -e .[dev]
```

## Quick Start

```bash
# List connected devices
zenith discover

# Interactive diagnostic triage
zenith triage --protocol edl

# List repair playbooks
zenith playbooks

# Execute a repair playbook
zenith repair --dry-run soft-brick---bootloop
zenith repair sony-xz2-frp-edl --serial R5CT1234ABCD

# FRP bypass (lists methods, then runs one)
zenith frp-bypass --list
zenith frp-bypass --profile sony_xz2_h8266 --method edl_youkiloon

# Run diagnostics
zenith diagnose bootloop

# Flash firmware
zenith flash ./firmware/ --dry-run --partition boot

# Launch GUI
zenith gui

# Start API server
zenith server --port 8089
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `zenith discover` | Detect all connected devices (ADB, Fastboot, USB, serial) |
| `zenith diagnose <symptom>` | Bayesian diagnostics for a symptom |
| `zenith triage --protocol <p>` | Interactive troubleshooting tree |
| `zenith playbooks` | List available repair playbooks |
| `zenith repair <id>` | Execute a repair playbook |
| `zenith frp-bypass` | FRP bypass using device profiles |
| `zenith flash <dir>` | Flash firmware via EDL/BROM |
| `zenith profiles` | List device profiles |
| `zenith repairs` | List repair actions |
| `zenith arsenal` | Browse DEEP_ATLAS knowledge base |
| `zenith ai <query>` | AI diagnostic assistant |
| `zenith ai index` | Index knowledge into ChromaDB |
| `zenith ai ask <query>` | Semantic knowledge search |
| `zenith tool sahara-ping` | Scan for Qualcomm EDL devices |
| `zenith tool token-hunt` | Scan logcat for leaked credentials |
| `zenith tool panic-inject` | Baseband panic injection |
| `zenith tool vcc-matrix` | VCC fault injection calculator |
| `zenith tool arsenal` | Diagnostic arsenal shell |
| `zenith audit show` | Show audit log |
| `zenith audit verify` | Verify audit log integrity |
| `zenith server` | Start FastAPI server |
| `zenith mcp` | Start MCP server |
| `zenith gui` | Launch desktop GUI |
| `zenith version` | Show version |

## FRP Bypass

```bash
# List all available FRP methods
zenith frp-bypass --list

# Execute a specific method
zenith frp-bypass --profile sony_xz2_h8266 --method edl_youkiloon

# Dry run (preview commands without executing)
zenith frp-bypass --profile samsung_a52_sm-a525f --method odin_combination --dry-run
```

## Docker

```bash
# CLI
docker compose -f docker/docker-compose.yml run --rm zenith discover

# Server
docker compose -f docker/docker-compose.yml up zenith-server

# GUI (requires X11)
docker compose -f docker/docker-compose.yml --profile gui up zenith-gui

# Build manually
docker build -f docker/Dockerfile -t zenith .
docker run --rm -it --device /dev/bus/usb zenith discover
```

## Windows .exe

```bash
pip install .[dev,gui]
python scripts/build_exe.py           # zenith.exe (CLI)
python scripts/build_exe.py --gui     # zenith-gui.exe (GUI)

# Or download from GitHub Releases
```

## GUI Usage

1. **Dashboard** — USB Port Monitor (auto-detect devices, 2s polling), device list, profile browser
2. **Diagnostics** — Symptom-based troubleshooting with Bayesian inference
3. **Repair** — Interactive step-by-step playbook execution (Run All / Run Next / Skip / Pause)
4. **Arsenal** — Diagnostic shell with 10+ hardware actions

### Step-by-Step Repair

1. Select a playbook from the dropdown
2. Enter device serial (optional, for ADB/Fastboot targeting)
3. Click "Load Playbook" to preview steps
4. Use **Run All** to execute all steps automatically
5. Use **Run Next Step** to control execution manually
6. Use **Skip Step** to bypass non-critical steps
7. Use **Pause** to stop after current step
8. The log console shows real-time adapter dispatch output

## Device Profiles

10 built-in profiles spanning 7 SoC vendors:

| Profile | SoC | Modes |
|---------|-----|-------|
| Sony Xperia XZ2 | Snapdragon 845 | EDL, Flashmode, Fastboot, ADB, Diag, Recovery |
| Nokia C32 | Unisoc SC9863A | SPRD BootROM, Diag, Fastboot, ADB, UART |
| Samsung Galaxy A52 | Snapdragon 720G | EDL, Download, Fastboot, ADB, Recovery, Diag |
| Google Pixel 7 | Tensor G2 | Fastboot, EDL, ADB, Recovery, Sideload |
| Xiaomi Redmi Note 12 | Helio G85 | BROM, Fastboot, ADB, Recovery |
| Samsung Galaxy S20 | Exynos 990 | Download, Fastboot, ADB, Recovery, Diag |
| Motorola Moto G51 | Snapdragon 480+ | EDL, Fastboot, ADB, Recovery |
| Huawei P30 | Kirin 980 | Fastboot, ADB, Recovery, BootROM |
| OnePlus 9 Pro | Snapdragon 888 | EDL, Fastboot, ADB, Recovery, Diag |
| LG G8 ThinQ | Snapdragon 855 | EDL, Download, Fastboot, ADB, Recovery |

## Troubleshooting

**"No module named 'usb'"** — Install pyusb: `pip install pyusb`

**"pyserial not installed"** — `pip install pyserial`

**EDL device not detected** — Install libusb driver via Zadig (Windows) or `apt install libusb-1.0-0` (Linux)

**GUI won't start** — `export QT_QPA_PLATFORM=offscreen` for headless, or install PySide6: `pip install PySide6`

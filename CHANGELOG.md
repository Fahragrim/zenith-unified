# Changelog

## v0.5.0.dev0 (2026-07-08)

### Added
- **`python -m zenith` support** — new `src/zenith/__main__.py` entry point
- **Device profiles** — 13 total: added Google Pixel 6a, Xiaomi Mi 11, Sony Xperia 1 III, Samsung Galaxy S23
- **Sony Xperia Toolkit** — enhanced `SonyS1Adapter` with `detect()`, `list_firmware()`, `backup_ta()`, S1 USB detection via pyusb
- **`scripts/sony_flash.py`** — CLI helper for Sony Flashmode operations (detect, list, flash, backup-ta)

### Fixed
- **`zenith.spec`** — replaced `PyAnalysis` (undefined) with standard `Analysis` + `PYZ` + `EXE` API
- **`scripts/build_exe.py`** — auto-detects Python >= 3.10, uses `py -m PyInstaller` instead of bare `pyinstaller`
- **`scripts/hardware_test.py`** — suppresses loguru output, ASCII-safe PASS/FAIL, no Unicode encoding errors
- **README** — clarified Python >= 3.10 requirement, updated install/build instructions

## v0.4.0 (2026-07-08)

### Added
- **Physical adapter transports** — Qualcomm EDL (`EdlUsbTransport`), MediaTek BROM (`BromUsbTransport`), Unisoc SPRD (`HDLCBootROM`/`Socrates`) integrated directly via pyusb
- **Native FDL1/FDL2 loading** — SPRD adapter loads FDL binaries from disk or extracts from .pac firmware files
- **`frp-bypass` CLI command** — lists and executes FRP bypass methods from device profiles via adapter dispatch
- **Interactive Step-by-Step Executor** — `StepByStepExecutor` widget with Run All / Run Next / Skip / Pause controls
- **Live USB Port Monitor** — `UsbPortMonitor` with 2s polling, auto-detects device type on connection
- **Integrated LogConsole** — color-coded Loguru stream in Dashboard and Repair tabs
- **Device profiles** — 10 total: Huawei P30 (Kirin 980), OnePlus 9 Pro (Snapdragon 888), LG G8 ThinQ (Snapdragon 855)
- **Hardware-mocked tests** — 11 integration tests mocking EDL/BROM USB packet-level transport

### Changed
- Version bumped to `0.4.0.dev0`
- `QualcommEDLAdapter` — added `connect()` via pyusb, `_run_transport()` for direct Sahara/Firehose operations
- `MediaTekBROMAdapter` — added `connect()` via pyusb, transport priority over mtkclient subprocess
- `UnisocSPRDAdapter` — synchronous wrappers for all async HDLC/Socrates methods
- RepairTab — complete rewrite with StepByStepExecutor + LogConsole
- Dashboard — integrated USB Port Monitor + auto-refresh (5s timer)
- MainWindow — enlarged to 1300x900, wired dashboard repair button to RepairTab

## v0.2.0.dev0 (2026-07-07)

### Added
- **PyInstaller .exe packaging** — `zenith.spec` + `scripts/build_exe.py` for Windows CLI and GUI executables
- **Docker support** — Multi-stage Dockerfile, docker-compose.yml (CLI + Server + GUI profiles), .dockerignore
- **CI/CD pipeline** — GitHub Actions: PyInstaller build (Windows), Docker build & push to GHCR, PyPI release
- **Device profiles** — `samsung_a52_sm-a525f.json` (Snapdragon 720G), `google_pixel_7.json` (Tensor G2) with full mode/FRP/unlock documentation
- **Adapter auto-registration** — `AdapterRegistry` now auto-discovers and registers all adapters via `supported_types`
- **Adapter dispatch** — `registry.dispatch()` routes commands (adb:, fastboot:, edl:, brom:) to the correct adapter
- **PlaybookExecutor adapter integration** — Uses `AdapterRegistry.dispatch` with subprocess fallback
- **RepairEngine adapter-aware** — Uses registry dispatch for protocol commands

### Changed
- Version bumped from `0.1.0` to `0.2.0.dev0`
- `AdapterRegistry` singleton (`get_adapter_registry()`) auto-registers all adapters
- `FlashEngine._executor` falls back to `registry.dispatch` when no executor is set
- `PlaybookExecutor` accepts optional `registry` parameter for adapter dispatch

### Fixed
- Version format to PEP 440 (`0.2.0.dev0`)
- Engine tests updated for new adapter dispatch behavior
- All 476 unit tests passing

## v0.1.1 (2026-07-06)

### Added
- Device profiles: Sony Xperia XZ2 H8266, Nokia C32 TA-1534
- Panic Injector tool (baseband crash via AT commands)
- VCC Fault Injection Matrix calculator
- Arsenal Shell (10 diagnostic actions)
- GUI Dashboard profiles display

## v0.1.0 (2026-07-05)

Initial release:
- 13 adapters (2 full, 11 stubs)
- CLI with 12 commands
- PySide6 GUI (Dashboard, Diagnostics, Repair, Arsenal)
- FastAPI server
- AI diagnostics + RAG
- 14 YAML repair playbooks
- 216 unit tests

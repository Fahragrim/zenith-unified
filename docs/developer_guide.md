# Developer Guide — Zenith Unified v0.4.0

## Architecture

```
zenith/                        Source (src/zenith/)
├── __init__.py                Package metadata, version
├── config.py                  Settings (pydantic-settings)
├── cli/                       Click CLI (14 commands)
│   ├── main.py                 Entry point, command groups
│   ├── commands/               Command modules
│   └── utils/                  CLI utilities
├── core/                       Core abstractions
│   ├── device.py               DeviceType enum, Device ABC, USB map
│   ├── discovery.py            USB + ADB + Fastboot device discovery
│   ├── policy.py               Safety policy engine
│   ├── consent.py              User consent gate
│   ├── audit.py                Tamper-proof audit log
│   └── backup.py               Backup manager
├── adapters/                   13 transport adapters
│   ├── protocol.py             AdapterProtocol ABC, AdapterResult
│   ├── registry.py             AdapterRegistry (auto-register + dispatch)
│   ├── adb.py                  ADB (adbutils + subprocess fallback)
│   ├── fastboot.py             Fastboot (subprocess)
│   ├── qualcomm_edl.py         Qualcomm EDL (EdlUsbTransport + edl tool)
│   ├── mediatek_brom.py        MediaTek BROM (BromUsbTransport + mtkclient)
│   ├── unisoc_sprd.py          Unisoc SPRD (HDLC + Socrates native)
│   ├── usb_transport.py        PyUSB EdlUsbTransport + BromUsbTransport
│   ├── _sprd_protocol.py       SPRD HDLC BootROM + Socrates protocol
│   └── ...                     samsung_odin, sony_s1, rockchip, etc.
├── engines/                    Business logic
│   ├── diagnostics.py          Bayesian diagnostic engine
│   ├── triage.py               Interactive triage tree
│   ├── repair.py               Repair action registry (10 actions)
│   ├── playbook_executor.py    Playbook executor (adapter-aware)
│   ├── flash.py                Flash engine (EDL/BROM pipelines)
│   └── flash_protocols.py      Sahara, Firehose, BROM protocol builders
├── knowledge/                  DEEP_ATLAS knowledge base
│   ├── atlas_parser.py         .md parser -> structured data
│   ├── knowledge_base.py       Knowledge access layer
│   ├── device_profile.py       Device profile data model
│   └── device_registry.py      Profile registry (JSON loader)
├── ai/                         AI / ML
│   ├── intent.py               Natural language intent parser
│   ├── provider.py             LLM provider abstraction
│   ├── rag.py                  ChromaDB RAG engine
│   └── mcp/                    MCP server for Claude Desktop
├── gui/                        Desktop GUI
│   ├── pyside6/main_window.py  Main window (4 tabs)
│   ├── pyside6/tabs/           Dashboard, Diagnostics, Repair, Arsenal
│   └── pyside6/widgets/        LogConsole, USB Monitor, StepExecutor
├── tools/                      Standalone hardware tools
│   ├── sahara_ping.py          COM port EDL scanner
│   ├── token_hunter.py         Logcat credential scanner
│   ├── vcc_matrix.py           Glitch width calculator
│   ├── panic_inject.py         AT command modem crasher
│   └── arsenal_shell.py        10 diagnostic actions
└── server/                     FastAPI server
    └── app.py                  REST API (6 endpoints)
```

## Key Design Decisions

### Adapter Pattern

Every transport (ADB, Fastboot, EDL, BROM, etc.) implements `AdapterProtocol`:

```python
class AdapterProtocol(ABC):
    name: ClassVar[str]
    binary: ClassVar[str]
    supported_types: ClassVar[tuple[DeviceType, ...]]

    def is_available(self) -> bool: ...
    def list_devices(self) -> list[dict]: ...
    def run(self, *args, timeout) -> AdapterResult: ...
    def connect(self, device_id: str) -> AdapterResult: ...
    def disconnect(self) -> None: ...
```

The `AdapterRegistry` singleton auto-registers all adapters and provides
`dispatch(command: str, serial: str) -> tuple[bool, str]` which routes
commands by prefix (`adb:`, `fastboot:`, `edl:`, `brom:`) to the correct
adapter.

### USB Transport Layer

For EDL and BROM, a native pyusb transport layer exists:

- **`EdlUsbTransport`** — Sahara hello → loader upload → Firehose XML commands
- **`BromUsbTransport`** — Handshake → Download Agent (DA) send → jump → flash

These are mockable in tests via `unittest.mock.patch("usb.core.find")`.

### Dispatch Flow

```
zenith repair sony-xz2-frp-edl
  → CLI calls PlaybookExecutor.execute()
    → _exec("adb:reboot recovery")
      → registry.dispatch("adb:reboot recovery")
        → ADBAdapter.run("reboot", "recovery")  # pyusb or subprocess
        → AdapterResult(success=True, stdout="...")
    → _exec("fastboot:flash frp frp_blank.img")
      → registry.dispatch("fastboot:flash frp ...")
        → FastbootAdapter.run("flash", "frp", "frp_blank.img")
```

## Adding a Device Profile

1. Create `data/devices/<id>.json` following `_schema.json`
2. Include at minimum: id, manufacturer, model, soc_vendor, soc_name, modes, frp_methods, unlock_methods
3. Register FRP bypass commands with the correct prefix (`adb:`, `fastboot:`, `edl:`, `shell:`)
4. Run `zenith profiles --json` to verify it loads

Example minimal profile:
```json
{
  "id": "my_device",
  "manufacturer": "Example",
  "model": "X200",
  "soc_vendor": "Qualcomm",
  "soc_name": "Snapdragon 8 Gen 2",
  "modes": [{"name": "edl", "display_name": "EDL 9008", ...}],
  "frp_methods": [{"id": "my_frp", "name": "My FRP Method", ...}],
  "unlock_methods": []
}
```

## Adding an Adapter

1. Create `src/zenith/adapters/<name>.py` implementing `AdapterProtocol`
2. Set `supported_types` to the DeviceType(s) this adapter handles
3. Export in `src/zenith/adapters/__init__.py`
4. The `AdapterRegistry` auto-registers it via `supported_types`
5. Add a prefix mapping in `registry.dispatch()` if needed
6. Write tests in `tests/unit/` and `tests/integration/`

## Adding a CLI Command

```python
# src/zenith/cli/main.py

@main.command()
@click.argument("device_id")
def my_command(device_id: str) -> None:
    """Description shown in --help."""
    from zenith.adapters.registry import get_adapter_registry
    reg = get_adapter_registry()
    ok, out = reg.dispatch(device_id)
    click.echo(out)
```

Then add to `user_guide.md` command table.

## Testing

```bash
# Unit tests (476+)
pytest tests/unit/

# Integration tests (30+)
pytest tests/integration/

# Hardware-mocked transport tests
pytest tests/integration/test_hardware_mocks.py

# With coverage
pytest --cov=src/zenith --cov-report=html

# Linting
ruff check src/

# Type checking
mypy src/zenith/
```

## Building

```bash
# Python wheel
python -m build

# Windows .exe
pip install .[dev,gui]
python scripts/build_exe.py
python scripts/build_exe.py --gui

# Docker
docker build -f docker/Dockerfile -t zenith .
```

## Versioning

- Source of truth: `src/zenith/__init__.py` (`__version__`)
- Also update: `pyproject.toml`, `docker/Dockerfile` labels
- Format: PEP 440 (`0.4.0.dev0`, `0.4.0`, `0.4.1`)

## Releasing

1. Update CHANGELOG.md
2. Set version in `__init__.py` and `pyproject.toml`
3. `git tag v0.4.0 && git push --tags`
4. GitHub Actions builds: PyPI, Docker, Windows .exe

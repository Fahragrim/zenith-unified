"""Adapter Registry — maps DeviceType to AdapterProtocol implementations.

Auto-registers all known adapters on first access.
"""

from __future__ import annotations

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol
from zenith.core.device import DeviceType


class AdapterRegistry:
    """Central registry: DeviceType → Adapter class."""

    def __init__(self, auto_register: bool = False) -> None:
        self._by_type: dict[DeviceType, type[AdapterProtocol]] = {}
        self._instances: dict[DeviceType, AdapterProtocol] = {}
        self._initialized = False
        self._auto_register_enabled = auto_register

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        if self._auto_register_enabled:
            self._auto_register()

    def _auto_register(self) -> None:
        """Discover and register all adapters with supported_types from zenith.adapters."""
        try:
            import importlib

            from zenith.adapters import __all__ as adapter_names

            for name in adapter_names:
                if name.endswith("Adapter"):
                    try:
                        mod = importlib.import_module(f"zenith.adapters.{name.lower().replace('adapter', '')}")
                        cls = getattr(mod, name, None)
                        if cls is None:
                            # Try direct import
                            cls = getattr(
                                importlib.import_module(f"zenith.adapters.{name.lower()}"),
                                name,
                                None,
                            )
                        if cls and hasattr(cls, "supported_types"):
                            for dt in cls.supported_types:
                                if isinstance(dt, DeviceType):
                                    self.register(dt, cls)
                    except Exception:
                        pass
        except Exception:
            logger.warning("Adapter auto-registration failed — using fallback")

        # Fallback: register known adapters manually (always run)
        self._register_known()

    def _register_known(self) -> None:
        """Fallback manual registration of all known adapters."""
        known = [
            ("zenith.adapters.adb", "ADBAdapter"),
            ("zenith.adapters.fastboot", "FastbootAdapter"),
            ("zenith.adapters.qualcomm_edl", "QualcommEDLAdapter"),
            ("zenith.adapters.mediatek_brom", "MediaTekBROMAdapter"),
            ("zenith.adapters.unisoc_sprd", "UnisocSPRDAdapter"),
            ("zenith.adapters.samsung_odin", "SamsungOdinAdapter"),
            ("zenith.adapters.sony_s1", "SonyS1Adapter"),
            ("zenith.adapters.rockchip", "RockchipAdapter"),
            ("zenith.adapters.allwinner_fel", "AllwinnerFELAdapter"),
            ("zenith.adapters.apple_dfu", "AppleDFUAdapter"),
            ("zenith.adapters.diag_at", "DiagATAdapter"),
            ("zenith.adapters.uart", "UARTAdapter"),
        ]
        for mod_path, cls_name in known:
            try:
                import importlib
                mod = importlib.import_module(mod_path)
                cls = getattr(mod, cls_name)
                if hasattr(cls, "supported_types"):
                    for dt in cls.supported_types:
                        if isinstance(dt, DeviceType):
                            self.register(dt, cls)
            except Exception as e:
                logger.debug(f"Could not register {cls_name}: {e}")

    def register(self, device_type: DeviceType, adapter_cls: type[AdapterProtocol]) -> None:
        self._by_type[device_type] = adapter_cls
        logger.debug(f"Registered adapter {adapter_cls.__name__} for {device_type.value}")

    def resolve(self, device_type: DeviceType) -> type[AdapterProtocol] | None:
        self._ensure_initialized()
        return self._by_type.get(device_type)

    def create(self, device_type: DeviceType) -> AdapterProtocol | None:
        self._ensure_initialized()
        cls = self._by_type.get(device_type)
        if cls is None:
            logger.warning(f"No adapter registered for {device_type.value}")
            return None
        return cls()

    def get_or_create(self, device_type: DeviceType) -> AdapterProtocol | None:
        self._ensure_initialized()
        if device_type not in self._instances:
            adapter = self.create(device_type)
            if adapter:
                self._instances[device_type] = adapter
        return self._instances.get(device_type)

    def dispatch(self, command: str, serial: str = "", device_type: DeviceType = DeviceType.ADB) -> tuple[bool, str]:
        """Execute a command through the appropriate adapter.

        Parses command prefixes (adb:, adb_shell:, fastboot:, edl:, brom:)
        and dispatches to the correct adapter. Falls back to subprocess if
        no adapter matches or if the adapter fails.
        """
        self._ensure_initialized()

        prefix_map: dict[str, DeviceType] = {
            "adb": DeviceType.ADB,
            "adb_shell": DeviceType.ADB,
            "fastboot": DeviceType.FASTBOOT,
            "edl": DeviceType.QUALCOMM_EDL,
            "brom": DeviceType.MTK_BROM,
        }

        prefix = command.split(":")[0] if ":" in command else ""
        resolved_type = prefix_map.get(prefix)

        if resolved_type is None:
            return self._fallback_subprocess(command, serial)

        adapter = self.get_or_create(resolved_type)
        if adapter is None:
            return self._fallback_subprocess(command, serial)

        try:
            if serial:
                adapter.connect(serial)

            # Strip prefix and split into args
            cmd_str = command[len(prefix) + 1:].strip() if prefix in prefix_map else command
            args = [a for a in cmd_str.split() if a]

            if not args:
                return True, ""

            # Special handling for adb_shell: prefix
            if prefix == "adb_shell":
                result = adapter.run("shell", *args, timeout=120)
            else:
                result = adapter.run(*args, timeout=120)

            return result.success, result.stdout or result.stderr
        except Exception:
            return self._fallback_subprocess(command, serial)

    @staticmethod
    def _fallback_subprocess(command: str, serial: str = "") -> tuple[bool, str]:
        """Fallback to subprocess when adapter dispatch fails."""
        import subprocess
        try:
            args = command.split()
            proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
            return proc.returncode == 0, proc.stdout.strip() or proc.stderr.strip()
        except Exception as e:
            return False, str(e)

    def supported_types(self) -> list[DeviceType]:
        self._ensure_initialized()
        return list(self._by_type.keys())

    def available_types(self) -> list[DeviceType]:
        self._ensure_initialized()
        return [dt for dt, adapter in self._instances.items() if adapter.is_available()]

    def __contains__(self, device_type: object) -> bool:
        if not isinstance(device_type, DeviceType):
            return False
        self._ensure_initialized()
        return device_type in self._by_type


# Module-level singleton
_registry: AdapterRegistry | None = None


def get_adapter_registry() -> AdapterRegistry:
    global _registry
    if _registry is None:
        _registry = AdapterRegistry(auto_register=True)
    return _registry

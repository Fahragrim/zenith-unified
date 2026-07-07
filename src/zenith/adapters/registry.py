"""Adapter Registry — maps DeviceType to AdapterProtocol implementations."""

from __future__ import annotations

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol
from zenith.core.device import DeviceType


class AdapterRegistry:
    """Central registry: DeviceType → Adapter class."""

    def __init__(self) -> None:
        self._by_type: dict[DeviceType, type[AdapterProtocol]] = {}
        self._instances: dict[DeviceType, AdapterProtocol] = {}

    def register(self, device_type: DeviceType, adapter_cls: type[AdapterProtocol]) -> None:
        self._by_type[device_type] = adapter_cls
        logger.debug(f"Registered adapter {adapter_cls.__name__} for {device_type.value}")

    def resolve(self, device_type: DeviceType) -> type[AdapterProtocol] | None:
        return self._by_type.get(device_type)

    def create(self, device_type: DeviceType) -> AdapterProtocol | None:
        cls = self._by_type.get(device_type)
        if cls is None:
            logger.warning(f"No adapter registered for {device_type.value}")
            return None
        return cls()

    def get_or_create(self, device_type: DeviceType) -> AdapterProtocol | None:
        if device_type not in self._instances:
            adapter = self.create(device_type)
            if adapter:
                self._instances[device_type] = adapter
        return self._instances.get(device_type)

    def supported_types(self) -> list[DeviceType]:
        return list(self._by_type.keys())

    def available_types(self) -> list[DeviceType]:
        return [dt for dt, adapter in self._instances.items() if adapter.is_available()]

    def __contains__(self, device_type: object) -> bool:
        return isinstance(device_type, DeviceType) and device_type in self._by_type


# Module-level singleton
_registry: AdapterRegistry | None = None


def get_adapter_registry() -> AdapterRegistry:
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
    return _registry

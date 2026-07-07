"""UART Adapter — serial port analyzer."""

from __future__ import annotations

from typing import Any, ClassVar

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class UARTAdapter(AdapterProtocol):
    name: ClassVar[str] = "uart"
    binary: ClassVar[str] = ""
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.UART,)

    def is_available(self) -> bool:
        try:
            import serial  # noqa: F401
            return True
        except ImportError:
            return False

    def list_devices(self) -> list[dict[str, Any]]:
        return []

    def run(self, *args: str, timeout: int = 60) -> AdapterResult:
        return AdapterResult(success=False, command="UART", stderr="Use scan() to find ports")

    def scan(self) -> list[dict[str, Any]]:
        ports: list[dict[str, Any]] = []
        try:
            import serial.tools.list_ports
            for p in serial.tools.list_ports.comports():
                ports.append({"device": p.device, "description": p.description or "", "hwid": p.hwid or ""})
        except Exception:
            pass
        return ports

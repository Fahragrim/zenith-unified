"""Adapter Protocol — unified interface for all transport adapters.

Every adapter must satisfy the AdapterProtocol. Adapters contain no business
logic — they are pure transports wrapping external tools or native protocols.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from zenith.core.device import DeviceType


@dataclass(frozen=True)
class AdapterResult:
    """Result of an adapter command execution."""

    success: bool
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    data: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.success

    def __str__(self) -> str:
        status = "OK" if self.success else "FAIL"
        return f"[{status}] {self.command}: {self.stdout[:80] or self.stderr[:80]}"


class AdapterProtocol(ABC):
    """Abstract base for all transport adapters."""

    name: ClassVar[str] = "base"
    binary: ClassVar[str] = ""
    supported_types: ClassVar[tuple[DeviceType, ...]] = ()

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the underlying tool/binary is installed."""
        ...

    @abstractmethod
    def list_devices(self) -> list[dict[str, Any]]:
        """List connected devices for this transport."""
        ...

    @abstractmethod
    def run(self, *args: str, timeout: int = 30) -> AdapterResult:
        """Execute a command. Returns AdapterResult."""
        ...

    def connect(self, device_id: str) -> AdapterResult:
        """Bind to a device. Override if protocol requires explicit connect."""
        return AdapterResult(success=True, command=f"{self.name} connect {device_id}")

    def disconnect(self) -> None:
        """Release any held resources."""
        return

    def get_info(self, device_id: str) -> dict[str, Any]:
        """Get device information."""
        return {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(binary={self.binary or 'native'})"

"""Allwinner FEL Adapter — wraps sunxi-fel."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, ClassVar

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class AllwinnerFELAdapter(AdapterProtocol):
    name: ClassVar[str] = "allwinner_fel"
    binary: ClassVar[str] = "sunxi-fel"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.ALLWINNER_FEL,)

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def list_devices(self) -> list[dict[str, Any]]:
        return []

    def run(self, *args: str, timeout: int = 120) -> AdapterResult:
        try:
            proc = subprocess.run([self.binary] + list(args), capture_output=True, text=True, timeout=timeout)
            return AdapterResult(success=proc.returncode == 0, command=f"sunxi-fel {' '.join(args)}",
                                stdout=proc.stdout.strip(), stderr=proc.stderr.strip())
        except Exception as e:
            return AdapterResult(success=False, command="sunxi-fel", stderr=str(e))

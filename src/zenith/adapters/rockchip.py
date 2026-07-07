"""Rockchip MaskROM Adapter — wraps rkdeveloptool."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, ClassVar

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class RockchipAdapter(AdapterProtocol):
    name: ClassVar[str] = "rockchip"
    binary: ClassVar[str] = "rkdeveloptool"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.ROCKCHIP_MASKROM,)

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def list_devices(self) -> list[dict[str, Any]]:
        return []

    def run(self, *args: str, timeout: int = 120) -> AdapterResult:
        try:
            proc = subprocess.run([self.binary] + list(args), capture_output=True, text=True, timeout=timeout)
            return AdapterResult(success=proc.returncode == 0, command=f"rkdeveloptool {' '.join(args)}",
                                stdout=proc.stdout.strip(), stderr=proc.stderr.strip())
        except Exception as e:
            return AdapterResult(success=False, command="rkdeveloptool", stderr=str(e))

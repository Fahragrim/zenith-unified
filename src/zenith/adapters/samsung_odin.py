"""Samsung Odin Adapter — wraps Heimdall for Samsung Download Mode."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class SamsungOdinAdapter(AdapterProtocol):
    name: ClassVar[str] = "samsung_odin"
    binary: ClassVar[str] = "heimdall"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.SAMSUNG_ODIN,)

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def list_devices(self) -> list[dict[str, Any]]:
        return []

    def run(self, *args: str, timeout: int = 120) -> AdapterResult:
        return self._exec(list(args), timeout)

    def _exec(self, args: list[str], timeout: int = 120) -> AdapterResult:
        try:
            proc = subprocess.run([self.binary] + args, capture_output=True, text=True, timeout=timeout)
            return AdapterResult(success=proc.returncode == 0, command=f"{self.binary} {' '.join(args)}",
                                stdout=proc.stdout.strip(), stderr=proc.stderr.strip())
        except Exception as e:
            return AdapterResult(success=False, command=self.binary, stderr=str(e))

    def print_pit(self) -> AdapterResult:
        return self._exec(["print-pit"])

    def flash(self, partition: str, image: str) -> AdapterResult:
        if not Path(image).exists():
            return AdapterResult(success=False, command="heimdall flash", stderr=f"Image not found: {image}")
        logger.warning(f"Odin flash: {partition} ← {image}")
        return self._exec(["flash", "--" + partition.upper(), image], timeout=300)

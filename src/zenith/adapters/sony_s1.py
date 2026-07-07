"""Sony S1 Adapter — wraps Newflasher for Sony Flashmode."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class SonyS1Adapter(AdapterProtocol):
    name: ClassVar[str] = "sony_s1"
    binary: ClassVar[str] = "newflasher"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.QUALCOMM_EDL,)

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None or Path("newflasher.exe").exists()

    def list_devices(self) -> list[dict[str, Any]]:
        return []

    def run(self, *args: str, timeout: int = 600) -> AdapterResult:
        nf = shutil.which(self.binary)
        if nf is None and Path("newflasher.exe").exists():
            nf = "newflasher.exe"
        if nf is None:
            return AdapterResult(success=False, command="newflasher", stderr="newflasher not found")
        try:
            proc = subprocess.run([nf] + list(args), capture_output=True, text=True, timeout=timeout)
            return AdapterResult(success=proc.returncode == 0, command=f"newflasher {' '.join(args)}",
                                stdout=proc.stdout.strip(), stderr=proc.stderr.strip())
        except Exception as e:
            return AdapterResult(success=False, command="newflasher", stderr=str(e))

    def flash(self) -> AdapterResult:
        logger.warning("Newflasher — flashing firmware")
        return self.run()

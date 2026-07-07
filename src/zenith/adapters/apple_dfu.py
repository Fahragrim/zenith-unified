"""Apple DFU Adapter — wraps libimobiledevice tools."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any, ClassVar

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class AppleDFUAdapter(AdapterProtocol):
    name: ClassVar[str] = "apple_dfu"
    binary: ClassVar[str] = "ideviceinfo"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.APPLE_DFU,)

    def is_available(self) -> bool:
        return shutil.which("idevice_id") is not None

    def list_devices(self) -> list[dict[str, Any]]:
        try:
            proc = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, timeout=10)
            if proc.returncode == 0:
                return [{"serial": s} for s in proc.stdout.strip().split("\n") if s.strip()]
        except Exception:
            pass
        return []

    def run(self, *args: str, timeout: int = 30) -> AdapterResult:
        try:
            proc = subprocess.run([self.binary] + list(args), capture_output=True, text=True, timeout=timeout)
            return AdapterResult(success=proc.returncode == 0, command=f"ideviceinfo {' '.join(args)}",
                                stdout=proc.stdout.strip(), stderr=proc.stderr.strip())
        except Exception as e:
            return AdapterResult(success=False, command="ideviceinfo", stderr=str(e))

    def get_info(self, device_id: str = "") -> dict[str, Any]:
        info: dict[str, Any] = {}
        try:
            proc = subprocess.run(["ideviceinfo"], capture_output=True, text=True, timeout=10)
            if proc.returncode == 0:
                for line in proc.stdout.split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        info[k.strip()] = v.strip()
        except Exception:
            pass
        return info

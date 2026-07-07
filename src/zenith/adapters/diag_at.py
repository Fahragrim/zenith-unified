"""Diag/AT Adapter — Qualcomm Diag mode + AT command serial interface."""

from __future__ import annotations

from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class DiagATAdapter(AdapterProtocol):
    name: ClassVar[str] = "diag_at"
    binary: ClassVar[str] = ""
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.DIAG,)

    CRASH_PAYLOADS: ClassVar[list[str]] = [
        "AT+CFUN=0", "AT+SYSDUMP=1,0", "AT$QCPWRDN", "AT+KDEAD",
    ]

    def is_available(self) -> bool:
        try:
            import serial  # noqa: F401
            return True
        except ImportError:
            return False

    def list_devices(self) -> list[dict[str, Any]]:
        return []

    def run(self, *args: str, timeout: int = 60) -> AdapterResult:
        return AdapterResult(success=False, command="AT", stderr="Use send_at(port, command) instead")

    def send_at(self, port: str, command: str, baud: int = 115200) -> AdapterResult:
        try:
            import serial
            with serial.Serial(port, baud, timeout=2) as s:
                s.write(f"{command}\r\n".encode())
                resp = s.read(4096)
                return AdapterResult(success=True, command=f"AT {command}",
                                    stdout=resp.decode(errors="replace").strip())
        except Exception as e:
            return AdapterResult(success=False, command=f"AT {command}", stderr=str(e))

    def panic_inject(self, port: str) -> list[AdapterResult]:
        results: list[AdapterResult] = []
        for payload in self.CRASH_PAYLOADS:
            results.append(self.send_at(port, payload))
            logger.warning(f"Panic inject: {payload}")
        return results

    def scan_ports(self) -> list[dict[str, str]]:
        ports: list[dict[str, str]] = []
        try:
            import serial.tools.list_ports
            for p in serial.tools.list_ports.comports():
                ports.append({"device": p.device, "description": p.description or "", "hwid": p.hwid or ""})
        except Exception:
            pass
        return ports

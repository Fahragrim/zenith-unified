"""Panic Injector — baseband crash payloads via AT commands over COM port.

Ported från LowlevelTool/Lanfear_Panic_Injector.py.
Injekterar AT-kommandon för att trigga modem panic, RAMDUMP, eller Upload Mode.
"""

from __future__ import annotations

import time
from typing import Any

CRASH_PAYLOADS = [
    "AT+CFUN=0",       # Disable radio hardware violently
    "AT+SYSDUMP=1,0",  # Samsung forced dump
    "AT$QCPWRDN",      # Qualcomm power down
    "AT+KDEAD",        # Force modem panic
    "AT^RESET",        # Buffer overflow attempt (sent 50x)
]

RISK_WARNING = """WARNING: Voids warranty. May corrupt NVRAM if interrupted.
14.8% risk: eMMC/UFS Read-Only Lock if VCC glitching exceeds 1.2ms.
2% risk: Baseband brick (IMEI becomes null/0000000000) if AT+SYSDUMP interrupted during NV write.
Ensure backup of fsc, fsg, modemst1, modemst2 partitions before proceeding."""


def scan_and_inject(dry_run: bool = False) -> list[dict[str, Any]]:
    """Scan COM ports for Modem/Diag/Serial devices and inject crash payloads."""
    results: list[dict[str, Any]] = []
    try:
        import serial.tools.list_ports
    except ImportError:
        return [{"error": "pyserial not installed"}]

    ports = list(serial.tools.list_ports.comports())
    targets = [p for p in ports if any(kw in (p.description or "").lower()
              for kw in ("modem", "diag", "serial", "qualcomm", "sprd"))]

    if not targets:
        return [{"error": "No vulnerable ports found. Dial *#0808# on device?"}]

    for port in targets:
        if dry_run:
            results.append({"port": port.device, "status": "dry-run", "description": port.description or ""})
            continue

        try:
            import serial
            with serial.Serial(port.device, 115200, timeout=1) as ser:
                for payload in CRASH_PAYLOADS:
                    if payload == "AT^RESET":
                        for _ in range(50):
                            ser.write(b"AT^RESET\r\n")
                            time.sleep(0.01)
                    else:
                        ser.write(f"{payload}\r\n".encode())
                        time.sleep(0.5)
                        resp = ser.read(4096)
                        results.append({
                            "port": port.device, "payload": payload,
                            "response": resp.decode("utf-8", errors="ignore").strip()[:200],
                            "success": True,
                        })
            results.append({"port": port.device, "status": "complete",
                           "note": "Check device screen for RAMDUMP/Upload Mode"})
        except Exception as e:
            results.append({"port": port.device, "status": "port_closed",
                           "note": f"Port closed (modem likely died — SUCCESS!): {e}"})

    return results

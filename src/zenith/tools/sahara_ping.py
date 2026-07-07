"""Sahara Ping — probe Qualcomm EDL devices via raw COM port."""

from __future__ import annotations

import time


def sahara_ping_scan(max_port: int = 32) -> list[dict]:
    """Scan COM ports for Qualcomm EDL devices using Sahara Hello packet."""
    results: list[dict] = []
    try:
        import serial
    except ImportError:
        return [{"error": "pyserial not installed"}]

    hello = bytes.fromhex("01000000300000000200000001000000")
    for port_num in range(1, max_port + 1):
        try:
            s = serial.Serial(f"COM{port_num}", 115200, timeout=1)
            s.write(hello)
            time.sleep(0.2)
            resp = s.read(48)
            s.close()
            if resp and len(resp) > 0:
                results.append({"port": f"COM{port_num}", "response_hex": resp[:16].hex(), "response_len": len(resp)})
        except Exception:
            continue
    return results

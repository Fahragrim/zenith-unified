"""Fastboot OEM Command Fuzzer — discover hidden bootloader commands."""

from __future__ import annotations

import subprocess
import time
from typing import Any

OEM_COMMANDS = [
    "unlock", "unlock-go", "device-info", "edl", "reboot-recovery",
    "enable-bp-tools", "qcom-on", "diag-enable", "hw-test",
    "off-mode-charge 0", "dump-registers", "test-mode", "debug-on",
    "serial-log-on", "atd-on",
]


def fuzz_oem_commands(fastboot_path: str = "fastboot", delay: float = 0.5) -> list[dict[str, Any]]:
    """Fuzz fastboot OEM commands and report interesting responses."""
    results: list[dict[str, Any]] = []
    for cmd in OEM_COMMANDS:
        try:
            proc = subprocess.run(
                [fastboot_path, "oem"] + cmd.split(),
                capture_output=True, text=True, timeout=10,
            )
            stderr_lower = proc.stderr.lower()
            interesting = "unknown command" not in stderr_lower and "not allowed" not in stderr_lower
            results.append({
                "command": f"fastboot oem {cmd}",
                "response": proc.stderr.strip() or proc.stdout.strip(),
                "interesting": interesting,
            })
        except Exception as e:
            results.append({"command": f"fastboot oem {cmd}", "response": str(e), "interesting": False})
        time.sleep(delay)
    return results

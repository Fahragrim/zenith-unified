"""Subprocess runner utility for adapters."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandResult:
    success: bool
    command: str
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    data: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.success


def run_command(binary: str, args: list[str], *, timeout: int = 60) -> CommandResult:
    """Run a subprocess command and return a normalized CommandResult."""
    cmd = f"{binary} {' '.join(args)}"
    try:
        proc = subprocess.run([binary] + args, capture_output=True, text=True, timeout=timeout)
        return CommandResult(
            success=proc.returncode == 0,
            command=cmd,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
            returncode=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(success=False, command=cmd, stderr="Timed out")
    except FileNotFoundError:
        return CommandResult(success=False, command=cmd, stderr=f"Binary not found: {binary}")
    except Exception as e:
        return CommandResult(success=False, command=cmd, stderr=str(e))

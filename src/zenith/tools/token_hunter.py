"""Token Hunter — scan logcat for leaked tokens, passwords, and keys."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

TOKEN_PATTERN = re.compile(
    r"(ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"  # JWT
    r"|Bearer [A-Za-z0-9\-._~+/]+=*"  # Bearer token
    r"|password=[a-zA-Z0-9!@#$&*]+"  # Password
    r"|BEGIN RSA PRIVATE KEY"  # RSA key
    r"|-----BEGIN PRIVATE KEY-----"  # Generic private key
    r")"
)


def token_hunt_logcat(duration: int = 30, output_file: str | None = None) -> list[dict[str, Any]]:
    """Scan logcat for leaked credentials. Returns list of findings.

    If output_file is None, writes to a temp file that is cleaned up automatically.
    """
    import time as _time

    findings: list[dict[str, Any]] = []
    _tmpdir: tempfile.TemporaryDirectory | None = None
    if not output_file:
        _tmpdir = tempfile.TemporaryDirectory(prefix="zenith_token_")
        out_path = str(Path(_tmpdir.name) / "findings.txt")
    else:
        out_path = output_file
    try:
        proc = subprocess.Popen(
            ["adb", "logcat"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        start = _time.time()
        with open(out_path, "w") as f:
            while _time.time() - start < duration:
                line = proc.stdout.readline()  # type: ignore[union-attr]
                if not line:
                    break
                match = TOKEN_PATTERN.search(line)
                if match:
                    findings.append({"match": match.group(0)[:80], "line": line.strip()[:200]})
                    f.write(line)
        proc.terminate()
    except Exception as e:
        return [{"error": str(e)}]
    finally:
        if _tmpdir is not None:
            _tmpdir.cleanup()
    return findings

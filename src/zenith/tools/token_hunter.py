"""Token Hunter — scan logcat for leaked tokens, passwords, and keys."""

from __future__ import annotations

import re
import subprocess

TOKEN_PATTERN = re.compile(
    r"(ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"  # JWT
    r"|Bearer [A-Za-z0-9\-._~+/]+=*"  # Bearer token
    r"|password=[a-zA-Z0-9!@#$&*]+"  # Password
    r"|BEGIN RSA PRIVATE KEY"  # RSA key
    r"|-----BEGIN PRIVATE KEY-----"  # Generic private key
    r")"
)


def token_hunt_logcat(output_file: str = "lanfear_loot.txt", duration: int = 30) -> list[dict]:
    """Scan logcat for leaked credentials. Returns list of findings."""
    findings: list[dict] = []
    try:
        proc = subprocess.Popen(
            ["adb", "logcat"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        start = __import__("time").time()
        with open(output_file, "w") as f:
            while __import__("time").time() - start < duration:
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
    return findings

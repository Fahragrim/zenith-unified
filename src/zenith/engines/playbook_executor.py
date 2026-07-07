"""Playbook Executor — executes YAML repair playbooks step-by-step.

Command prefix routing: adb:, adb_shell:, fastboot:, shell:, edl:, newflasher:.
NO shell=True — all subprocess calls use list-based arguments for security.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class StepResult:
    step_number: int
    description: str
    command: str = ""
    success: bool = True
    output: str = ""
    error: str = ""


@dataclass
class PlaybookRunResult:
    playbook_id: str
    title: str
    success: bool = False
    steps_completed: int = 0
    total_steps: int = 0
    results: list[StepResult] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"playbook_id": self.playbook_id, "title": self.title, "success": self.success,
                "steps_completed": self.steps_completed, "total_steps": self.total_steps,
                "results": [{"step": r.step_number, "description": r.description, "command": r.command,
                            "success": r.success, "output": r.output[:200], "error": r.error} for r in self.results],
                "error": self.error}


class PlaybookExecutor:
    """Executes playbooks. NO shell=True. Uses list-based subprocess."""

    def __init__(self) -> None:
        self.dry_run = False

    def execute(self, playbook: dict[str, Any], device_serial: str = "") -> PlaybookRunResult:
        title = playbook.get("title", "Unknown")
        pb_id = playbook.get("id", "unknown")
        steps = playbook.get("steps", [])
        result = PlaybookRunResult(playbook_id=pb_id, title=title, total_steps=len(steps))
        logger.info(f"Executing: {title} ({len(steps)} steps)")

        for idx, step in enumerate(steps):
            step_num = step.get("step_number", step.get("step", idx + 1))
            if isinstance(step_num, dict):
                step_num = step_num.get("number", idx + 1)
            desc = step.get("description", step.get("desc", f"Step {step_num}"))
            cmd = step.get("command", "")

            sn = int(step_num) if isinstance(step_num, (int, float)) or (isinstance(step_num, str) and str(step_num).isdigit()) else idx + 1
            sr = StepResult(step_number=sn, description=str(desc), command=str(cmd))

            if not cmd:
                sr.success = True
                result.results.append(sr)
                continue

            ok, out = self._exec(str(cmd), device_serial)
            sr.success = ok
            sr.output = out or ""
            if not ok:
                sr.error = out or "Failed"
                fallback = step.get("fallback")
                if fallback:
                    logger.info(f"Step {sn} failed. Fallback: {fallback}")
                    fb_ok, fb_out = self._exec(str(fallback), device_serial)
                    if fb_ok:
                        sr.success = True
                        sr.output = f"[fallback] {fb_out}"
                        result.results.append(sr)
                        continue
                result.results.append(sr)
                result.error = f"Step {sn}: {desc}"
                return result
            result.results.append(sr)

        result.success = True
        result.steps_completed = sum(1 for r in result.results if r.success)
        logger.info(f"Playbook OK: {title} ({result.steps_completed}/{result.total_steps})")
        return result

    def _exec(self, command: str, serial: str = "") -> tuple[bool, str]:
        if self.dry_run:
            return True, f"[dry-run] {command}"

        try:
            if command.startswith("adb_shell:"):
                cmd_str = command[len("adb_shell:"):].strip()
                if serial:
                    return self._run(["adb", "-s", serial, "shell", cmd_str], timeout=60)
                return self._run(["adb", "shell", cmd_str], timeout=60)

            elif command.startswith("adb:"):
                cmd_str = command[len("adb:"):].strip()
                base = ["adb"] + (["-s", serial] if serial else []) + cmd_str.split()
                return self._run(base, timeout=60)

            elif command.startswith("fastboot:"):
                cmd_str = command[len("fastboot:"):].strip()
                return self._run(["fastboot"] + cmd_str.split(), timeout=120)

            elif command.startswith("shell:"):
                cmd_str = command[len("shell:"):].strip()
                return self._run(cmd_str.split(), timeout=60)

            elif command.startswith("edl:"):
                cmd_str = command[len("edl:"):].strip()
                return self._run(["edl"] + cmd_str.split(), timeout=300)

            elif command.startswith("newflasher:"):
                cmd_str = command[len("newflasher:"):].strip()
                nf = shutil.which("newflasher") or "newflasher"
                return self._run([nf] + cmd_str.split(), timeout=600)

            else:
                return self._run(command.split(), timeout=60)

        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _run(args: list[str], timeout: int = 60) -> tuple[bool, str]:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return (proc.returncode == 0, proc.stdout.strip() or proc.stderr.strip())

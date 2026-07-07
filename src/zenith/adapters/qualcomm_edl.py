"""Qualcomm EDL Adapter — Emergency Download Mode via bkerler/edl.

Wraps the edl tool for Sahara+Firehose protocol operations.
USB VID: 05C6, PID: 9008.
Supports: printgpt, dump/flash/erase partitions, safe firehose flash with snapshot.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class QualcommEDLAdapter(AdapterProtocol):
    name: ClassVar[str] = "qualcomm_edl"
    binary: ClassVar[str] = "edl"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.QUALCOMM_EDL,)

    def __init__(self, loader: str | None = None) -> None:
        self._python = "python"
        self._loader = loader
        self._available = False
        self._init()

    def _init(self) -> None:
        self._edl_path = self._find_edl()
        self._available = self._edl_path is not None
        if self._available:
            logger.info(f"EDL adapter: {self._edl_path}")

    def _find_edl(self) -> str | None:
        candidates = [shutil.which("edl")]
        python_exe = shutil.which("python")
        if python_exe:
            candidates.append(str(Path(python_exe).parent / "Scripts" / "edl.exe"))
        for c in candidates:
            if c and Path(c).exists():
                return c
        try:
            result = subprocess.run(
                [self._python, "-c", "import edl; print(edl.__file__)"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                p = Path(result.stdout.strip()).parent / "edl.py"
                if p.exists():
                    return str(p)
        except Exception:
            pass
        return None

    def is_available(self) -> bool:
        return self._available

    def _run(self, *args: str, timeout: int = 120) -> dict[str, Any]:
        if not self._available:
            return {"success": False, "error": "edl tool not found"}
        cmd = [self._python, str(self._edl_path)] + list(args)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {"success": proc.returncode == 0, "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(), "returncode": proc.returncode}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_devices(self) -> list[dict[str, Any]]:
        return [{"status": "available", "tool": "edl"}] if self._available else []

    def run(self, *args: str, timeout: int = 120) -> AdapterResult:
        r = self._run(*args, timeout=timeout)
        return AdapterResult(success=r["success"], command=f"edl {' '.join(args)}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def printgpt(self, serial: str | None = None) -> AdapterResult:
        args = ["printgpt"]
        if serial:
            args = ["-s", serial] + args
        if self._loader:
            args.insert(1, f"--loader={self._loader}")
        r = self._run(*args)
        return AdapterResult(success=r["success"], command="edl printgpt",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def dump_partition(self, partition: str, output: str, serial: str | None = None) -> AdapterResult:
        logger.warning(f"EDL DUMP: {partition} → {output}")
        args = ["r", f"--partition={partition}", f"--outfile={output}"]
        if serial:
            args = ["-s", serial] + args
        if self._loader:
            args.insert(1 if serial else 0, f"--loader={self._loader}")
        r = self._run(*args, timeout=300)
        return AdapterResult(success=r["success"], command=f"edl dump {partition}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def flash_partition(self, partition: str, image: str, serial: str | None = None) -> AdapterResult:
        if not Path(image).exists():
            return AdapterResult(success=False, command=f"edl flash {partition}",
                                stderr=f"Image not found: {image}")
        logger.warning(f"EDL FLASH: {image} → {partition}")
        args = ["w", f"--partition={partition}", f"--sid={image}"]
        if serial:
            args = ["-s", serial] + args
        if self._loader:
            args.insert(1 if serial else 0, f"--loader={self._loader}")
        r = self._run(*args, timeout=300)
        return AdapterResult(success=r["success"], command=f"edl flash {partition}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def erase_partition(self, partition: str, serial: str | None = None) -> AdapterResult:
        logger.warning(f"EDL ERASE: {partition}")
        args = ["e", f"--partition={partition}"]
        if serial:
            args = ["-s", serial] + args
        if self._loader:
            args.insert(1 if serial else 0, f"--loader={self._loader}")
        r = self._run(*args)
        return AdapterResult(success=r["success"], command=f"edl erase {partition}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def safe_firehose_flash(self, partition: str, image: str, serial: str | None = None) -> AdapterResult:
        if not Path(image).exists():
            return AdapterResult(success=False, command="edl safe_flash", stderr=f"Image not found: {image}")
        import time
        snapshot = f"/tmp/snapshot_{partition}_{int(time.time())}.img"
        dump = self.dump_partition(partition, snapshot, serial)
        if not dump.success:
            return AdapterResult(success=False, command="edl safe_flash",
                                stderr=f"Failed to create snapshot: {dump.stderr}")
        result = self.flash_partition(partition, image, serial)
        if result.success:
            return AdapterResult(success=True, command="edl safe_flash",
                                stdout=f"Flash OK. Snapshot: {snapshot}")
        return AdapterResult(success=False, command="edl safe_flash",
                            stderr=result.stderr, data={"snapshot": snapshot})

    def sahara_ping(self) -> AdapterResult:
        try:
            import time

            import serial as _serial
            hello = bytes.fromhex("01000000300000000200000001000000")
            for port_num in range(1, 32):
                try:
                    s = _serial.Serial(f"COM{port_num}", 115200, timeout=1)
                    s.write(hello)
                    time.sleep(0.2)
                    resp = s.read(48)
                    s.close()
                    if resp and len(resp) > 0:
                        return AdapterResult(success=True, command=f"Sahara ping COM{port_num}",
                                            stdout=f"Response: {resp[:16].hex()}...")
                except Exception:
                    continue
            return AdapterResult(success=False, command="Sahara ping", stderr="No EDL device found")
        except ImportError:
            return AdapterResult(success=False, command="Sahara ping", stderr="pyserial not installed")

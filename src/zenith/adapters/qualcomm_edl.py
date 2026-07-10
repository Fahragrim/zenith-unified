"""Qualcomm EDL Adapter — Emergency Download Mode via native pyusb transport.

USB VID: 05C6, PID: 9008.
Primary transport is EdlUsbTransport (pyusb); falls back to bkerler/edl tool.
"""

from __future__ import annotations

import contextlib
import importlib.util
import shutil
import subprocess
import time
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
        import sys as _sys
        self._python = _sys.executable
        self._loader = loader
        self._available = False
        self._transport = None
        self._init()

    def _init(self) -> None:
        self._edl_path = self._find_edl()
        self._has_pyusb = bool(importlib.util.find_spec("usb.core"))
        self._available = self._edl_path is not None or self._has_pyusb
        if self._available:
            logger.info(f"EDL adapter ready: pyusb={self._has_pyusb} edl_tool={self._edl_path is not None}")

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

    def connect(self, device_id: str = "") -> AdapterResult:
        if not self._has_pyusb:
            return AdapterResult(success=False, command="edl connect",
                                stderr="pyusb not installed — use subprocess fallback")
        try:
            from zenith.adapters.usb_transport import EdlUsbTransport
            t = EdlUsbTransport()
            serial = t.detect()
            if serial is None:
                return AdapterResult(success=False, command="edl connect",
                                    stderr="No EDL device found (VID 05C6, PID 9008)")
            self._transport = t
            t.sahara_hello()
            return AdapterResult(success=True, command=f"edl connect {serial}",
                                stdout=f"EDL device: {serial}")
        except Exception as e:
            return AdapterResult(success=False, command="edl connect", stderr=str(e))

    def disconnect(self) -> None:
        if self._transport is not None:
            with contextlib.suppress(Exception):
                self._transport.close()
            self._transport = None

    def _run(self, *args: str, timeout: int = 120) -> dict[str, Any]:
        if not self._edl_path:
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

    def _run_transport(self, command: str, *args: str, timeout: int = 120) -> AdapterResult:
        if self._transport is None:
            return AdapterResult(success=False, command=command, stderr="No transport. Call connect() first.")
        try:
            if command == "sahara_hello":
                resp = self._transport.sahara_hello()
                ok = "error" not in resp
                return AdapterResult(success=ok, command=command, stdout=str(resp))
            elif command == "firehose_connect":
                ok = self._transport.firehose_connect()
                return AdapterResult(success=ok, command=command)
            elif command == "firehose_reset":
                ok = self._transport.firehose_reset()
                return AdapterResult(success=ok, command=command)
            elif command == "sahara_upload_loader":
                if not args:
                    return AdapterResult(success=False, command=command, stderr="Missing loader path")
                ok = self._transport.sahara_upload_loader(args[0])
                return AdapterResult(success=ok, command=f"{command} {args[0]}")
            else:
                return AdapterResult(success=False, command=command, stderr=f"Unknown transport command: {command}")
        except Exception as e:
            return AdapterResult(success=False, command=command, stderr=str(e))

    def list_devices(self) -> list[dict[str, Any]]:
        if self._has_pyusb:
            try:
                import usb.core
                dev = usb.core.find(idVendor=0x05C6, idProduct=0x9008)
                if dev is not None:
                    return [{"serial": f"EDL_{dev.bus:03d}_{dev.address:03d}",
                             "vid": "0x05C6", "pid": "0x9008", "status": "detected"}]
            except Exception:
                pass
        if self._edl_path:
            return [{"status": "available", "tool": "edl"}]
        return []

    def run(self, *args: str, timeout: int = 120) -> AdapterResult:
        if not args:
            return AdapterResult(success=False, command="edl", stderr="No command")
        cmd = args[0]
        transport_commands = {"sahara_hello", "firehose_connect", "firehose_reset", "sahara_upload_loader"}
        if cmd in transport_commands:
            return self._run_transport(cmd, *args[1:], timeout=timeout)
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
        logger.warning(f"EDL DUMP: {partition} -> {output}")
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
        logger.warning(f"EDL FLASH: {image} -> {partition}")
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

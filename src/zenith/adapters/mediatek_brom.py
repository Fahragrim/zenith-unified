"""MediaTek BROM Adapter — Boot ROM mode via native pyusb transport.

USB VID: 0E8D, PID varies (2000, 3000).
Primary transport is BromUsbTransport (pyusb); falls back to mtkclient.
"""

from __future__ import annotations

import contextlib
import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from loguru import logger

from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.core.device import DeviceType


class MediaTekBROMAdapter(AdapterProtocol):
    name: ClassVar[str] = "mediatek_brom"
    binary: ClassVar[str] = "mtk"
    supported_types: ClassVar[tuple[DeviceType, ...]] = (DeviceType.MTK_BROM,)

    def __init__(self) -> None:
        import sys as _sys
        self._python = _sys.executable
        self._available = False
        self._authenticated = False
        self._transport = None
        self._init()

    def _init(self) -> None:
        self._mtk_path = self._find_mtk()
        self._has_pyusb = bool(importlib.util.find_spec("usb.core"))
        self._available = self._mtk_path is not None or self._has_pyusb
        if self._available:
            logger.info(f"BROM adapter ready: pyusb={self._has_pyusb} mtkclient={self._mtk_path is not None}")

    def _find_mtk(self) -> str | None:
        for c in [shutil.which("mtk"), shutil.which("mtkclient")]:
            if c and Path(c).exists():
                return c
        try:
            result = subprocess.run(
                [self._python, "-c", "import mtkclient; print(mtkclient.__file__)"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                p = Path(result.stdout.strip()).parent / "mtk" / "main.py"
                if p.exists():
                    return str(p)
        except Exception:
            pass
        return None

    def is_available(self) -> bool:
        return self._available

    def connect(self, device_id: str = "") -> AdapterResult:
        if not self._has_pyusb:
            return AdapterResult(success=False, command="brom connect",
                                stderr="pyusb not installed — use subprocess fallback")
        try:
            from zenith.adapters.usb_transport import BromUsbTransport
            t = BromUsbTransport()
            serial = t.detect()
            if serial is None:
                return AdapterResult(success=False, command="brom connect",
                                    stderr="No BROM device found (VID 0E8D)")
            self._transport = t
            resp = t.handshake()
            if "error" in resp:
                return AdapterResult(success=False, command="brom connect",
                                    stderr=f"Handshake failed: {resp['error']}")
            return AdapterResult(success=True, command=f"brom connect {serial}",
                                stdout=f"BROM device: {serial} handshake={resp}")
        except Exception as e:
            return AdapterResult(success=False, command="brom connect", stderr=str(e))

    def disconnect(self) -> None:
        if self._transport is not None:
            with contextlib.suppress(Exception):
                self._transport.close()
            self._transport = None

    def _run(self, *args: str, timeout: int = 120) -> dict[str, Any]:
        if not self._mtk_path:
            return {"success": False, "error": "mtkclient not found"}
        cmd = [self._python, str(self._mtk_path)] + list(args)
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
            if command == "handshake":
                resp = self._transport.handshake()
                ok = "error" not in resp
                return AdapterResult(success=ok, command=command, stdout=str(resp))
            elif command == "send_da":
                if not args:
                    return AdapterResult(success=False, command=command, stderr="Missing DA path")
                ok = self._transport.send_da(args[0])
                return AdapterResult(success=ok, command=f"{command} {args[0]}")
            elif command == "jump_da":
                ok = self._transport.jump_da()
                return AdapterResult(success=ok, command=command)
            elif command == "flash_partition":
                if len(args) < 2:
                    return AdapterResult(success=False, command=command, stderr="Need partition and image")
                ok = self._transport.flash_partition(args[0], args[1])
                return AdapterResult(success=ok, command=f"{command} {args[0]}")
            elif command == "reset":
                ok = self._transport.reset()
                return AdapterResult(success=ok, command=command)
            else:
                return AdapterResult(success=False, command=command, stderr=f"Unknown transport command: {command}")
        except Exception as e:
            return AdapterResult(success=False, command=command, stderr=str(e))

    def list_devices(self) -> list[dict[str, Any]]:
        if self._has_pyusb:
            try:
                from zenith.adapters.usb_transport import BromUsbTransport
                t = BromUsbTransport()
                serial = t.detect()
                if serial is not None:
                    return [{"serial": serial, "vid": "0x0E8D", "status": "detected"}]
            except Exception:
                pass
        return [{"status": "available", "tool": "mtkclient"}] if self._available else []

    def run(self, *args: str, timeout: int = 120) -> AdapterResult:
        if not args:
            return AdapterResult(success=False, command="mtk", stderr="No command")
        cmd = args[0]
        transport_commands = {"handshake", "send_da", "jump_da", "flash_partition", "reset"}
        if cmd in transport_commands:
            return self._run_transport(cmd, *args[1:], timeout=timeout)
        r = self._run(*args, timeout=timeout)
        return AdapterResult(success=r["success"], command=f"mtk {' '.join(args)}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def payload(self) -> AdapterResult:
        logger.warning("MTK BROM bypass payload injection")
        r = self._run("payload", timeout=60)
        self._authenticated = r["success"]
        return AdapterResult(success=r["success"], command="mtk payload",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def printgpt(self) -> AdapterResult:
        r = self._run("printgpt")
        return AdapterResult(success=r["success"], command="mtk printgpt",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def dump_partition(self, partition: str, output: str) -> AdapterResult:
        logger.warning(f"MTK DUMP: {partition} -> {output}")
        r = self._run("r", f"--partition={partition}", f"--outfilename={output}", timeout=300)
        return AdapterResult(success=r["success"], command=f"mtk dump {partition}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def flash_partition(self, partition: str, image: str) -> AdapterResult:
        if not Path(image).exists():
            return AdapterResult(success=False, command=f"mtk flash {partition}", stderr=f"Image not found: {image}")
        if self._transport is not None:
            try:
                ok = self._transport.flash_partition(partition, image)
                return AdapterResult(success=ok, command=f"mtk flash {partition} (transport)",
                                    stdout="OK" if ok else "")
            except Exception:
                pass
        logger.warning(f"MTK FLASH: {image} -> {partition}")
        r = self._run("w", f"--partition={partition}", f"--sid={image}", timeout=300)
        return AdapterResult(success=r["success"], command=f"mtk flash {partition}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def erase_partition(self, partition: str) -> AdapterResult:
        logger.warning(f"MTK ERASE: {partition}")
        r = self._run("e", f"--partition={partition}")
        return AdapterResult(success=r["success"], command=f"mtk erase {partition}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def erase_multiple(self, partitions: list[str]) -> AdapterResult:
        parts_str = ",".join(partitions)
        logger.warning(f"MTK ERASE: {parts_str}")
        r = self._run("e", f"--partition={parts_str}")
        return AdapterResult(success=r["success"], command=f"mtk erase [{parts_str}]",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def handshake(self) -> AdapterResult:
        if self._transport is not None:
            try:
                resp = self._transport.handshake()
                ok = "error" not in resp
                return AdapterResult(success=ok, command="brom handshake (transport)", stdout=str(resp))
            except Exception:
                pass
        r = self._run("brom", "--test-point", timeout=60)
        return AdapterResult(success=r["success"], command="mtk brom handshake",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def bypass_sec_cfg(self) -> AdapterResult:
        r = self._run("seccfg", "unlock")
        return AdapterResult(success=r["success"], command="mtk seccfg unlock",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

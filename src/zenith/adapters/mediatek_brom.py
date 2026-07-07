"""MediaTek BROM Adapter — Boot ROM mode via mtkclient.

Wraps bkerler/mtkclient for BROM operations.
USB VID: 0E8D. Supports payload bypass, dump/flash/erase partitions.
"""

from __future__ import annotations

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
        self._python = "python"
        self._available = False
        self._authenticated = False
        self._init()

    def _init(self) -> None:
        self._mtk_path = self._find_mtk()
        self._available = self._mtk_path is not None
        if self._available:
            logger.info(f"MTK adapter: {self._mtk_path}")

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

    def _run(self, *args: str, timeout: int = 120) -> dict[str, Any]:
        if not self._available:
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

    def list_devices(self) -> list[dict[str, Any]]:
        return [{"status": "available", "tool": "mtkclient"}] if self._available else []

    def run(self, *args: str, timeout: int = 120) -> AdapterResult:
        r = self._run(*args, timeout=timeout)
        return AdapterResult(success=r["success"], command=f"mtk {' '.join(args)}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def payload(self) -> AdapterResult:
        """BROM bypass — inject payload to disable DA authentication."""
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
        logger.warning(f"MTK DUMP: {partition} → {output}")
        r = self._run("r", f"--partition={partition}", f"--outfilename={output}", timeout=300)
        return AdapterResult(success=r["success"], command=f"mtk dump {partition}",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def flash_partition(self, partition: str, image: str) -> AdapterResult:
        if not Path(image).exists():
            return AdapterResult(success=False, command=f"mtk flash {partition}", stderr=f"Image not found: {image}")
        logger.warning(f"MTK FLASH: {image} → {partition}")
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
        r = self._run("brom", "--test-point", timeout=60)
        return AdapterResult(success=r["success"], command="mtk brom handshake",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

    def bypass_sec_cfg(self) -> AdapterResult:
        r = self._run("seccfg", "unlock")
        return AdapterResult(success=r["success"], command="mtk seccfg unlock",
                            stdout=r.get("stdout", ""), stderr=r.get("stderr", r.get("error", "")))

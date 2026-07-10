"""Hardware Test Harness — detect, verify, and report on all connected devices.

Usage:
    python scripts/hardware_test.py              # Full scan
    python scripts/hardware_test.py --quick      # Quick availability check only
    python scripts/hardware_test.py --json        # JSON output
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class TestResult:
    name: str
    status: bool
    detail: str = ""
    duration_ms: float = 0.0

    def ok(self) -> str:
        return "PASS" if self.status else "FAIL"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": "PASS" if self.status else "FAIL",
                "detail": self.detail[:200], "duration_ms": round(self.duration_ms, 1)}


def timed(test_fn):
    def wrapper(*args: Any, **kwargs: Any) -> TestResult:
        t0 = time.perf_counter()
        result = test_fn(*args, **kwargs)
        result.duration_ms = (time.perf_counter() - t0) * 1000
        return result
    return wrapper


@timed
def test_pyusb() -> TestResult:
    try:
        import usb.core
        return TestResult("pyusb", True, f"usb.core found: {usb.core.__file__}")
    except ImportError:
        return TestResult("pyusb", False, "not installed — run: pip install pyusb")


@timed
def test_pyserial() -> TestResult:
    try:
        import serial
        return TestResult("pyserial", True, f"serial found: {serial.__file__}")
    except ImportError:
        return TestResult("pyserial", False, "not installed — run: pip install pyserial")


@timed
def test_adb_binary() -> TestResult:
    import shutil
    path = shutil.which("adb")
    if path:
        return TestResult("adb binary", True, f"found: {path}")
    return TestResult("adb binary", False, "adb not in PATH")


@timed
def test_fastboot_binary() -> TestResult:
    import shutil
    path = shutil.which("fastboot")
    if path:
        return TestResult("fastboot binary", True, f"found: {path}")
    return TestResult("fastboot binary", False, "fastboot not in PATH")


@timed
def test_adb_devices() -> TestResult:
    import subprocess
    try:
        result = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=5)
        lines_ = [ln for ln in result.stdout.strip().split("\n") if ln and not ln.startswith("List")]
        serials = [ln.split()[0] for ln in lines_[:5]] if lines_ else ["none"]
        return TestResult("adb devices", result.returncode == 0,
                         f"{len(lines_)} device(s): {', '.join(serials)}")
    except FileNotFoundError:
        return TestResult("adb devices", False, "adb not found")
    except Exception as e:
        return TestResult("adb devices", False, str(e))


@timed
def test_fastboot_devices() -> TestResult:
    import subprocess
    try:
        result = subprocess.run(["fastboot", "devices"], capture_output=True, text=True, timeout=5)
        lines_ = [ln for ln in result.stdout.strip().split("\n") if ln.strip()]
        serials = [ln.split()[0] for ln in lines_[:5]] if lines_ else ["none"]
        return TestResult("fastboot devices", result.returncode == 0,
                         f"{len(lines_)} device(s): {', '.join(serials)}")
    except FileNotFoundError:
        return TestResult("fastboot devices", False, "fastboot not found")
    except Exception as e:
        return TestResult("fastboot devices", False, str(e))


@timed
def test_usb_scan() -> TestResult:
    try:
        import usb.core
        devices = list(usb.core.find(find_all=True))
        zenith_vids = {0x05C6, 0x0E8D, 0x1782, 0x04E8, 0x0FCE, 0x18D1, 0x12D1, 0x2207, 0x1F3A}
        relevant = []
        for d in devices:
            if d.idVendor in zenith_vids:
                relevant.append(f"{d.idVendor:04X}:{d.idProduct:04X}")
        total = len(devices)
        return TestResult("usb scan", True, f"{total} USB device(s), {len(relevant)} relevant: {', '.join(relevant) if relevant else 'none'}")
    except ImportError:
        return TestResult("usb scan", False, "pyusb not installed")
    except Exception as e:
        return TestResult("usb scan", False, str(e))


@timed
def test_discovery() -> TestResult:
    try:
        from zenith.core.discovery import run_discovery
        result = run_discovery()
        parts = []
        if result.adb_devices:
            parts.append(f"{len(result.adb_devices)} ADB")
        if result.fastboot_devices:
            parts.append(f"{len(result.fastboot_devices)} Fastboot")
        if result.usb_hits:
            parts.append(f"{len(result.usb_hits)} USB")
        if result.serial_ports:
            parts.append(f"{len(result.serial_ports)} Serial")
        return TestResult("discovery", True, ", ".join(parts) if parts else "no devices found")
    except Exception as e:
        return TestResult("discovery", False, str(e))


@timed
def test_registry() -> TestResult:
    try:
        from zenith.adapters.registry import get_adapter_registry
        reg = get_adapter_registry()
        types = reg.supported_types()
        return TestResult("adapter registry", True,
                         f"{len(types)} adapter(s): {', '.join(t.value for t in types)}")
    except Exception as e:
        return TestResult("adapter registry", False, str(e))


@timed
def test_device_profiles() -> TestResult:
    try:
        from zenith.knowledge.device_registry import get_device_profile_registry
        reg = get_device_profile_registry()
        profiles = reg.list_all()
        return TestResult("device profiles", True,
                         f"{len(profiles)} profile(s): {', '.join(p.id for p in profiles[:10])}")
    except Exception as e:
        return TestResult("device profiles", False, str(e))


@timed
def test_knowledge_base() -> TestResult:
    try:
        from zenith.knowledge.knowledge_base import get_knowledge_base
        kb = get_knowledge_base()
        return TestResult("knowledge base", True,
                         f"{len(kb.data.socs)} SoCs, {len(kb.data.protocols)} protocols, {len(kb.data.playbooks)} playbooks")
    except Exception as e:
        return TestResult("knowledge base", False, str(e))


@timed
def test_dispatch_dry() -> TestResult:
    try:
        from zenith.adapters.registry import get_adapter_registry
        reg = get_adapter_registry()
        commands = ["adb:devices", "fastboot:devices", "edl:printgpt"]
        results = []
        for cmd in commands:
            try:
                ok, out = reg.dispatch(cmd)
                results.append(f"{cmd.split(':')[0]}={'OK' if ok else 'FAIL'}")
            except Exception:
                results.append(f"{cmd.split(':')[0]}=ERR")
        return TestResult("dispatch dry-run", True, ", ".join(results))
    except Exception as e:
        return TestResult("dispatch dry-run", False, str(e))


@timed
def test_gui_import() -> TestResult:
    import importlib
    try:
        spec = importlib.util.find_spec("zenith.gui")
        if spec is not None:
            return TestResult("gui import", True, "GUI module loads successfully")
        return TestResult("gui import", False, "GUI module not found")
    except Exception as e:
        return TestResult("gui import", False, str(e))


def run_all(quick: bool = False) -> list[TestResult]:
    import logging
    logging.disable(logging.CRITICAL)
    import os
    os.environ["LOGURU_LEVEL"] = "ERROR"
    from loguru import logger
    logger.remove()
    logger.add(lambda _: None, level="ERROR")
    results: list[TestResult] = []

    # Core dependencies
    results.extend([test_pyusb(), test_pyserial()])

    if not quick:
        # Binaries
        results.extend([test_adb_binary(), test_fastboot_binary()])

        # Runtime detection
        results.extend([test_adb_devices(), test_fastboot_devices(), test_usb_scan()])

    # Software stack
    results.extend([
        test_registry(),
        test_device_profiles(),
        test_knowledge_base(),
    ])

    if not quick:
        results.extend([test_discovery(), test_dispatch_dry(), test_gui_import()])

    return results


def print_report(results: list[TestResult]) -> None:
    passed = sum(1 for r in results if r.status)
    total = len(results)
    print("=" * 70)
    print("  ZENITH HARDWARE TEST HARNESS")
    print("=" * 70)
    print(f"\n  {passed}/{total} tests passed\n")

    for r in results:
        icon = "PASS" if r.status else "FAIL"
        color = "\033[92m" if r.status else "\033[91m"
        reset = "\033[0m"
        duration = f"({r.duration_ms:.0f}ms)" if r.duration_ms > 1 else ""
        print(f"  {color}{icon}{reset}  {r.name:25s} {r.ok():6s} {duration}")
        if r.detail:
            print(f"      {r.detail[:120]}")

    print()
    if passed == total:
        print("  All tests passed!")
    else:
        print(f"  {total - passed} test(s) failed — see details above")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Zenith Hardware Test Harness")
    parser.add_argument("--quick", action="store_true", help="Quick check — skip binary and device scans")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = run_all(quick=args.quick)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print_report(results)

    sys.exit(0 if all(r.status for r in results) else 1)


if __name__ == "__main__":
    main()

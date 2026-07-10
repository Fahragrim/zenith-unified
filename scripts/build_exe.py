"""Build Zenith Unified as a Windows .exe via PyInstaller.

Usage:
    python scripts/build_exe.py              # CLI only
    python scripts/build_exe.py --gui         # GUI + CLI
    python scripts/build_exe.py --clean       # Clean build dirs first
    python scripts/build_exe.py --no-upx      # Disable UPX compression

Requires Python >= 3.10. Auto-detects py -3.12 or python3 on PATH.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "zenith.spec"


def _find_python() -> str:
    """Find a Python >= 3.10 executable."""
    candidates = ["py -3.12", "py -3.11", "py -3.10", "python3", "python"]
    for c in candidates:
        try:
            parts = c.split()
            ver = subprocess.run(
                parts + ["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True, text=True, timeout=5,
            )
            if ver.returncode == 0:
                major, minor = ver.stdout.strip().split(".")
                if int(major) >= 3 and int(minor) >= 10:
                    return c
        except Exception:
            continue
    print("ERROR: No Python >= 3.10 found. Install Python 3.10+ and try again.")
    sys.exit(1)


def clean() -> None:
    for d in [DIST, BUILD]:
        if d.exists():
            shutil.rmtree(d)
    for spec_bak in ROOT.glob("*.spec.bak"):
        spec_bak.unlink()
    for warn in ROOT.glob("warn-*.txt"):
        warn.unlink()
    for xref in ROOT.glob("xref-*.html"):
        xref.unlink()
    print("Cleaned build artifacts")


def build(gui: bool = False, upx: bool = True, clean_first: bool = False) -> None:
    if clean_first:
        clean()

    if not SPEC.exists():
        print(f"Error: {SPEC} not found")
        sys.exit(1)

    python = _find_python()
    pyinstaller = f"{python} -m PyInstaller"
    cmd = pyinstaller.split() + [str(SPEC)]
    if not upx:
        cmd.append("--noconfirm")
    if gui:
        cmd.append("--")
        cmd.append("--gui")

    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(ROOT))

    print("\nBuild artifacts:")
    for f in sorted(DIST.iterdir()):
        if f.suffix in (".exe",):
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {f.name}  ({size_mb:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Zenith .exe via PyInstaller")
    parser.add_argument("--gui", action="store_true", help="Build GUI version too")
    parser.add_argument("--clean", action="store_true", help="Clean build dirs first")
    parser.add_argument("--no-upx", action="store_true", help="Disable UPX compression")
    args = parser.parse_args()

    build(gui=args.gui, upx=not args.no_upx, clean_first=args.clean)


if __name__ == "__main__":
    main()

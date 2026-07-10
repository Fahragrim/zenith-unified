"""Sony Xperia Flash Helper — Flash mode operations via SonyS1Adapter.

Usage:
    py -3.12 scripts/sony_flash.py detect              # Check for Sony device
    py -3.12 scripts/sony_flash.py list <firmware_dir>  # List .sin files
    py -3.12 scripts/sony_flash.py flash <firmware_dir>  # Flash firmware
    py -3.12 scripts/sony_flash.py backup-ta <out_dir>   # Backup TA partition
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zenith.adapters.sony_s1 import SonyS1Adapter


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    adapter = SonyS1Adapter()

    if cmd == "detect":
        result = adapter.detect()
        print(f"Detect: {'OK' if result.success else 'FAIL'}")
        print(result.stdout or result.stderr)

    elif cmd == "list":
        if len(sys.argv) < 3:
            print("Usage: sony_flash.py list <firmware_dir>")
            return
        files = adapter.list_firmware(sys.argv[2])
        if not files:
            print("No firmware files found.")
        for f in files:
            size_kb = f["size_bytes"] / 1024
            print(f"  {f['type']:8s} {f['filename']:40s} {size_kb:8.1f} KB")

    elif cmd == "flash":
        if len(sys.argv) < 3:
            print("Usage: sony_flash.py flash <firmware_dir>")
            return
        fw_dir = sys.argv[2]
        files = adapter.list_firmware(fw_dir)
        print(f"Found {len(files)} firmware files in {fw_dir}")
        confirm = input("Continue with flash? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return
        result = adapter.flash(fw_dir)
        print(f"Flash: {'OK' if result.success else 'FAIL'}")
        print(result.stdout or result.stderr)

    elif cmd == "backup-ta":
        out = sys.argv[2] if len(sys.argv) > 2 else "ta_backup"
        result = adapter.backup_ta(out)
        print(f"TA backup: {'OK' if result.success else 'FAIL'}")
        print(result.stdout or result.stderr)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()

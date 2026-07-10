"""SPRD BootROM Driver Installer for Windows.

Detects Nokia C32 / Unisoc SPRD device in BootROM mode (VID 1782, PID 4D00)
and guides installation of the WinUSB driver required for pyusb bulk transfers.

Usage:
    py -3.12 scripts/install_sprd_driver.py           # Auto-detect + guide
    py -3.12 scripts/install_sprd_driver.py --check   # Check only
    py -3.12 scripts/install_sprd_driver.py --zadig   # Open Zadig download
"""

from __future__ import annotations

import sys
import webbrowser

SPRD_VID = 0x1782
SPRD_PID = 0x4D00


def detect_device() -> bool:
    try:
        import usb.core
        dev = usb.core.find(idVendor=SPRD_VID, idProduct=SPRD_PID)
        if dev is not None:
            print(f"SPRD BootROM device found: bus={dev.bus} address={dev.address}")
            return True
        print(f"No SPRD device found (VID {SPRD_VID:04X}, PID {SPRD_PID:04X})")
        print("Is the Nokia C32 connected in BootROM mode?")
        print("Try: Hold Vol buttons while inserting USB cable")
        return False
    except ImportError:
        print("pyusb not installed — run: pip install pyusb")
        return False
    except Exception as e:
        print(f"USB scan error: {e}")
        return False


def check_driver() -> str | None:
    try:
        import usb.core
        dev = usb.core.find(idVendor=SPRD_VID, idProduct=SPRD_PID)
        if dev is None:
            return None
        try:
            cfg = dev.get_active_configuration()
            for iface in cfg:
                return f"Interface {iface.bInterfaceNumber}: class={iface.bInterfaceClass}"
        except Exception:
            return "WinUSB driver needed — pyusb cannot access the device"
    except Exception:
        return "Driver check failed"
    return None


def guide_zadig() -> None:
    print()
    print("=" * 60)
    print("  SPRD BootROM — WinUSB Driver Installation")
    print("=" * 60)
    print()
    print("  Step 1: Download Zadig from:")
    print("    https://zadig.akeo.ie/")
    print()
    print("  Step 2: Open Zadig.exe as Administrator")
    print()
    print("  Step 3: Options -> List All Devices")
    print()
    print("  Step 4: Select from the dropdown:")
    print('    "SPRD SCI-USB" or "SPRD U2S Diag Port"')
    print("    (VID 1782, PID 4D00)")
    print()
    print("  Step 5: In the right column, select 'WinUSB'")
    print()
    print("  Step 6: Click 'Install Driver' (or 'Replace Driver')")
    print()
    print("  Step 7: Wait for installation to complete")
    print()
    print("  Step 8: Run this script again to verify:")
    print("    py -3.12 scripts/install_sprd_driver.py --check")
    print()
    print("  Alternative: Use pnputil:")
    print("    pnputil /add-driver drivers\\sprd_winusb.inf /install")
    print()
    print("=" * 60)


def main() -> None:
    if "--check" in sys.argv:
        if detect_device():
            status = check_driver()
            if status:
                print(f"Driver status: {status}")
            else:
                print("Device accessible — driver OK")
        return

    if "--zadig" in sys.argv:
        webbrowser.open("https://zadig.akeo.ie/")
        print("Opened Zadig download page in browser")
        return

    if not detect_device():
        print()
        print("Troubleshooting tips:")
        print("  1. Ensure Nokia C32 is powered off")
        print("  2. Short test point to GND while connecting USB")
        print("  3. Or hold both Vol buttons while connecting USB")
        print("  4. Check Windows Device Manager for 'SPRD SCI-USB'")
        sys.exit(1)

    status = check_driver()
    if status and "WinUSB" in status:
        print(f"Device found but: {status}")
        guide_zadig()
        sys.exit(1)
    elif status:
        print(f"Device found: {status}")
        print("SPRD adapter should work correctly.")
    else:
        print("Device is accessible via pyusb — driver OK!")
        print("You can now run UnisocSPRDAdapter operations.")


if __name__ == "__main__":
    main()

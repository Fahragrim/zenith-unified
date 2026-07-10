# Hardware Setup Guide

How to connect real devices to Zenith Unified with USB access.

## Windows: WinUSB / libusb via Zadig

PyUSB needs a WinUSB driver for bulk transfers to EDL/BROM/SPRD devices.

1. Download **Zadig** from https://zadig.akeo.ie/
2. Run `zadig.exe` **as Administrator**
3. **Options → List All Devices**
4. Find your device in the dropdown:

   | Device | VID | PID | Look for in Zadig |
   |--------|-----|-----|-------------------|
   | Qualcomm EDL | `05C6` | `9008` | "Qualcomm HS-USB QDLoader 9008" |
   | MediaTek BROM | `0E8D` | `2000` | "MediaTek Preloader" |
   | **Nokia C32 / Unisoc SPRD** | `1782` | `4D00` | "SPRD SCI-USB" or "Unisoc BootROM" |
   | Samsung Download | `04E8` | `685D` | "Samsung Mobile USB" |

5. Select **WinUSB** as the driver (right column)
6. Click **Install Driver** (or Replace Driver)
7. Verify: `py -3.12 scripts/install_sprd_driver.py --check`

> **Note:** After driver replacement, the device will no longer appear as a COM port
> in Device Manager. Run `scripts\hack_back_com_port.bat` to restore if needed.

### Automated check

```bash
py -3.12 scripts/install_sprd_driver.py          # Detect + guide
py -3.12 scripts/install_sprd_driver.py --check  # Quick check
py -3.12 scripts/install_sprd_driver.py --zadig  # Open Zadig download
```

## Linux: udev Rules

Create `/etc/udev/rules.d/51-zenith.rules`:

```
# Qualcomm EDL
SUBSYSTEM=="usb", ATTR{idVendor}=="05c6", ATTR{idProduct}=="9008", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="05c6", ATTR{idProduct}=="900e", MODE="0666"

# MediaTek BROM
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", MODE="0666"

# Unisoc SPRD BootROM
SUBSYSTEM=="usb", ATTR{idVendor}=="1782", ATTR{idProduct}=="4d00", MODE="0666"

# Sony Flashmode
SUBSYSTEM=="usb", ATTR{idVendor}=="0fce", ATTR{idProduct}=="ade5", MODE="0666"

# Samsung Download Mode
SUBSYSTEM=="usb", ATTR{idVendor}=="04e8", ATTR{idProduct}=="685d", MODE="0666"

# Apple DFU
SUBSYSTEM=="usb", ATTR{idVendor}=="05ac", ATTR{idProduct}=="1227", MODE="0666"
```

Then reload:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Test Your Setup

```bash
# Quick hardware test
py -3.12 scripts/hardware_test.py

# Discover connected devices
zenith discover

# Check specific adapter (e.g. SPRD)
py -3.12 scripts/check_sprd_device.py
```

## Supported Devices (20 profiles)

| Manufacturer | Model | SoC | Mode |
|-------------|-------|-----|------|
| Google | Pixel 7 | Tensor G2 | Fastboot, EDL, ADB |
| Google | Pixel 6a | Tensor | Fastboot, EDL, ADB |
| Google | Pixel 4a | SD730G | Fastboot, EDL, ADB |
| Samsung | Galaxy S23 | SD8 Gen 2 | Odin, EDL, ADB |
| Samsung | Galaxy S20 (E) | Exynos 990 | Odin, Fastboot, ADB |
| Samsung | Galaxy A52 | SD720G | EDL, Odin, ADB |
| Samsung | Note 20 Ultra | Exynos 990 | Odin, ADB |
| Sony | Xperia XZ2 | SD845 | Flashmode, EDL, ADB |
| Sony | Xperia 1 III | SD888 | Flashmode, EDL, ADB |
| OnePlus | 9 Pro | SD888 | EDL, Fastboot, ADB |
| OnePlus | 7T | SD855+ | EDL, Fastboot, ADB |
| OnePlus | Nord 2 | Dimensity 1200 | BROM, Fastboot, ADB |
| Xiaomi | Mi 11 | SD888 | EDL, Fastboot, ADB |
| Xiaomi | Poco F3 | SD870 | EDL, Fastboot, ADB |
| Xiaomi | Redmi Note 12 | Helio G85 | BROM, Fastboot, ADB |
| Nokia | C32 | SC9863A1 | SPRD BootROM, Diag, ADB |
| Nokia | G21 | T606 | SPRD BootROM, ADB |
| Motorola | Moto G51 | SD480+ | EDL, Fastboot, ADB |
| Huawei | P30 | Kirin 980 | Fastboot, ADB |
| LG | G8 ThinQ | SD855 | EDL, Download, ADB |
| Fairphone | 4 | SD750G | EDL, Fastboot, ADB |

## Troubleshooting

**"No module named 'usb'"**
```bash
pip install pyusb
```

**"Access denied" on Linux**
```bash
sudo udevadm control --reload-rules
# Or run as root temporarily
sudo zenith discover
```

**Device not detected by pyusb but visible in Device Manager**
→ Install WinUSB driver via Zadig (see above)

**"Operation not supported or unimplemented on this platform"**
→ The device needs a WinUSB/libusb driver. Windows default driver only exposes a COM port, not bulk endpoints.

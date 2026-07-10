"""Check SPRD/Nokia C32 USB device status — read-only diagnostic."""

import usb.core
import usb.util

dev = usb.core.find(idVendor=0x1782, idProduct=0x4D00)
if dev is None:
    print("No SPRD device found (VID 1782, PID 4D00)")
    print("Is the Nokia C32 connected in BootROM mode?")
    raise SystemExit(1)

print(f"SPRD BootROM Device: bus={dev.bus} address={dev.address}")
try:
    manu = usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else "N/A"
    prod = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "N/A"
    serial = usb.util.get_string(dev, dev.iSerialNumber) if dev.iSerialNumber else "N/A"
    print(f"  Manufacturer: {manu}")
    print(f"  Product:      {prod}")
    print(f"  Serial:       {serial}")
except Exception as e:
    print(f"  String descriptors: {e}")

try:
    active = dev.is_kernel_driver_active(0)
    print(f"  Kernel driver (iface 0): {active}")
except Exception as e:
    print(f"  Kernel driver check: {e}")

try:
    cfg = dev.get_active_configuration()
    print(f"  Configuration: {cfg.bConfigurationValue}")
    for iface in cfg:
        print(f"  Interface {iface.bInterfaceNumber}: "
              f"class={iface.bInterfaceClass} subclass={iface.bInterfaceSubClass}")
        for ep in iface:
            addr = "IN" if ep.bEndpointAddress & 0x80 else "OUT"
            print(f"    EP 0x{ep.bEndpointAddress:02X} ({addr}) "
                  f"maxPkt={ep.wMaxPacketSize}")
except Exception as e:
    print(f"  Config read error: {e}")

print()
print("SPRD BootROM transport requires WinUSB/libusb driver.")
print("To install: 1. Download Zadig (https://zadig.akeo.ie)")
print("            2. Options -> List All Devices")
print("            3. Select 'SPRD SCI-USB' or '1782:4D00'")
print("            4. Install WinUSB driver")

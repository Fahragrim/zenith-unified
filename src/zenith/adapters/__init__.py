"""Adapter module exports — all 13 adapters."""

from zenith.adapters.adb import ADBAdapter
from zenith.adapters.allwinner_fel import AllwinnerFELAdapter
from zenith.adapters.apple_dfu import AppleDFUAdapter
from zenith.adapters.diag_at import DiagATAdapter
from zenith.adapters.fastboot import FastbootAdapter
from zenith.adapters.mediatek_brom import MediaTekBROMAdapter
from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.adapters.qualcomm_edl import QualcommEDLAdapter
from zenith.adapters.registry import AdapterRegistry, get_adapter_registry
from zenith.adapters.rockchip import RockchipAdapter
from zenith.adapters.samsung_odin import SamsungOdinAdapter
from zenith.adapters.sony_s1 import SonyS1Adapter
from zenith.adapters.uart import UARTAdapter
from zenith.adapters.unisoc_sprd import UnisocSPRDAdapter

__all__ = [
    "AdapterProtocol", "AdapterResult", "AdapterRegistry", "get_adapter_registry",
    "ADBAdapter", "FastbootAdapter",
    "AllwinnerFELAdapter", "AppleDFUAdapter", "DiagATAdapter",
    "MediaTekBROMAdapter", "QualcommEDLAdapter", "RockchipAdapter",
    "SamsungOdinAdapter", "SonyS1Adapter", "UARTAdapter", "UnisocSPRDAdapter",
]

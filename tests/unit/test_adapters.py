"""Unit tests for adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zenith.adapters.adb import ADBAdapter
from zenith.adapters.allwinner_fel import AllwinnerFELAdapter
from zenith.adapters.apple_dfu import AppleDFUAdapter
from zenith.adapters.diag_at import DiagATAdapter
from zenith.adapters.fastboot import FastbootAdapter
from zenith.adapters.mediatek_brom import MediaTekBROMAdapter
from zenith.adapters.protocol import AdapterProtocol, AdapterResult
from zenith.adapters.qualcomm_edl import QualcommEDLAdapter
from zenith.adapters.registry import AdapterRegistry
from zenith.adapters.rockchip import RockchipAdapter
from zenith.adapters.samsung_odin import SamsungOdinAdapter
from zenith.adapters.sony_s1 import SonyS1Adapter
from zenith.adapters.uart import UARTAdapter
from zenith.adapters.unisoc_sprd import UnisocSPRDAdapter
from zenith.core.device import DeviceType


class TestAdapterResult:
    def test_success(self) -> None:
        r = AdapterResult(success=True, command="adb devices", stdout="device")
        assert bool(r) is True

    def test_failure(self) -> None:
        r = AdapterResult(success=False, command="adb", stderr="error")
        assert bool(r) is False
        assert "FAIL" in str(r)


class TestAdapterRegistry:
    def test_register_and_create(self) -> None:
        reg = AdapterRegistry()
        reg.register(DeviceType.ADB, ADBAdapter)
        a = reg.create(DeviceType.ADB)
        assert isinstance(a, ADBAdapter)

    def test_unregistered_returns_none(self) -> None:
        reg = AdapterRegistry()
        assert reg.create(DeviceType.APPLE_DFU) is None

    def test_supported_types(self) -> None:
        reg = AdapterRegistry()
        reg.register(DeviceType.ADB, ADBAdapter)
        reg.register(DeviceType.FASTBOOT, FastbootAdapter)
        assert len(reg.supported_types()) == 2


class TestADBAdapter:
    def test_name(self) -> None:
        a = ADBAdapter()
        assert a.name == "adb"

    def test_connect(self) -> None:
        a = ADBAdapter()
        a._use_adbutils = False
        with patch("subprocess.run") as m:
            m.return_value = MagicMock(returncode=0, stdout="", stderr="")
            r = a.connect("SERIAL123")
            assert r.success is True
            assert a._active_serial == "SERIAL123"

    def test_disconnect(self) -> None:
        a = ADBAdapter()
        a._active_serial = "SERIAL123"
        a.disconnect()
        assert a._active_serial is None

    def test_shell(self) -> None:
        a = ADBAdapter()
        a._use_adbutils = False
        with patch("subprocess.run") as m:
            m.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            r = a.shell("echo test")
            assert r.success is True

    def test_reboot(self) -> None:
        a = ADBAdapter()
        a._use_adbutils = False
        with patch("subprocess.run") as m:
            m.return_value = MagicMock(returncode=0, stdout="", stderr="")
            r = a.reboot("bootloader")
            assert r.success is True


class TestFastbootAdapter:
    def test_name(self) -> None:
        a = FastbootAdapter()
        assert a.name == "fastboot"

    def test_getvar(self) -> None:
        a = FastbootAdapter()
        with patch.object(a, "_run_raw") as m:
            m.return_value = MagicMock(returncode=0, stdout="product: tokay\n", stderr="")
            r = a.getvar("product")
            assert r.success is True

    def test_oem_unlock(self) -> None:
        a = FastbootAdapter()
        with patch.object(a, "_run_raw") as m:
            m.return_value = MagicMock(returncode=0, stdout="OKAY", stderr="")
            r = a.oem_unlock()
            assert r.success is True

    def test_fuzz(self) -> None:
        a = FastbootAdapter()
        with patch.object(a, "_run_raw") as m:
            m.return_value = MagicMock(returncode=0, stdout="", stderr="unknown command")
            results = a.fuzz_oem_commands()
            assert len(results) >= 15


class TestAllAdaptersPresent:
    ALL = [
        (QualcommEDLAdapter, "qualcomm_edl"),
        (MediaTekBROMAdapter, "mediatek_brom"),
        (UnisocSPRDAdapter, "unisoc_sprd"),
        (SamsungOdinAdapter, "samsung_odin"),
        (SonyS1Adapter, "sony_s1"),
        (DiagATAdapter, "diag_at"),
        (UARTAdapter, "uart"),
        (AppleDFUAdapter, "apple_dfu"),
        (RockchipAdapter, "rockchip"),
        (AllwinnerFELAdapter, "allwinner_fel"),
    ]

    @pytest.mark.parametrize("cls,expected_name", ALL)
    def test_adapter_metadata(self, cls, expected_name) -> None:
        a = cls()
        assert a.name == expected_name

    def test_edl_methods(self) -> None:
        a = QualcommEDLAdapter()
        for method in ["printgpt", "sahara_ping", "flash_partition"]:
            assert hasattr(a, method)

    def test_mtk_methods(self) -> None:
        a = MediaTekBROMAdapter()
        for method in ["payload", "handshake", "erase_partition"]:
            assert hasattr(a, method)

    def test_diag_at_methods(self) -> None:
        a = DiagATAdapter()
        assert hasattr(a, "send_at")
        assert hasattr(a, "panic_inject")
        assert hasattr(a, "scan_ports")

    def test_full_registry(self) -> None:
        reg = AdapterRegistry()
        types_to_register = [
            (DeviceType.QUALCOMM_EDL, QualcommEDLAdapter),
            (DeviceType.MTK_BROM, MediaTekBROMAdapter),
            (DeviceType.UNISOC_SPD, UnisocSPRDAdapter),
            (DeviceType.SAMSUNG_ODIN, SamsungOdinAdapter),
            (DeviceType.DIAG, DiagATAdapter),
            (DeviceType.UART, UARTAdapter),
            (DeviceType.APPLE_DFU, AppleDFUAdapter),
            (DeviceType.ROCKCHIP_MASKROM, RockchipAdapter),
            (DeviceType.ALLWINNER_FEL, AllwinnerFELAdapter),
        ]
        for dt, cls in types_to_register:
            reg.register(dt, cls)
        assert len(reg.supported_types()) == len(types_to_register)

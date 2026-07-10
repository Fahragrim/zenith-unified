"""Hardware-mocked integration tests for adapter USB transport layer.

Mocks USB packets on the register level (Sahara/Firehose XML, BROM handshake)
to test the full flash and repair chain without physical devices.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typing import Any

import pytest

from zenith.adapters.protocol import AdapterResult
from zenith.adapters.qualcomm_edl import QualcommEDLAdapter
from zenith.adapters.registry import AdapterRegistry, get_adapter_registry
from zenith.core.device import DeviceType


# ─── Mock USB Device ─────────────────────────────────────────────────────────


class MockUsbDevice:
    """Simulates a usb.core.Device for testing transport layers."""

    def __init__(self) -> None:
        self.bus = 1
        self.address = 1
        self.idVendor = 0x05C6
        self.idProduct = 0x9008
        self.iSerialNumber = 0
        self._cfg = MagicMock()
        self._written: list[bytes] = []

    def is_kernel_driver_active(self, _iface: int) -> bool:
        return False

    def detach_kernel_driver(self, _iface: int) -> None:
        pass

    def set_configuration(self) -> None:
        pass

    def get_active_configuration(self) -> MagicMock:
        return self._cfg

    def write(self, ep: int, data: bytes, timeout: int = 5000) -> int:
        self._written.append(data)
        return len(data)

    def read(self, ep: int, length: int, timeout: int = 5000) -> bytes:
        # Return Sahara HELLO response (48 bytes)
        if length == 64:
            return bytes.fromhex(
                "020000003000000002000000000000000100000000000000"
                "000000000000000000000000000000000000000000000000"
            )
        # Firehose ACK: XML response containing response="ACK"
        if self._written and b"configure" in self._written[-1]:
            return b'<?xml version="1.0"?><data response="ACK">OK</data>'
        # Generic ACK
        return b"\x00" * length

    def ctrl_transfer(self, *args: Any, **kwargs: Any) -> None:
        pass


# ─── EDL Transport Mock Tests ────────────────────────────────────────────────


class TestEdlTransportMock:
    def test_detect_mock_device(self) -> None:
        with patch("usb.core.find", return_value=MockUsbDevice()):
            from zenith.adapters.usb_transport import EdlUsbTransport
            t = EdlUsbTransport()
            serial = t.detect()
            assert serial is not None
            assert "05C6" in serial

    def test_sahara_hello_mock(self) -> None:
        with patch("usb.core.find", return_value=MockUsbDevice()):
            from zenith.adapters.usb_transport import EdlUsbTransport
            t = EdlUsbTransport()
            t.detect()
            resp = t.sahara_hello()
            assert "error" not in resp
            assert resp.get("mode") is not None

    def test_firehose_connect_mock(self) -> None:
        with patch("usb.core.find", return_value=MockUsbDevice()):
            from zenith.adapters.usb_transport import EdlUsbTransport
            t = EdlUsbTransport()
            t.detect()
            ok = t.firehose_connect()
            assert ok is True

    def test_close_transport(self) -> None:
        with patch("usb.core.find", return_value=MockUsbDevice()):
            from zenith.adapters.usb_transport import EdlUsbTransport
            t = EdlUsbTransport()
            t.detect()
            t.close()
            assert t._dev is None


# ─── BROM Transport Mock Tests ───────────────────────────────────────────────


class MockBromUsbDevice:
    def __init__(self) -> None:
        self.bus = 1
        self.address = 1
        self.idVendor = 0x0E8D
        self.idProduct = 0x2000
        self.iSerialNumber = 0
        self._written: list[bytes] = []

    def is_kernel_driver_active(self, _iface: int) -> bool:
        return False

    def detach_kernel_driver(self, _iface: int) -> None:
        pass

    def set_configuration(self) -> None:
        pass

    def write(self, ep: int, data: bytes, timeout: int = 5000) -> int:
        self._written.append(data)
        return len(data)

    def read(self, ep: int, length: int, timeout: int = 5000) -> bytes:
        return b"\x00" * 64

    def ctrl_transfer(self, *args: Any, **kwargs: Any) -> None:
        pass


class TestBromTransportMock:
    def test_detect_brom_mock(self) -> None:
        with patch("usb.core.find", return_value=MockBromUsbDevice()):
            from zenith.adapters.usb_transport import BromUsbTransport
            t = BromUsbTransport()
            serial = t.detect()
            assert serial is not None
            assert "0E8D" in serial

    def test_brom_handshake_mock(self) -> None:
        with patch("usb.core.find", return_value=MockBromUsbDevice()):
            from zenith.adapters.usb_transport import BromUsbTransport
            t = BromUsbTransport()
            t.detect()
            resp = t.handshake()
            assert "error" not in resp

    def test_brom_reset_mock(self) -> None:
        with patch("usb.core.find", return_value=MockBromUsbDevice()):
            from zenith.adapters.usb_transport import BromUsbTransport
            t = BromUsbTransport()
            t.detect()
            ok = t.reset()
            assert ok is True


# ─── Adapter Dispatch Mock Tests ─────────────────────────────────────────────


class TestAdapterDispatchMock:
    def test_registry_auto_register(self) -> None:
        reg = get_adapter_registry()
        types = reg.supported_types()
        assert DeviceType.ADB in types
        assert DeviceType.FASTBOOT in types
        assert DeviceType.QUALCOMM_EDL in types
        assert DeviceType.MTK_BROM in types

    def test_qualcomm_adapter_connect_mock(self) -> None:
        with patch("usb.core.find", return_value=MockUsbDevice()):
            adapter = QualcommEDLAdapter()
            assert adapter.is_available()
            result = adapter.connect()
            assert result.success is True

    def test_qualcomm_adapter_list_devices_mock(self) -> None:
        with patch("usb.core.find", return_value=MockUsbDevice()):
            adapter = QualcommEDLAdapter()
            devices = adapter.list_devices()
            assert len(devices) > 0
            assert "0x05C6" in devices[0].get("vid", "")

    def test_registry_create_adapter(self) -> None:
        reg = AdapterRegistry()
        reg.register(DeviceType.ADB, MagicMock)
        adapter = reg.create(DeviceType.ADB)
        assert adapter is not None

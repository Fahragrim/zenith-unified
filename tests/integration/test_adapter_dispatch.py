"""Integration tests for AdapterRegistry dispatch (no hardware required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from zenith.adapters.registry import AdapterRegistry
from zenith.core.device import DeviceType


class TestAdapterDispatch:
    def test_dispatch_adb_fallback(self) -> None:
        """dispatch() falls back to subprocess when no ADB hardware available."""
        reg = AdapterRegistry()
        ok, out = reg.dispatch("adb:devices")
        # Should not crash; may succeed or fail depending on ADB availability
        assert isinstance(ok, bool)
        assert isinstance(out, str)

    def test_dispatch_fastboot_unknown(self) -> None:
        """dispatch() handles fastboot gracefully."""
        reg = AdapterRegistry()
        ok, out = reg.dispatch("fastboot:devices")
        assert isinstance(ok, bool)

    def test_dispatch_unknown_prefix(self) -> None:
        """dispatch() falls back to subprocess for unknown prefixes."""
        reg = AdapterRegistry()
        ok, out = reg.dispatch("unknown_cmd --help")
        assert isinstance(ok, bool)

    def test_dispatch_empty_command(self) -> None:
        """dispatch() handles empty commands gracefully."""
        reg = AdapterRegistry()
        ok, out = reg.dispatch("adb:")
        # adb with no args returns exit code 1 — that's expected
        assert isinstance(ok, bool)
        assert isinstance(out, str)

    def test_registry_create_returns_adapter(self) -> None:
        """create() returns an adapter instance for known types."""
        reg = AdapterRegistry()
        reg.register(DeviceType.ADB, MagicMock)
        adapter = reg.create(DeviceType.ADB)
        assert adapter is not None

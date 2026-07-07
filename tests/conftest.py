"""Test fixtures and configuration for Zenith Unified tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Yield a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def temp_file(temp_dir: Path) -> Generator[Path, None, None]:
    """Yield a pre-created temporary file."""
    f = temp_dir / "test.txt"
    f.write_text("test content")
    yield f


@pytest.fixture
def sample_device_info() -> dict:
    """Return a sample device info dict for testing."""
    return {
        "serial": "emulator-5554",
        "model": "Pixel 7",
        "manufacturer": "Google",
        "android_version": "14",
        "sdk_version": "34",
        "build_id": "UP1A.231005.007",
        "soc": "Google Tensor G2",
        "state": "device",
    }


@pytest.fixture
def sample_adb_devices_output() -> str:
    """Return sample `adb devices -l` output."""
    return (
        "List of devices attached\n"
        "emulator-5554          device product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a\n"
        "R5CT1234ABCD           device product:tokay model:Pixel_7 device:tokay\n"
    )


@pytest.fixture
def sample_prop_output() -> str:
    """Return sample `adb shell getprop` output."""
    return (
        "[ro.product.model]: [Pixel 7]\n"
        "[ro.product.manufacturer]: [Google]\n"
        "[ro.build.version.release]: [14]\n"
        "[ro.build.version.sdk]: [34]\n"
        "[ro.product.cpu.abi]: [arm64-v8a]\n"
        "[ro.hardware]: [tokay]\n"
    )

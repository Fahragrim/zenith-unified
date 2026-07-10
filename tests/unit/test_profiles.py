"""Unit tests for device profiles and registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from zenith.knowledge.device_profile import DeviceProfile, FRPMethod, ModeInfo, UnlockMethod
from zenith.knowledge.device_registry import DeviceProfileRegistry, get_device_profile_registry


class TestDeviceProfile:
    def test_load_sony_xz2(self) -> None:
        profiles_dir = Path(__file__).resolve().parents[2] / "src" / "zenith" / "data" / "devices"
        path = profiles_dir / "sony_xz2_h8266.json"
        assert path.exists(), f"Profile not found: {path}"
        profile = DeviceProfile.from_json(path)
        assert profile.id == "sony_xz2_h8266"
        assert profile.manufacturer == "Sony"
        assert profile.soc_vendor == "Qualcomm"
        assert "SDM845" in profile.soc_name
        assert len(profile.modes) >= 4
        assert len(profile.frp_methods) >= 3
        assert len(profile.unlock_methods) >= 2
        assert len(profile.firehoses) >= 1

    def test_load_nokia_c32(self) -> None:
        profiles_dir = Path(__file__).resolve().parents[2] / "src" / "zenith" / "data" / "devices"
        path = profiles_dir / "nokia_c32_ta1534.json"
        assert path.exists(), f"Profile not found: {path}"
        profile = DeviceProfile.from_json(path)
        assert profile.id == "nokia_c32_ta1534"
        assert profile.manufacturer == "Nokia"
        assert profile.soc_vendor == "Unisoc"
        assert profile.sprd_chip_family == "SHARKL3"
        assert profile.fdl1_base == 20480
        assert profile.cve_exec_addr == 20200
        assert len(profile.modes) >= 5

    def test_display_name(self) -> None:
        profiles_dir = Path(__file__).resolve().parents[2] / "src" / "zenith" / "data" / "devices"
        profile = DeviceProfile.from_json(profiles_dir / "sony_xz2_h8266.json")
        assert "Sony Xperia XZ2" in profile.display_name

    def test_get_mode(self) -> None:
        profiles_dir = Path(__file__).resolve().parents[2] / "src" / "zenith" / "data" / "devices"
        profile = DeviceProfile.from_json(profiles_dir / "sony_xz2_h8266.json")
        edl = profile.get_mode("edl")
        assert edl is not None
        assert "9008" in edl.display_name
        non = profile.get_mode("nonexistent")
        assert non is None

    def test_get_frp_method(self) -> None:
        profiles_dir = Path(__file__).resolve().parents[2] / "src" / "zenith" / "data" / "devices"
        profile = DeviceProfile.from_json(profiles_dir / "sony_xz2_h8266.json")
        first = profile.frp_methods[0]
        found = profile.get_frp_method(first.id)
        assert found is not None
        assert found.name == first.name

    def test_get_frp_partitions(self) -> None:
        profiles_dir = Path(__file__).resolve().parents[2] / "src" / "zenith" / "data" / "devices"
        profile = DeviceProfile.from_json(profiles_dir / "sony_xz2_h8266.json")
        frp_parts = profile.get_frp_partitions()
        assert isinstance(frp_parts, list)

    def test_nokia_sprd_fields(self) -> None:
        profiles_dir = Path(__file__).resolve().parents[2] / "src" / "zenith" / "data" / "devices"
        profile = DeviceProfile.from_json(profiles_dir / "nokia_c32_ta1534.json")
        assert profile.sprd_chip_family is not None
        assert profile.fdl1_base is not None
        assert profile.fdl2_base is not None
        assert profile.cve_exec_addr is not None


class TestDeviceProfileRegistry:
    def test_loads_both_profiles(self) -> None:
        reg = DeviceProfileRegistry()
        count = reg.load_all()
        assert count >= 2

    def test_get_by_id(self) -> None:
        reg = DeviceProfileRegistry()
        reg.load_all()
        sony = reg.get("sony_xz2_h8266")
        assert sony is not None
        assert sony.manufacturer == "Sony"
        nokia = reg.get("nokia_c32_ta1534")
        assert nokia is not None
        assert nokia.manufacturer == "Nokia"

    def test_list_ids(self) -> None:
        reg = DeviceProfileRegistry()
        ids = reg.list_ids()
        assert "sony_xz2_h8266" in ids
        assert "nokia_c32_ta1534" in ids

    def test_match_by_usb_qualcomm_edl(self) -> None:
        reg = DeviceProfileRegistry()
        reg.load_all()
        # 0x05C6=1478, 0x9008=36872 — multiple profiles match this (sony, motorola, google, samsung)
        matched = reg.match_by_usb(0x05C6, 0x9008)
        assert matched is not None
        assert matched.soc_vendor == "Qualcomm"

    def test_match_by_usb_sprd(self) -> None:
        reg = DeviceProfileRegistry()
        reg.load_all()
        matched = reg.match_by_usb(0x1782, 0x4D00)
        assert matched is not None
        assert "nokia" in matched.id

    def test_match_by_usb_none(self) -> None:
        reg = DeviceProfileRegistry()
        reg.load_all()
        assert reg.match_by_usb(0xFFFF, 0xFFFF) is None

    def test_search(self) -> None:
        reg = DeviceProfileRegistry()
        reg.load_all()
        results = reg.search("qualcomm")
        assert len(results) >= 1
        results = reg.search("nokia")
        assert len(results) >= 1

    def test_singleton(self) -> None:
        r1 = get_device_profile_registry()
        r2 = get_device_profile_registry()
        assert r1 is r2

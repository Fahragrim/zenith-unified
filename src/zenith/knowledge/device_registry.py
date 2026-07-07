"""Device Profile Registry — load, validate, and match JSON device profiles.

Reads data/devices/*.json, validates against _schema.json.
Provides auto-matching against DiscoveryResult and USB VID/PID.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from loguru import logger

from zenith.knowledge.device_profile import DeviceProfile

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "data" / "devices" / "_schema.json"
PROFILES_DIR = Path(__file__).resolve().parents[3] / "data" / "devices"


class DeviceProfileRegistry:
    """Loads and manages device profiles from data/devices/*.json."""

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self.profiles_dir = profiles_dir or PROFILES_DIR
        self.profiles: dict[str, DeviceProfile] = {}
        self._loaded = False

    def load_all(self) -> int:
        """Load all *.json profiles (skips _schema.json)."""
        self.profiles.clear()
        if not self.profiles_dir.exists():
            logger.warning(f"Profiles dir not found: {self.profiles_dir}")
            return 0

        for path in sorted(self.profiles_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            try:
                profile = DeviceProfile.from_json(path)
                self.profiles[profile.id] = profile
                logger.info(f"Loaded device profile: {profile.display_name}")
            except Exception as e:
                logger.error(f"Failed to load {path.name}: {e}")

        self._loaded = True
        logger.info(f"Loaded {len(self.profiles)} device profiles")
        return len(self.profiles)

    def get(self, profile_id: str) -> DeviceProfile | None:
        if not self._loaded:
            self.load_all()
        return self.profiles.get(profile_id)

    def list_all(self) -> list[DeviceProfile]:
        if not self._loaded:
            self.load_all()
        return list(self.profiles.values())

    def list_ids(self) -> list[str]:
        if not self._loaded:
            self.load_all()
        return list(self.profiles.keys())

    def match_by_usb(self, vid: int, pid: int) -> DeviceProfile | None:
        """Find the device profile matching a USB VID/PID pair."""
        if not self._loaded:
            self.load_all()

        for profile in self.profiles.values():
            for mode in profile.modes:
                for usb_id in mode.usb_ids:
                    if usb_id.vid == vid and usb_id.pid == pid:
                        return profile
                    if usb_id.vid == vid and usb_id.pid == 0:
                        return profile
        return None

    def match_by_mode(self, mode_names: list[str]) -> DeviceProfile | None:
        """Find a profile whose modes overlap with detected modes."""
        if not self._loaded:
            self.load_all()

        best = None
        best_score = 0
        for profile in self.profiles.values():
            profile_modes = {m.name for m in profile.modes}
            overlap = len(profile_modes & set(mode_names))
            if overlap > best_score:
                best_score = overlap
                best = profile

        return best if best_score > 0 else None

    def match_by_discovery(self, discovery_result: Any) -> list[DeviceProfile]:
        """Match profiles against a DiscoveryResult from zenith.core.discovery."""
        if not self._loaded:
            self.load_all()

        mode_names = [m.value for m in discovery_result.modes]

        scored: list[tuple[int, DeviceProfile]] = []
        for profile in self.profiles.values():
            profile_modes = {m.name for m in profile.modes}
            profile_port_patterns: set[str] = set()
            for m in profile.modes:
                profile_port_patterns.update(p.lower() for p in m.port_description_patterns)

            score = len(profile_modes & set(mode_names))
            for port in discovery_result.serial_ports:
                desc = port.get("description", "").lower()
                for pattern in profile_port_patterns:
                    if pattern in desc or desc in pattern:
                        score += 2
                        break
            for hit in discovery_result.usb_hits:
                for mode in profile.modes:
                    for usb_id in mode.usb_ids:
                        if usb_id.vid == hit.vid and usb_id.pid == hit.pid:
                            score += 5
                            break
            if score > 0:
                scored.append((score, profile))

        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored]

    def search(self, query: str) -> list[DeviceProfile]:
        """Free-text search across all profiles."""
        q = query.lower()
        if not self._loaded:
            self.load_all()
        return [
            p for p in self.profiles.values()
            if q in p.manufacturer.lower() or q in p.model.lower()
            or q in p.codename.lower() or q in p.soc_vendor.lower()
            or q in p.soc_name.lower()
        ]


# Module-level singleton
_registry: DeviceProfileRegistry | None = None
_registry_lock = threading.Lock()


def get_device_profile_registry() -> DeviceProfileRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = DeviceProfileRegistry()
    return _registry

"""Device Manager — unified device lifecycle management.

Handles discovery, connection tracking, and profile matching.
Combines xperiatool's DeviceRegistry with OpencodeDeviceTool's detect_devices.
"""

from __future__ import annotations

import contextlib
from typing import Any

from loguru import logger

from zenith.core.device import (
    Device,
    DeviceSnapshot,
    DeviceType,
    detect_device_type_from_usb,
    get_vendor_name,
)


class DeviceManager:
    """Central device lifecycle manager."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._snapshots: dict[str, list[DeviceSnapshot]] = {}
        self._on_connect: list[Any] = []
        self._on_disconnect: list[Any] = []

    @property
    def devices(self) -> list[Device]:
        return list(self._devices.values())

    @property
    def connected_devices(self) -> list[Device]:
        return [d for d in self._devices.values() if d.is_connected]

    def get(self, identifier: str) -> Device | None:
        return self._devices.get(identifier)

    def register(self, device: Device) -> None:
        if device.identifier in self._devices:
            logger.debug("Device already registered: {}", device.identifier)
            return
        self._devices[device.identifier] = device
        device.register_disconnect_callback(self._on_device_disconnected)
        logger.info("Registered device: {} ({})", device.identifier, device.type.value)

    def unregister(self, identifier: str) -> Device | None:
        device = self._devices.pop(identifier, None)
        if device:
            logger.info("Unregistered device: {}", identifier)
        return device

    async def connect(self, identifier: str) -> bool:
        device = self._devices.get(identifier)
        if device is None:
            logger.error("Device not found: {}", identifier)
            return False
        try:
            success = await device.connect()
            if success:
                info = await device.get_info()
                snapshot = DeviceSnapshot(info=info)
                self._snapshots.setdefault(identifier, []).append(snapshot)
                for cb in self._on_connect:
                    with contextlib.suppress(Exception):
                        cb(device)
            return success
        except Exception as e:
            logger.exception(f"Failed to connect to {identifier}: {e}")
            return False

    async def disconnect(self, identifier: str) -> None:
        device = self._devices.get(identifier)
        if device is None:
            return
        try:
            await device.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting {identifier}: {e}")

    def _on_device_disconnected(self, device: Device) -> None:
        for cb in self._on_disconnect:
            with contextlib.suppress(Exception):
                cb(device)

    def on_device_connected(self, callback: Any) -> None:
        self._on_connect.append(callback)

    def on_device_disconnected(self, callback: Any) -> None:
        self._on_disconnect.append(callback)

    def get_snapshots(self, identifier: str) -> list[DeviceSnapshot]:
        return self._snapshots.get(identifier, [])

    def get_latest_snapshot(self, identifier: str) -> DeviceSnapshot | None:
        snapshots = self._snapshots.get(identifier, [])
        return snapshots[-1] if snapshots else None

    def detect_from_usb_ids(self, vid: int, pid: int) -> DeviceType:
        return detect_device_type_from_usb(vid, pid)

    def get_vendor(self, vid: int) -> str:
        return get_vendor_name(vid)

    def shutdown(self) -> None:
        for identifier in list(self._devices.keys()):
            self._devices[identifier]._mark_disconnected()
        self._devices.clear()
        self._snapshots.clear()
        logger.info("DeviceManager shut down: all devices released")

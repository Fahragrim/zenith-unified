"""Device Profile models — Pydantic v2 schema for JSON device profiles.

Validated against data/devices/_schema.json.
A DeviceProfile contains everything needed to diagnose/repair a specific device:
modes, FRP methods, unlock methods, firehoses, test points, partitions, AT commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UsbId(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vid: int
    pid: int = 0


class ModeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    display_name: str
    usb_ids: list[UsbId] = Field(default_factory=list)
    port_description_patterns: list[str] = Field(default_factory=list)
    entry_methods: list[str] = Field(default_factory=list)
    exit_methods: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    description: str = ""


class FRPMethod(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    category: str = "general"
    success_rate: float = 0.0
    risk_level: str = "MEDIUM"
    prerequisites: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    requires_screen: bool = False
    requires_adb: bool = False
    requires_edl: bool = False
    requires_root: bool = False
    cost: str = "Gratis"
    guide_file: str | None = None
    commands: list[str] = Field(default_factory=list)


class UnlockMethod(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    success_rate: float = 0.0
    risk_level: str = "MEDIUM"
    prerequisites: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    guide_file: str | None = None
    official: bool = False


class FirehoseInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    priority: int = 99
    notes: str = ""


class TestPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    location: str
    coordinates: str | None = None
    notes: str = ""


class PartitionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    purpose: str = ""
    frp_relevant: bool = False
    backup_before_write: bool = True


class ATCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str
    description: str = ""
    modifies_nvram: bool = False
    risk_level: str = "LOW"


class ServiceCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    function: str


class DeviceProfile(BaseModel):
    """Complete device profile — identifies a device and all its capabilities."""

    model_config = ConfigDict(extra="forbid")

    id: str
    manufacturer: str
    model: str
    codename: str
    soc_vendor: str
    soc_name: str
    android_version: str = ""
    storage_type: str = ""
    bootloader_locked: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    modes: list[ModeInfo] = Field(default_factory=list)
    frp_methods: list[FRPMethod] = Field(default_factory=list)
    unlock_methods: list[UnlockMethod] = Field(default_factory=list)
    firehoses: list[FirehoseInfo] = Field(default_factory=list)
    test_points: list[TestPoint] = Field(default_factory=list)
    partitions: list[PartitionInfo] = Field(default_factory=list)
    at_commands: list[ATCommand] = Field(default_factory=list)
    service_codes: list[ServiceCode] = Field(default_factory=list)
    sprd_chip_family: str | None = None
    fdl1_base: int | None = None
    fdl2_base: int | None = None
    cve_exec_addr: int | None = None
    talkback_shortcuts: dict[str, str] = Field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return f"{self.manufacturer} {self.model} ({self.codename})"

    def get_mode(self, name: str) -> ModeInfo | None:
        for m in self.modes:
            if m.name == name:
                return m
        return None

    def get_frp_method(self, method_id: str) -> FRPMethod | None:
        for m in self.frp_methods:
            if m.id == method_id:
                return m
        return None

    def get_unlock_method(self, method_id: str) -> UnlockMethod | None:
        for m in self.unlock_methods:
            if m.id == method_id:
                return m
        return None

    def get_frp_partitions(self) -> list[str]:
        return [p.name for p in self.partitions if p.frp_relevant]

    @classmethod
    def from_json(cls, path: Path) -> DeviceProfile:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate(data)

"""Unit tests for zenith core module — Phase 1."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from zenith.core.audit import AuditEntry, AuditLog, _compute_hash, _make_summary, GENESIS_HASH
from zenith.core.backup_manager import BackupManager
from zenith.core.consent import ConsentGate, ConsentStatus
from zenith.core.device import (
    Device,
    DeviceInfo,
    DeviceRegistry,
    DeviceSnapshot,
    DeviceStatus,
    DeviceType,
    PortInfo,
    RiskLevel,
    UsbIdentifier,
    detect_device_type_from_usb,
    get_vendor_name,
)
from zenith.core.device_manager import DeviceManager
from zenith.core.discovery import (
    ConnectionMode,
    DiscoveryResult,
    UsbEndpoint,
    _pick_primary_mode,
    run_discovery,
)
from zenith.core.event_bus import Event, EventBus
from zenith.core.exceptions import (
    ConsentDeniedError,
    ConsentRequiredError,
    PolicyViolationError,
    ZenithError,
)
from zenith.core.policy import (
    ActionLevel,
    PolicyContext,
    PolicyEngine,
    PolicyRule,
    Verdict,
)

# ─── Device Models ───────────────────────────────────────────────────────


class TestDeviceType:
    def test_all_types_registered(self) -> None:
        assert len(DeviceType) >= 10

    def test_string_values(self) -> None:
        assert DeviceType.ADB.value == "adb"
        assert DeviceType.QUALCOMM_EDL.value == "qualcomm_edl"

    def test_detect_from_usb_qualcomm_edl(self) -> None:
        assert detect_device_type_from_usb(0x05C6, 0x9008) == DeviceType.QUALCOMM_EDL

    def test_detect_from_usb_mtk_brom(self) -> None:
        assert detect_device_type_from_usb(0x0E8D, 0x0003) == DeviceType.MTK_BROM

    def test_detect_from_usb_unknown(self) -> None:
        assert detect_device_type_from_usb(0xFFFF, 0xFFFF) == DeviceType.ANDROID

    def test_get_vendor_qualcomm(self) -> None:
        assert get_vendor_name(0x05C6) == "Qualcomm"

    def test_get_vendor_unknown(self) -> None:
        assert "0xFFFF" in get_vendor_name(0xFFFF)


class TestDeviceInfo:
    def test_creation(self) -> None:
        info = DeviceInfo(serial="12345", type=DeviceType.ADB, manufacturer="Google", model="Pixel 7")
        assert info.serial == "12345"
        assert info.type == DeviceType.ADB
        assert info.manufacturer == "Google"

    def test_vid_pid_label(self) -> None:
        info = DeviceInfo(usb_vid=0x05C6, usb_pid=0x9008)
        assert info.vid_pid_label == "05C6:9008"

    def test_vid_pid_label_none(self) -> None:
        info = DeviceInfo()
        assert info.vid_pid_label == ""


class TestUsbIdentifier:
    def test_match_exact(self) -> None:
        uid = UsbIdentifier(vid=0x05C6, pid=0x9008)
        assert uid.match(0x05C6, 0x9008) is True

    def test_match_wildcard(self) -> None:
        uid = UsbIdentifier(vid=0x0E8D, pid=0)
        assert uid.match(0x0E8D, 0x0003) is True
        assert uid.match(0x0E8D, 0x9999) is True

    def test_no_match(self) -> None:
        uid = UsbIdentifier(vid=0x05C6, pid=0x9008)
        assert uid.match(0x0E8D, 0x0003) is False

    def test_label(self) -> None:
        uid = UsbIdentifier(vid=0x05C6, pid=0x9008)
        assert uid.label == "05C6:9008"


class TestPortInfo:
    def test_creation(self) -> None:
        port = PortInfo(device="COM3", description="USB Serial", hwid="VID:PID=05C6:9008")
        assert port.device == "COM3"
        assert port.description == "USB Serial"


class TestDeviceRegistry:
    def test_register_and_create(self) -> None:
        class FakeDevice(Device):
            async def connect(self) -> bool:
                return True

            async def disconnect(self) -> None:
                pass

            async def get_info(self) -> DeviceInfo:
                return DeviceInfo()

            async def execute(self, command: str, timeout: int = 30):
                from zenith.core.device import ActionResult
                return ActionResult(success=True, action=command)

        DeviceRegistry.register(DeviceType.ADB, FakeDevice)
        dev = DeviceRegistry.create(DeviceType.ADB, "test123")
        assert dev.serial == "test123"
        assert dev.type == DeviceType.ADB

    def test_create_unregistered_raises(self) -> None:
        with pytest.raises(ValueError):
            DeviceRegistry.create(DeviceType.APPLE_DFU, "test")


# ─── EventBus ────────────────────────────────────────────────────────────


class TestEventBus:
    def test_publish_and_subscribe(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("test.topic", handler)
        bus.publish("test.topic", data={"key": "value"})
        assert len(received) == 1
        assert received[0].data == {"key": "value"}
        assert received[0].topic == "test.topic"

    def test_wildcard_subscription(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        bus.subscribe("*", lambda e: received.append(e))
        bus.publish("foo.bar")
        bus.publish("baz.qux")
        assert len(received) == 2

    def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        def handler(event: Event) -> None:
            received.append(event)

        bus.subscribe("test", handler)
        bus.publish("test")
        assert len(received) == 1
        bus.unsubscribe("test", handler)
        bus.publish("test")
        assert len(received) == 1  # No new events

    def test_history(self) -> None:
        bus = EventBus()
        bus.publish("a")
        bus.publish("b")
        bus.publish("c")
        hist = bus.history()
        assert len(hist) == 3
        assert hist[0].topic == "a"

    def test_history_filtered(self) -> None:
        bus = EventBus()
        bus.publish("flash.start")
        bus.publish("flash.progress")
        bus.publish("device.detected")
        hist = bus.history(topic="flash")
        assert len(hist) == 2

    def test_event_frozen(self) -> None:
        e = Event(topic="test", data=42, source="unit")
        assert e.topic == "test"
        assert e.data == 42
        assert e.source == "unit"


# ─── Policy Engine ───────────────────────────────────────────────────────


class TestPolicyEngine:
    def test_read_always_allowed(self) -> None:
        engine = PolicyEngine()
        ctx = PolicyContext()
        decision = engine.evaluate(ActionLevel.READ, ctx)
        assert decision.verdict == Verdict.ALLOW

    def test_destructive_requires_consent(self) -> None:
        engine = PolicyEngine()
        ctx = PolicyContext(operator_acknowledged_legal=True)
        decision = engine.evaluate(ActionLevel.DESTRUCTIVE, ctx)
        assert decision.verdict == Verdict.REQUIRE_CONSENT

    def test_destructive_denied_without_legal_ack(self) -> None:
        engine = PolicyEngine()
        ctx = PolicyContext(operator_acknowledged_legal=False)
        decision = engine.evaluate(ActionLevel.DESTRUCTIVE, ctx)
        assert decision.verdict == Verdict.DENY

    def test_dry_run_blocks_write(self) -> None:
        engine = PolicyEngine()
        ctx = PolicyContext(dry_run=True)
        decision = engine.evaluate(ActionLevel.WRITE, ctx)
        assert decision.verdict == Verdict.DENY

    def test_enforce_raises_on_deny(self) -> None:
        engine = PolicyEngine()
        ctx = PolicyContext(operator_acknowledged_legal=False)
        with pytest.raises(PolicyViolationError):
            engine.enforce(ActionLevel.DESTRUCTIVE, ctx)

    def test_enforce_pass_on_allow(self) -> None:
        engine = PolicyEngine()
        ctx = PolicyContext()
        decision = engine.enforce(ActionLevel.READ, ctx)
        assert decision.verdict == Verdict.ALLOW

    def test_add_rule(self) -> None:
        engine = PolicyEngine()
        # Custom rule at specific level should match before default R001
        engine.add_rule(PolicyRule("CUSTOM", ActionLevel.READ, Verdict.DENY, "Blocked by custom rule"))
        ctx = PolicyContext()
        decision = engine.evaluate(ActionLevel.READ, ctx)
        assert decision.verdict == Verdict.DENY
        assert decision.rule_id == "CUSTOM"

    def test_forensic_is_read_equivalent(self) -> None:
        engine = PolicyEngine()
        ctx = PolicyContext()
        decision = engine.evaluate(ActionLevel.FORENSIC, ctx)
        assert decision.verdict == Verdict.ALLOW


# ─── Audit Log ───────────────────────────────────────────────────────────


class TestAuditLog:
    def test_record_and_verify(self, temp_dir: Path) -> None:
        log = AuditLog(temp_dir / "test_audit.jsonl")
        log.record("device.detected", source="test", device_serial="123", data={"mode": "adb"})
        log.record("flash.start", source="test", device_serial="123", data={"partition": "boot"})
        assert log.verify_chain() is True

    def test_tamper_detection(self, temp_dir: Path) -> None:
        log = AuditLog(temp_dir / "tamper_audit.jsonl")
        log.record("test.event", source="test")
        # Tamper with the file
        content = log.path.read_text()
        content = content.replace('"hash"', '"hash_x"')
        log.path.write_text(content)
        assert log.verify_chain() is False

    def test_tail(self, temp_dir: Path) -> None:
        log = AuditLog(temp_dir / "tail_audit.jsonl")
        for i in range(25):
            log.record(f"event.{i}", source="test")
        entries = log.tail(10)
        assert len(entries) == 10

    def test_query_by_device(self, temp_dir: Path) -> None:
        log = AuditLog(temp_dir / "query_audit.jsonl")
        log.record("event.a", source="test", device_serial="AAA")
        log.record("event.b", source="test", device_serial="BBB")
        log.record("event.c", source="test", device_serial="AAA")
        results = log.query(device_serial="AAA")
        assert len(results) == 2

    def test_query_by_level(self, temp_dir: Path) -> None:
        log = AuditLog(temp_dir / "level_audit.jsonl")
        log.record("flash.start", source="test")
        log.record("device.detected", source="test")
        destructive = log.query(action_level="destructive")
        assert len(destructive) == 1

    def test_stats(self, temp_dir: Path) -> None:
        log = AuditLog(temp_dir / "stats_audit.jsonl")
        log.record("flash.start", source="test")
        log.record("device.detected", source="test")
        s = log.stats()
        assert "destructive" in s or "read" in s

    def test_compute_hash(self) -> None:
        entry = AuditEntry(seq=1, timestamp="now", topic="test", source="s", action_level="read", summary="test")
        h = _compute_hash(entry, GENESIS_HASH)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_make_summary(self) -> None:
        assert "boot" in _make_summary("flash.start", {"partition": "boot"})
        assert "playbook" in _make_summary("recovery.playbook", {"playbook_id": "test"})

    def test_subscribe_to_bus(self, temp_dir: Path) -> None:
        log = AuditLog(temp_dir / "bus_audit.jsonl")
        bus = EventBus()
        log.subscribe_to_bus(bus)
        bus.publish("device.detected", data={"serial": "123"})
        entries = log.tail(5)
        assert any(e.topic == "device.detected" for e in entries)


# ─── Consent Gate ───────────────────────────────────────────────────────


class TestConsentGate:
    def test_request_auto_approve_low_risk(self) -> None:
        engine = PolicyEngine()
        gate = ConsentGate(engine, auto_approve_low_risk=True)
        status = gate.request("test", "Test", "Desc", risk_level="low")
        assert status.status == ConsentStatus.PENDING

    def test_grant(self) -> None:
        engine = PolicyEngine()
        gate = ConsentGate(engine)
        req = gate.request("flash", "Flash Boot", "Flashing boot partition", risk_level="high")
        status = gate.grant("flash")
        assert status == ConsentStatus.GRANTED

    def test_deny(self) -> None:
        engine = PolicyEngine()
        gate = ConsentGate(engine)
        gate.request("flash", "Flash Boot", "Flashing boot", risk_level="high")
        status = gate.deny("flash")
        assert status == ConsentStatus.DENIED

    def test_check_and_require_high_risk_raises(self) -> None:
        engine = PolicyEngine()
        gate = ConsentGate(engine, auto_approve_low_risk=True)
        with pytest.raises(ConsentRequiredError):
            gate.check_and_require("flash", "Flash", "Flashing", risk_level="high")

    def test_is_pending(self) -> None:
        engine = PolicyEngine()
        gate = ConsentGate(engine)
        gate.request("test", "T", "D")
        assert gate.is_pending("test") is True
        assert gate.is_pending("nonexistent") is False

    def test_history(self) -> None:
        engine = PolicyEngine()
        gate = ConsentGate(engine)
        gate.request("op1", "T1", "D1")
        gate.grant("op1")
        gate.request("op2", "T2", "D2")
        gate.deny("op2")
        hist = gate.history()
        assert len(hist) == 2


# ─── Backup Manager ──────────────────────────────────────────────────────


class TestBackupManager:
    def test_create_and_verify_backup(self, temp_dir: Path) -> None:
        mgr = BackupManager(temp_dir)
        manifest = mgr.create_backup(
            "device_001",
            {"file1.txt": b"hello", "sub/file2.bin": b"world"},
        )
        assert manifest is not None
        assert len(manifest.files) == 2
        assert mgr.verify_backup(manifest.id) is True

    def test_list_backups(self, temp_dir: Path) -> None:
        mgr = BackupManager(temp_dir)
        mgr.create_backup("device_A", {"a.txt": b"a"})
        mgr.create_backup("device_B", {"b.txt": b"b"})
        all_backups = mgr.list_backups()
        assert len(all_backups) == 2
        a_backups = mgr.list_backups(device_serial="device_A")
        assert len(a_backups) == 1

    def test_get_manifest(self, temp_dir: Path) -> None:
        mgr = BackupManager(temp_dir)
        manifest = mgr.create_backup("dev", {"f.txt": b"data"})
        assert manifest is not None
        retrieved = mgr.get_manifest(manifest.id)
        assert retrieved is not None
        assert retrieved.device_serial == "dev"

    def test_delete_backup(self, temp_dir: Path) -> None:
        mgr = BackupManager(temp_dir)
        manifest = mgr.create_backup("dev", {"f.txt": b"data"})
        assert manifest is not None
        assert mgr.delete_backup(manifest.id) is True
        assert mgr.get_manifest(manifest.id) is None

    def test_nonexistent_backup(self, temp_dir: Path) -> None:
        mgr = BackupManager(temp_dir)
        assert mgr.get_manifest("nonexistent") is None
        assert mgr.list_backups() == []


# ─── Discovery ───────────────────────────────────────────────────────────


class TestDiscovery:
    def test_run_discovery_empty(self) -> None:
        result = run_discovery(adb_devices=[], fastboot_devices=[])
        assert result.primary_mode == ConnectionMode.UNKNOWN

    def test_run_discovery_with_adb(self) -> None:
        result = run_discovery(
            adb_devices=[{"serial": "emulator-5554", "state": "device", "model": "Pixel"}],
            fastboot_devices=[],
        )
        assert ConnectionMode.ADB in result.modes

    def test_run_discovery_with_fastboot(self) -> None:
        result = run_discovery(
            adb_devices=[],
            fastboot_devices=["R5CT1234ABCD"],
        )
        assert ConnectionMode.FASTBOOT in result.modes

    def test_primary_mode_priority(self) -> None:
        modes = [ConnectionMode.ADB, ConnectionMode.QUALCOMM_EDL, ConnectionMode.FASTBOOT]
        primary = _pick_primary_mode(modes)
        assert primary == ConnectionMode.QUALCOMM_EDL  # Higher priority

    def test_matched_profiles_sony(self) -> None:
        result = run_discovery(
            adb_devices=[{"serial": "SERIAL", "state": "device"}],
            fastboot_devices=["SERIAL"],
        )
        assert "sony_xz2_h8266" in result.matched_profiles

    def test_to_display_text(self) -> None:
        result = run_discovery(adb_devices=[], fastboot_devices=[])
        text = result.to_display_text()
        assert "ZENITH DEVICE DISCOVERY" in text


# ─── Device Manager ──────────────────────────────────────────────────────


class TestDeviceManager:
    @pytest.mark.asyncio
    async def test_register_device(self) -> None:
        class FakeDevice(Device):
            async def connect(self) -> bool:
                self._status = DeviceStatus.CONNECTED
                return True

            async def disconnect(self) -> None:
                self._status = DeviceStatus.DISCONNECTED

            async def get_info(self) -> DeviceInfo:
                return DeviceInfo(serial=self.identifier)

            async def execute(self, command: str, timeout: int = 30):
                from zenith.core.device import ActionResult
                return ActionResult(success=True, action=command)

        DeviceRegistry.register(DeviceType.ADB, FakeDevice)
        mgr = DeviceManager()
        dev = DeviceRegistry.create(DeviceType.ADB, "test123")
        mgr.register(dev)
        assert mgr.get("test123") is not None
        assert len(mgr.devices) == 1

    @pytest.mark.asyncio
    async def test_connect_device(self) -> None:
        class FakeDevice(Device):
            async def connect(self) -> bool:
                self._status = DeviceStatus.CONNECTED
                self._info = DeviceInfo(serial=self.identifier, type=DeviceType.ADB)
                return True

            async def disconnect(self) -> None:
                self._status = DeviceStatus.DISCONNECTED

            async def get_info(self) -> DeviceInfo:
                return DeviceInfo(serial=self.identifier, type=DeviceType.ADB)

            async def execute(self, command: str, timeout: int = 30):
                from zenith.core.device import ActionResult
                return ActionResult(success=True, action=command)

        DeviceRegistry.register(DeviceType.ADB, FakeDevice)
        mgr = DeviceManager()
        dev = DeviceRegistry.create(DeviceType.ADB, "test123")
        mgr.register(dev)
        success = await mgr.connect("test123")
        assert success is True
        assert dev.is_connected is True

    def test_detect_from_usb_ids(self) -> None:
        mgr = DeviceManager()
        assert mgr.detect_from_usb_ids(0x05C6, 0x9008) == DeviceType.QUALCOMM_EDL

    def test_get_vendor(self) -> None:
        mgr = DeviceManager()
        assert mgr.get_vendor(0x1782) == "Unisoc/Spreadtrum"


# ─── Exceptions ──────────────────────────────────────────────────────────


class TestExceptions:
    def test_zenith_error_inheritance(self) -> None:
        assert issubclass(PolicyViolationError, ZenithError)
        assert issubclass(ConsentRequiredError, ZenithError)
        assert issubclass(ConsentDeniedError, ZenithError)
        assert issubclass(ConsentDeniedError, ZenithError)

    def test_raise_and_catch(self) -> None:
        with pytest.raises(ZenithError):
            raise PolicyViolationError("Test error")

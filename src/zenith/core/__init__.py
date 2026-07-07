"""Core module exports for Zenith Unified."""

from zenith.core.audit import AuditEntry, AuditLog
from zenith.core.backup_manager import BackupManager
from zenith.core.consent import ConsentGate, ConsentRequest, ConsentStatus
from zenith.core.device import (
    ActionResult,
    ActionType,
    Device,
    DeviceInfo,
    DeviceRegistry,
    DeviceSnapshot,
    DeviceStatus,
    DeviceType,
    PortInfo,
    RiskLevel,
    SoCVendor,
    UsbIdentifier,
    detect_device_type_from_usb,
    get_vendor_name,
)
from zenith.core.device_manager import DeviceManager
from zenith.core.discovery import (
    ConnectionMode,
    DiscoveryResult,
    UsbEndpoint,
    run_discovery,
    scan_adb,
    scan_fastboot,
    scan_serial_ports,
    scan_usb_pyusb,
)
from zenith.core.event_bus import Event, EventBus, get_event_bus
from zenith.core.exceptions import (
    AdapterError,
    BackupFailedError,
    BackupRequiredError,
    ConsentDeniedError,
    ConsentRequiredError,
    DeviceNotFoundError,
    PolicyViolationError,
    ProtocolError,
    SafetyViolationError,
    VerificationFailedError,
    ZenithError,
)
from zenith.core.policy import (
    ActionLevel,
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
    PolicyRule,
    Verdict,
)

__all__ = [
    # Enums
    "ActionLevel",
    "ActionType",
    "ConnectionMode",
    "ConsentStatus",
    "DeviceStatus",
    "DeviceType",
    "RiskLevel",
    "SoCVendor",
    "Verdict",
    # Models
    "ActionResult",
    "AuditEntry",
    "ConsentRequest",
    "Device",
    "DeviceInfo",
    "DeviceRegistry",
    "DeviceSnapshot",
    "DiscoveryResult",
    "PortInfo",
    "UsbEndpoint",
    "UsbIdentifier",
    "PolicyContext",
    "PolicyDecision",
    "PolicyRule",
    # Managers & Engines
    "AuditLog",
    "BackupManager",
    "ConsentGate",
    "DeviceManager",
    "Event",
    "EventBus",
    "PolicyEngine",
    # Functions
    "detect_device_type_from_usb",
    "get_event_bus",
    "get_vendor_name",
    "run_discovery",
    "scan_adb",
    "scan_fastboot",
    "scan_serial_ports",
    "scan_usb_pyusb",
    # Exceptions
    "AdapterError",
    "BackupFailedError",
    "BackupRequiredError",
    "ConsentDeniedError",
    "ConsentRequiredError",
    "DeviceNotFoundError",
    "PolicyViolationError",
    "ProtocolError",
    "SafetyViolationError",
    "VerificationFailedError",
    "ZenithError",
]

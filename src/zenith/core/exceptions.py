"""Custom exceptions for Zenith Unified."""

from __future__ import annotations


class ZenithError(Exception):
    """Base exception for all Zenith errors."""


class DeviceNotFoundError(ZenithError):
    """Raised when a device cannot be found."""


class AdapterError(ZenithError):
    """Raised when an adapter operation fails."""


class SafetyViolationError(ZenithError):
    """Raised when a safety policy blocks an operation."""


class PolicyViolationError(ZenithError):
    """Raised when a policy rule denies an action."""


class ConsentRequiredError(ZenithError):
    """Raised when human-in-the-loop consent is required."""


class ConsentDeniedError(ZenithError):
    """Raised when consent is denied by the operator."""


class BackupRequiredError(ZenithError):
    """Raised when a backup must be created before proceeding."""


class BackupFailedError(ZenithError):
    """Raised when a backup operation fails."""


class VerificationFailedError(ZenithError):
    """Raised when a post-operation verification fails."""


class ProtocolError(ZenithError):
    """Raised when a protocol-level error occurs."""


class AuditIntegrityError(ZenithError):
    """Raised when the audit log integrity check fails."""

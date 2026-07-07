"""Human-in-the-loop Consent Gate.

All destructive operations flow through here before execution.
Integrates with PolicyEngine and AuditLog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from loguru import logger

from zenith.core.exceptions import ConsentRequiredError

if TYPE_CHECKING:
    from zenith.core.audit import AuditLog
    from zenith.core.event_bus import EventBus
    from zenith.core.policy import PolicyEngine


class ConsentStatus(str, Enum):
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    EXPIRED = "expired"
    NOT_REQUIRED = "not_required"


@dataclass
class ConsentRequest:
    operation: str
    title: str
    description: str
    risk_level: str
    device_serial: str = ""
    requires_legal_ack: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    status: ConsentStatus = ConsentStatus.PENDING
    granted_at: str | None = None
    expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation, "title": self.title,
            "description": self.description, "risk_level": self.risk_level,
            "device_serial": self.device_serial, "requires_legal_ack": self.requires_legal_ack,
            "details": self.details, "status": self.status.value,
            "granted_at": self.granted_at, "expires_at": self.expires_at,
        }


class ConsentGate:
    """Manages human-in-the-loop consent for risky operations."""

    def __init__(
        self,
        policy_engine: PolicyEngine,
        audit_log: AuditLog | None = None,
        bus: EventBus | None = None,
        *,
        auto_approve_low_risk: bool = True,
    ) -> None:
        self.policy = policy_engine
        self.audit = audit_log
        self.bus = bus
        self.auto_approve_low_risk = auto_approve_low_risk
        self._pending: dict[str, ConsentRequest] = {}
        self._history: list[ConsentRequest] = []

    def request(
        self,
        operation: str,
        title: str,
        description: str,
        *,
        risk_level: str = "medium",
        device_serial: str = "",
        requires_legal_ack: bool = False,
        details: dict[str, Any] | None = None,
    ) -> ConsentRequest:
        req = ConsentRequest(
            operation=operation, title=title, description=description,
            risk_level=risk_level, device_serial=device_serial,
            requires_legal_ack=requires_legal_ack,
            details=details or {},
        )
        self._pending[operation] = req

        if self.bus:
            self.bus.publish("consent.requested", data=req.to_dict(), source="zenith.consent")

        logger.info(f"Consent requested: {title} [{risk_level}]")
        return req

    def auto_evaluate(self, req: ConsentRequest) -> ConsentStatus:
        if self.auto_approve_low_risk and req.risk_level == "low":
            return self.grant(req.operation, reason="Auto-approved (low risk)")

        if req.risk_level in ("high", "critical") and not req.requires_legal_ack:
            return ConsentStatus.PENDING

        return ConsentStatus.PENDING

    def grant(self, operation: str, *, reason: str = "") -> ConsentStatus:
        req = self._pending.pop(operation, None)
        if req is None:
            logger.warning(f"Consent grant for unknown operation: {operation}")
            return ConsentStatus.NOT_REQUIRED

        req.status = ConsentStatus.GRANTED
        req.granted_at = datetime.now(timezone.utc).isoformat()
        self._history.append(req)

        if self.audit:
            self.audit.record(
                "consent.granted", source="zenith.consent",
                data={"operation": operation, "reason": reason, "risk_level": req.risk_level},
                device_serial=req.device_serial,
            )

        if self.bus:
            self.bus.publish("consent.granted", data=req.to_dict(), source="zenith.consent")

        logger.info(f"Consent granted: {operation} — {reason}")
        return ConsentStatus.GRANTED

    def deny(self, operation: str, *, reason: str = "") -> ConsentStatus:
        req = self._pending.pop(operation, None)
        if req is None:
            return ConsentStatus.NOT_REQUIRED

        req.status = ConsentStatus.DENIED
        self._history.append(req)

        if self.audit:
            self.audit.record(
                "consent.denied", source="zenith.consent",
                data={"operation": operation, "reason": reason, "risk_level": req.risk_level},
                device_serial=req.device_serial,
            )

        if self.bus:
            self.bus.publish("consent.denied", data=req.to_dict(), source="zenith.consent")

        logger.warning(f"Consent denied: {operation} — {reason}")
        return ConsentStatus.DENIED

    def check_and_require(
        self,
        operation: str,
        title: str,
        description: str,
        *,
        risk_level: str = "medium",
        device_serial: str = "",
        details: dict[str, Any] | None = None,
    ) -> ConsentStatus:
        """Request consent and raise if denied."""
        _req = self.request(
            operation, title, description,
            risk_level=risk_level, device_serial=device_serial,
            details=details,
        )

        # Auto-approve low risk
        if self.auto_approve_low_risk and risk_level == "low":
            return self.grant(operation, reason="Auto-approved (low risk)")

        # For high/critical, always require explicit consent
        raise ConsentRequiredError(
            f"Consent required for {operation}: {title} [{risk_level}]. "
            "Call consent_gate.grant() or consent_gate.deny() to proceed."
        )

    def is_pending(self, operation: str) -> bool:
        return operation in self._pending

    def get_pending(self) -> list[ConsentRequest]:
        return list(self._pending.values())

    def history(self, limit: int = 20) -> list[ConsentRequest]:
        return list(reversed(self._history))[:limit]

    def reset(self) -> None:
        self._pending.clear()

    def __len__(self) -> int:
        return len(self._pending)

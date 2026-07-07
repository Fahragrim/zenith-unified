"""Safety-by-Design policy engine.

Every destructive action passes through here. The policy decides:
  ALLOW   → proceed
  DENY    → hard block, raise PolicyViolation
  REQUIRE → hold for human-in-the-loop consent

Rules loaded from YAML. Built-in defaults if no YAML available.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from loguru import logger

from zenith.core.exceptions import PolicyViolationError

if TYPE_CHECKING:
    from zenith.core.event_bus import EventBus


class ActionLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    FORENSIC = "forensic"


class Verdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONSENT = "require_consent"


@dataclass(frozen=True)
class PolicyContext:
    device_serial: str | None = None
    device_profile_id: str | None = None
    user_role: str = "operator"
    operator_acknowledged_legal: bool = False
    dry_run: bool = False
    action_id: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    verdict: Verdict
    reason: str
    rule_id: str


@dataclass(frozen=True)
class PolicyRule:
    id: str
    level: ActionLevel | str
    verdict: Verdict
    reason: str
    when_dry_run: bool = False
    requires_legal_ack: bool = False

    def matches_level(self, level: ActionLevel) -> bool:
        if self.level == "any":
            return True
        return str(self.level) == str(level)


BUILTIN_RULES: list[PolicyRule] = [
    PolicyRule("R001", ActionLevel.READ, Verdict.ALLOW, "Read-only operations are always allowed."),
    PolicyRule("R002", ActionLevel.WRITE, Verdict.REQUIRE_CONSENT, "Writes require explicit consent."),
    PolicyRule("R003", ActionLevel.DESTRUCTIVE, Verdict.REQUIRE_CONSENT, "Destructive ops require consent + legal ack."),
    PolicyRule("R004", ActionLevel.DESTRUCTIVE, Verdict.DENY, "Destructive ops denied without legal acknowledgment.", requires_legal_ack=True),
    PolicyRule("R005", ActionLevel.FORENSIC, Verdict.ALLOW, "Forensic scans are read-only by design."),
    PolicyRule("R006", ActionLevel.WRITE, Verdict.DENY, "Writes denied in dry_run mode.", when_dry_run=True),
    PolicyRule("R007", ActionLevel.DESTRUCTIVE, Verdict.DENY, "Destructive ops denied in dry_run mode.", when_dry_run=True),
    PolicyRule("R000", "any", Verdict.DENY, "No matching rule — default deny (fail-closed)."),
]


class PolicyEngine:
    """Evaluates actions against rules, returns decisions."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._rules: list[PolicyRule] = list(BUILTIN_RULES)
        self._device_overrides: dict[str, dict[str, dict[str, str]]] = {}
        self.bus = bus

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.insert(0, rule)
        logger.debug(f"Policy: added rule {rule.id} at priority position")

    def load_rules_from_yaml(self, path: Path) -> int:
        if not path.exists():
            logger.warning(f"Policy rules YAML not found: {path} — using built-ins")
            return 0
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse {path}: {e}")
            return 0

        rules_data = data.get("rules", []) if isinstance(data, dict) else []
        loaded: list[PolicyRule] = []
        for rd in rules_data:
            try:
                level: ActionLevel | str = ActionLevel(rd["level"]) if rd["level"] != "any" else "any"
                loaded.append(PolicyRule(
                    id=rd["id"], level=level, verdict=Verdict(rd["verdict"]),
                    reason=rd["reason"],
                    when_dry_run=rd.get("when_dry_run", False),
                    requires_legal_ack=rd.get("requires_legal_ack", False),
                ))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid rule {rd.get('id')}: {e}")

        if loaded:
            new_ids = {r.id for r in loaded}
            self._rules = [r for r in self._rules if r.id not in new_ids] + loaded

        self._device_overrides = data.get("device_overrides", {}) if isinstance(data, dict) else {}
        logger.info(f"Policy: loaded {len(loaded)} rules from {path}")
        return len(loaded)

    def rules(self) -> list[PolicyRule]:
        return list(self._rules)

    def evaluate(self, level: ActionLevel, ctx: PolicyContext) -> PolicyDecision:
        logger.debug(f"Policy evaluate: level={level.value} ctx={ctx}")

        # Dry-run gates
        if ctx.dry_run:
            for rule in self._rules:
                if rule.when_dry_run and rule.matches_level(level) and rule.verdict == Verdict.DENY:
                    return self._decide(Verdict.DENY, rule.reason, rule.id)

        # Legal acknowledgment
        if not ctx.operator_acknowledged_legal:
            for rule in self._rules:
                if rule.requires_legal_ack and rule.matches_level(level) and rule.verdict == Verdict.DENY:
                    return self._decide(Verdict.DENY, rule.reason, rule.id)

        # Device-specific overrides
        if ctx.device_profile_id and ctx.action_id:
            override = self._device_overrides.get(ctx.device_profile_id, {}).get(ctx.action_id)
            if override:
                return self._decide(
                    Verdict(override["verdict"]), override["reason"],
                    f"override:{ctx.device_profile_id}:{ctx.action_id}",
                )

        # First matching rule
        for rule in self._rules:
            if rule.when_dry_run or rule.requires_legal_ack:
                continue
            if not rule.matches_level(level):
                continue
            return self._decide(rule.verdict, rule.reason, rule.id)

        # Fallback
        for rule in self._rules:
            if rule.level == "any":
                return self._decide(rule.verdict, rule.reason, rule.id)
        return self._decide(Verdict.DENY, "No matching rule.", "R000")

    def _decide(self, verdict: Verdict, reason: str, rule_id: str) -> PolicyDecision:
        decision = PolicyDecision(verdict=verdict, reason=reason, rule_id=rule_id)
        logger.debug(f"Policy decision: {verdict.value} — [{rule_id}] {reason}")
        return decision

    def enforce(self, level: ActionLevel, ctx: PolicyContext) -> PolicyDecision:
        decision = self.evaluate(level, ctx)
        if decision.verdict == Verdict.DENY:
            if self.bus:
                self.bus.publish("policy.violation", data={
                    "level": level.value, "rule_id": decision.rule_id,
                    "reason": decision.reason, "action_id": ctx.action_id,
                    "device_serial": ctx.device_serial,
                }, source="zenith.policy")
            raise PolicyViolationError(f"[{decision.rule_id}] {decision.reason}")
        if self.bus:
            self.bus.publish("policy.enforced", data={
                "level": level.value, "verdict": decision.verdict.value,
                "rule_id": decision.rule_id, "action_id": ctx.action_id,
            }, source="zenith.policy")
        return decision

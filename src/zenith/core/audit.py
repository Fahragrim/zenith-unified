"""Append-only, hash-chained audit log.

Every event is chained to the previous via SHA-256. Tampering is detectable
through verify_chain(). Designed for destructive/forensic operation logging.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from zenith.core.event_bus import Event as BusEvent
from zenith.core.event_bus import EventBus as BusType

GENESIS_HASH = "0" * 64

TOPIC_LEVEL_MAP: dict[str, str] = {
    "flash.": "destructive",
    "recovery.playbook": "write",
    "policy.violation": "read",
    "consent.": "read",
    "device.detected": "read",
    "diagnostics.": "read",
    "runner.command": "write",
}


def _infer_level(topic: str) -> str:
    for prefix, level in TOPIC_LEVEL_MAP.items():
        if topic.startswith(prefix):
            return level
    return "read"


def _canonical_json(entry: dict[str, Any]) -> bytes:
    return json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


@dataclass
class AuditEntry:
    seq: int
    timestamp: str
    topic: str
    source: str
    action_level: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    device_id: str = ""
    device_serial: str = ""
    operator: str = ""
    correlation_id: str = ""
    prev_hash: str = GENESIS_HASH
    hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = {
            "seq": self.seq, "timestamp": self.timestamp, "topic": self.topic,
            "source": self.source, "action_level": self.action_level,
            "summary": self.summary, "data": self.data,
            "device_id": self.device_id, "device_serial": self.device_serial,
            "operator": self.operator, "correlation_id": self.correlation_id,
            "prev_hash": self.prev_hash,
        }
        # hash is computed separately, not part of the content
        result["hash"] = self.hash
        return result

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AuditEntry:
        return cls(
            seq=d["seq"], timestamp=d["timestamp"], topic=d["topic"],
            source=d["source"], action_level=d["action_level"],
            summary=d["summary"], data=d.get("data", {}),
            device_id=d.get("device_id", ""), device_serial=d.get("device_serial", ""),
            operator=d.get("operator", ""), correlation_id=d.get("correlation_id", ""),
            prev_hash=d.get("prev_hash", GENESIS_HASH), hash=d.get("hash", ""),
        )


def _compute_hash(entry: AuditEntry, prev_hash: str) -> str:
    d = entry.to_dict()
    d["prev_hash"] = prev_hash
    if "hash" in d:
        del d["hash"]
    return hashlib.sha256(_canonical_json(d)).hexdigest()


def _make_summary(topic: str, data: dict[str, Any]) -> str:
    if topic.startswith("flash."):
        return f"{data.get('kind', 'op')} {data.get('partition', '?')}"
    if topic.startswith("recovery."):
        return f"playbook {data.get('playbook_id', '?')} — {data.get('success', 'running')}"
    if topic.startswith("policy."):
        return f"[{data.get('rule_id', '?')}] {data.get('verdict', '?')}: {data.get('reason', '?')}"
    if topic.startswith("consent."):
        return f"{topic.split('.')[-1]} for {data.get('title', '?')}"
    if topic.startswith("device."):
        return f"{topic.split('.')[-1]} {data.get('serial', '?')}"
    if topic.startswith("runner.command"):
        return f"exit={data.get('returncode', '?')}"
    if topic.startswith("diagnostics."):
        return f"snapshot {data.get('device_id', '?')}"
    return topic


class AuditLog:
    """Append-only, hash-chained audit log."""

    def __init__(self, path: str | Path = "data/audit.jsonl") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._seq: int = 0
        self._last_hash: str = GENESIS_HASH
        self._load_state()

    def _load_state(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            return
        with self._lock:
            last_line: str | None = None
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f:
                        last_line = line
            except (OSError, UnicodeDecodeError):
                pass
            if last_line:
                try:
                    d = json.loads(last_line)
                    self._seq = d.get("seq", 0)
                    self._last_hash = d.get("hash", GENESIS_HASH)
                except (json.JSONDecodeError, KeyError):
                    pass

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def record(
        self,
        topic: str,
        source: str = "unknown",
        *,
        data: dict[str, Any] | None = None,
        device_serial: str = "",
        operator: str = "",
        correlation_id: str = "",
    ) -> AuditEntry:
        with self._lock:
            entry = AuditEntry(
                seq=self._next_seq(),
                timestamp=datetime.now(timezone.utc).isoformat(),
                topic=topic,
                source=source,
                action_level=_infer_level(topic),
                summary=_make_summary(topic, data or {}),
                data=data or {},
                device_serial=device_serial,
                operator=operator,
                correlation_id=correlation_id,
                prev_hash=self._last_hash,
            )
            entry.hash = _compute_hash(entry, entry.prev_hash)
            self._write(entry)
            logger.debug(f"Audit: [{entry.seq}] {topic} — {entry.action_level}")
        return entry

    def _write(self, entry: AuditEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        self._last_hash = entry.hash

    def verify_chain(self) -> bool:
        with self._lock:
            if not self.path.exists():
                return True
            prev_hash = GENESIS_HASH
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    f.seek(0)
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        d = json.loads(line)
                        expected_prev = d.get("prev_hash", GENESIS_HASH)
                        if expected_prev != prev_hash:
                            logger.error(f"Audit chain broken at line {line_num}: prev_hash mismatch")
                            return False
                        expected_hash = d.pop("hash", "")
                        d["prev_hash"] = prev_hash
                        computed = hashlib.sha256(_canonical_json(d)).hexdigest()
                        if computed != expected_hash:
                            logger.error(f"Audit chain broken at line {line_num}: hash mismatch")
                            return False
                        prev_hash = d["hash"] = expected_hash
                return True
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Audit verify failed: {e}")
                return False

    def query(
        self,
        *,
        device_serial: str | None = None,
        action_level: str | None = None,
        topic_prefix: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        results: list[AuditEntry] = []
        with self._lock:
            if not self.path.exists():
                return results
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        d = json.loads(line)
                        entry = AuditEntry.from_dict(d)
                        if device_serial and entry.device_serial != device_serial:
                            continue
                        if action_level and entry.action_level != action_level:
                            continue
                        if topic_prefix and not entry.topic.startswith(topic_prefix):
                            continue
                        results.append(entry)
            except (OSError, json.JSONDecodeError):
                pass
        return results[-limit:]

    def stats(self) -> dict[str, int]:
        stats: dict[str, int] = {}
        with self._lock:
            if not self.path.exists():
                return stats
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        d = json.loads(line)
                        level = d.get("action_level", "unknown")
                        stats[level] = stats.get(level, 0) + 1
                        topic = d.get("topic", "unknown").split(".")[0]
                        stats[f"topic:{topic}"] = stats.get(f"topic:{topic}", 0) + 1
            except (OSError, json.JSONDecodeError):
                pass
        return stats

    def tail(self, n: int = 20) -> list[AuditEntry]:
        return self.query(limit=n)

    def subscribe_to_bus(self, bus: BusType) -> None:
        def on_event(event: BusEvent) -> None:
            self.record(
                event.topic, source=event.source, data=event.data if isinstance(event.data, dict) else None,
                correlation_id=event.correlation_id or "",
            )
        bus.subscribe("*", on_event)
        logger.info("AuditLog subscribed to EventBus wildcard")

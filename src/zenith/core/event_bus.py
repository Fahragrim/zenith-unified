"""Async pub/sub EventBus for inter-component communication.

All communication between core, engines, adapters, and UI flows through this bus.
UI-agnostic. Thread-safe. Supports wildcard subscriptions.

Topics are dotted strings: "device.detected", "flash.progress", "consent.required", etc.
"""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypeAlias

from loguru import logger

Subscriber: TypeAlias = Callable[["Event"], Awaitable[None] | None]


@dataclass(frozen=True)
class Event:
    """Immutable event payload."""

    topic: str
    data: Any = None
    source: str = "unknown"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str | None = None


class EventBus:
    """Thread-safe async pub/sub event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)
        self._lock = threading.RLock()
        self._history: list[Event] = []
        self._history_max: int = 1000

    def subscribe(self, topic: str, fn: Subscriber) -> None:
        """Register a callback for a topic. Use '*' for all events."""
        with self._lock:
            self._subscribers[topic].append(fn)
            logger.debug(f"Subscribed '{topic}': {getattr(fn, '__qualname__', str(fn))}")

    def unsubscribe(self, topic: str, fn: Subscriber) -> None:
        with self._lock:
            subscribers = self._subscribers.get(topic, [])
            if fn in subscribers:
                subscribers.remove(fn)
                logger.debug(f"Unsubscribed '{topic}': {getattr(fn, '__qualname__', str(fn))}")

    def publish(
        self,
        topic: str,
        data: Any = None,
        *,
        source: str = "unknown",
        correlation_id: str | None = None,
    ) -> Event:
        """Publish synchronously. Calls subscribers inline."""
        event = Event(topic=topic, data=data, source=source, correlation_id=correlation_id)
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_max:
                self._history = self._history[-self._history_max:]
            targets = list(self._subscribers.get(topic, [])) + list(self._subscribers.get("*", []))

        for fn in targets:
            try:
                result = fn(event)
                if asyncio.iscoroutine(result):
                    self._schedule_async(result)
            except Exception:
                logger.exception(f"Subscriber failed for topic={topic}")
        return event

    async def publish_async(
        self,
        topic: str,
        data: Any = None,
        *,
        source: str = "unknown",
        correlation_id: str | None = None,
    ) -> Event:
        """Publish and await all async subscribers."""
        event = Event(topic=topic, data=data, source=source, correlation_id=correlation_id)
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_max:
                self._history = self._history[-self._history_max:]
            targets = list(self._subscribers.get(topic, [])) + list(self._subscribers.get("*", []))

        for fn in targets:
            try:
                result = fn(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception(f"Async subscriber failed for topic={topic}")
        return event

    @staticmethod
    def _schedule_async(coro: Awaitable[None]) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_ensure_coro(coro))
        except RuntimeError:
            asyncio.run(_ensure_coro(coro))

    def history(self, topic: str | None = None, limit: int = 50) -> list[Event]:
        """Return recent events, optionally filtered by topic prefix."""
        with self._lock:
            events = list(self._history)
        if topic:
            events = [e for e in events if e.topic == topic or e.topic.startswith(topic + ".")]
        return events[-limit:]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._subscribers.values())


async def _ensure_coro(aw: Awaitable[None]) -> None:
    await aw


# Module-level singleton
_default_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get or create the default event bus singleton."""
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus

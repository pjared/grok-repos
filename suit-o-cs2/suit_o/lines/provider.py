"""Choose a line for an event.

``LineProvider`` is the seam a future AI backend can implement. v1 ships
``YamlLineProvider``, which reads a stock lines file and applies mute,
per-event cooldowns, a global rate limit, priority bypass for big moments,
and a no-immediate-repeat pick.
"""

from __future__ import annotations

import random
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from suit_o.models import VISIBLE_CONTEXT_KEYS, EventType, GameEvent

_DEFAULT_CONTEXT = {
    "map": "this map",
    "money": "some",
    "health": "low",
    "round_kills": "some",
    "team": "your",
}


class LineProvider:
    """Interface for turning a game event into one spoken line.

    ``select`` returns None when Suit-O should stay quiet. Implementations
    must not inspect raw GSI payloads; the event context is limited to HUD
    fields the player can already see.
    """

    def select(self, event: GameEvent, now: float) -> str | None:  # pragma: no cover - interface
        raise NotImplementedError


class YamlLineProvider(LineProvider):
    """Stock lines from YAML, with cooldown, rate limit, and no immediate repeats."""

    def __init__(
        self,
        lines: Mapping[str, Sequence[str]],
        *,
        cooldowns: Mapping[str, float] | None = None,
        default_cooldown: float = 0.0,
        min_interval: float = 0.0,
        preempt_min_priority: int = 70,
        muted: bool = False,
        rng: random.Random | None = None,
    ) -> None:
        self._lines: dict[str, list[str]] = {
            str(key): [str(line) for line in value] for key, value in lines.items()
        }
        self._cooldowns = dict(cooldowns or {})
        self._default_cooldown = default_cooldown
        self._min_interval = min_interval
        self._preempt_min_priority = preempt_min_priority
        self.muted = muted
        self._rng = rng or random.Random()
        self._last_at: dict[str, float] = {}
        self._last_global: float | None = None
        self._last_line: dict[str, str] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        cooldowns: Mapping[str, float],
        default_cooldown: float,
        min_interval: float,
        preempt_min_priority: int,
        muted: bool = False,
        rng: random.Random | None = None,
    ) -> YamlLineProvider:
        loaded = load_lines(path)
        return cls(
            loaded,
            cooldowns=cooldowns,
            default_cooldown=default_cooldown,
            min_interval=min_interval,
            preempt_min_priority=preempt_min_priority,
            muted=muted,
            rng=rng,
        )

    def lines_for(self, event_type: EventType) -> list[str]:
        return list(self._lines.get(event_type.value, []))

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            self.muted = muted

    def select(self, event: GameEvent, now: float) -> str | None:
        with self._lock:
            return self._select(event, now)

    def _select(self, event: GameEvent, now: float) -> str | None:
        if self.muted:
            return None
        key = event.type.value
        pool = self._lines.get(key) or []
        if not pool:
            return None
        last_at = self._last_at.get(key)
        cooldown = self._cooldowns.get(key, self._default_cooldown)
        if last_at is not None and now - last_at < cooldown:
            return None
        if event.priority < self._preempt_min_priority:
            if self._last_global is not None and now - self._last_global < self._min_interval:
                return None
        choice = self._pick(key, pool)
        self._last_at[key] = now
        self._last_global = now
        self._last_line[key] = choice
        return _render(choice, event.context)

    def _pick(self, key: str, pool: list[str]) -> str:
        previous = self._last_line.get(key)
        choices = [line for line in pool if line != previous] or list(pool)
        return self._rng.choice(choices)


def load_lines(path: Path) -> dict[str, list[str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Lines file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict) or not isinstance(raw.get("events"), dict):
        raise ValueError(f"{path} must contain an 'events' mapping")
    lines: dict[str, list[str]] = {}
    for name, value in raw["events"].items():
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"events.{name} must be a list of strings")
        lines[str(name)] = value
    return lines


def _render(line: str, context: Mapping[str, object]) -> str:
    safe = dict(_DEFAULT_CONTEXT)
    for key in VISIBLE_CONTEXT_KEYS:
        if key in context and context[key] is not None:
            safe[key] = context[key]
    return line.format_map(safe)

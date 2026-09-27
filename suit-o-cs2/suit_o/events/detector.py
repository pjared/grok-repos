"""Detect match events by diffing successive own-player snapshots.

The first gameplay snapshot is a baseline and emits nothing. Later snapshots
emit an event only on a transition. Stats from a spectated player (a steamid
that does not match provider.steamid) never update the local player's memory.
"""

from __future__ import annotations

from suit_o.config import Thresholds
from suit_o.models import VISIBLE_CONTEXT_KEYS, DetectedEvent, EventType, OwnPlayer, Snapshot

_MULTI_KILL = (
    (5, EventType.ACE),
    (4, EventType.MULTI_KILL_4),
    (3, EventType.MULTI_KILL_3),
    (2, EventType.MULTI_KILL_2),
)


class EventDetector:
    def __init__(self, thresholds: Thresholds) -> None:
        self._thresholds = thresholds
        self._seen = False
        self._map_name: str | None = None
        self._map_phase: str | None = None
        self._round_phase: str | None = None
        self._round_number: int | None = None
        self._bomb: str | None = None
        self._activity: str | None = None
        self._own: OwnPlayer | None = None

    def update(self, snap: Snapshot) -> list[DetectedEvent]:
        if not self._seen:
            self._remember(snap)
            self._seen = True
            return []

        events: list[DetectedEvent] = []
        new_phase = snap.map_phase if snap.map_present else self._map_phase
        if snap.map_present and snap.map_name:
            self._map_name = snap.map_name
        round_changed = (
            snap.map_present
            and snap.round_number is not None
            and self._round_number is not None
            and snap.round_number != self._round_number
        )

        if new_phase == "warmup" and self._map_phase != "warmup":
            events.append(self._event(EventType.WARMUP))
        if new_phase == "live" and self._map_phase not in {"live", "intermission"}:
            events.append(self._event(EventType.MATCH_START))
        if new_phase == "gameover" and self._map_phase != "gameover":
            events.append(self._event(EventType.MATCH_END))

        if snap.own is not None:
            merged = _merge_own(self._own, snap.own)
            if merged.activity == "menu" and self._activity != "menu":
                events.append(self._event(EventType.IDLE, merged))
            events.extend(self._combat_events(self._own, merged, round_changed))
            self._own = merged
            self._activity = merged.activity

        phase_for_round = new_phase
        if phase_for_round == "live":
            events.extend(self._round_events(snap, round_changed))
            events.extend(self._bomb_events(snap))

        if snap.map_present:
            self._map_phase = new_phase
            if snap.round_number is not None:
                self._round_number = snap.round_number
        if snap.round_present:
            self._round_phase = snap.round_phase
        if snap.bomb_known:
            self._bomb = snap.bomb
        return events

    def _round_events(self, snap: Snapshot, round_changed: bool) -> list[DetectedEvent]:
        if not snap.round_present:
            return []
        events: list[DetectedEvent] = []
        new_round_phase = snap.round_phase
        entered_freeze = new_round_phase == "freezetime" and (
            self._round_phase != "freezetime" or round_changed
        )
        if entered_freeze:
            money = _money(snap, self._own)
            team = _team(snap, self._own)
            if money is not None and money < self._thresholds.full_buy_money(team):
                events.append(self._event(EventType.BUY_LOW_MONEY, self._own_after(snap)))
            else:
                events.append(self._event(EventType.ROUND_FREEZETIME, self._own_after(snap)))

        entered_over = new_round_phase == "over" and self._round_phase != "over"
        if entered_over:
            winner = snap.win_team
            team = _team(snap, self._own)
            if winner in {"CT", "T"} and team in {"CT", "T"}:
                kind = EventType.ROUND_WON if winner == team else EventType.ROUND_LOST
                events.append(self._event(kind, self._own_after(snap)))
        return events

    def _bomb_events(self, snap: Snapshot) -> list[DetectedEvent]:
        if not snap.bomb_known or snap.bomb == self._bomb:
            return []
        kind = {
            "planted": EventType.BOMB_PLANTED,
            "defused": EventType.BOMB_DEFUSED,
            "exploded": EventType.BOMB_EXPLODED,
        }.get(snap.bomb or "")
        if kind is None:
            return []
        return [self._event(kind, self._own_after(snap))]

    def _combat_events(
        self,
        previous: OwnPlayer | None,
        current: OwnPlayer,
        round_changed: bool,
    ) -> list[DetectedEvent]:
        events: list[DetectedEvent] = []
        if previous is None:
            return events

        new_kills = current.round_kills
        new_hs = current.round_killhs
        kills_reset = round_changed or (
            previous.round_kills is not None
            and new_kills is not None
            and new_kills < previous.round_kills
        )
        old_kills = 0 if kills_reset or previous.round_kills is None else previous.round_kills
        old_hs = 0 if kills_reset or previous.round_killhs is None else previous.round_killhs
        if new_kills is not None and new_kills > old_kills:
            kill_delta = new_kills - old_kills
            hs_delta = 0
            if new_hs is not None:
                hs_delta = max(0, new_hs - old_hs)
                hs_delta = min(hs_delta, kill_delta)
            if hs_delta > 0:
                events.append(self._event(EventType.HEADSHOT_KILL, current))
            if kill_delta > hs_delta:
                events.append(self._event(EventType.KILL, current))
            for threshold, kind in _MULTI_KILL:
                if old_kills < threshold <= new_kills:
                    events.append(self._event(kind, current))
                    break

        respawned = (
            previous.health == 0 and current.health is not None and current.health > 0
        )
        if round_changed or kills_reset or respawned:
            return events

        prev_health = previous.health
        health = current.health
        if (
            prev_health is not None
            and health is not None
            and health < prev_health
            and 0 < health <= self._thresholds.low_health
        ):
            events.append(self._event(EventType.LOW_HEALTH, current))

        died = False
        if prev_health is not None and prev_health > 0 and health == 0:
            died = True
        prev_deaths = previous.deaths
        deaths = current.deaths
        if (
            not died
            and prev_deaths is not None
            and deaths is not None
            and deaths > prev_deaths
            and health in {0, None}
        ):
            died = True
        if died:
            events.append(self._event(EventType.DEATH, current))
        return events

    def _remember(self, snap: Snapshot) -> None:
        if snap.map_present:
            self._map_phase = snap.map_phase
            self._map_name = snap.map_name
            if snap.round_number is not None:
                self._round_number = snap.round_number
        if snap.round_present:
            self._round_phase = snap.round_phase
        if snap.bomb_known:
            self._bomb = snap.bomb
        if snap.own is not None:
            self._own = snap.own
            self._activity = snap.own.activity

    def _own_after(self, snap: Snapshot) -> OwnPlayer | None:
        if snap.own is None:
            return self._own
        return _merge_own(self._own, snap.own)

    def _event(self, kind: EventType, own: OwnPlayer | None = None) -> DetectedEvent:
        source = own if own is not None else self._own
        return DetectedEvent(type=kind, context=_context(self._map_name, source))


def _merge_own(previous: OwnPlayer | None, incoming: OwnPlayer) -> OwnPlayer:
    if previous is None:
        return incoming
    return OwnPlayer(
        steamid=incoming.steamid,
        activity=incoming.activity if incoming.activity is not None else previous.activity,
        team=incoming.team if incoming.team is not None else previous.team,
        health=incoming.health if incoming.health is not None else previous.health,
        money=incoming.money if incoming.money is not None else previous.money,
        round_kills=(
            incoming.round_kills if incoming.round_kills is not None else previous.round_kills
        ),
        round_killhs=(
            incoming.round_killhs if incoming.round_killhs is not None else previous.round_killhs
        ),
        deaths=incoming.deaths if incoming.deaths is not None else previous.deaths,
    )


def _money(snap: Snapshot, own: OwnPlayer | None) -> int | None:
    if snap.own is not None and snap.own.money is not None:
        return snap.own.money
    if own is not None:
        return own.money
    return None


def _team(snap: Snapshot, own: OwnPlayer | None) -> str | None:
    if snap.own is not None and snap.own.team is not None:
        return snap.own.team
    if own is not None:
        return own.team
    return None


def _context(map_name: str | None, own: OwnPlayer | None) -> dict[str, object]:
    raw: dict[str, object] = {}
    if map_name:
        raw["map"] = map_name
    if own is not None:
        if own.money is not None:
            raw["money"] = own.money
        if own.health is not None:
            raw["health"] = own.health
        if own.round_kills is not None:
            raw["round_kills"] = own.round_kills
        if own.team is not None:
            raw["team"] = own.team
    return {key: raw[key] for key in VISIBLE_CONTEXT_KEYS if key in raw}

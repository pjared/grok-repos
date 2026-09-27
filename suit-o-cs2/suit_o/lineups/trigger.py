"""When the lineup overlay is allowed to be on screen.

The decision uses the latest GSI snapshot only: map, side, the weapon in
hand, health, and round phase. It does not know about pixels, hotkey APIs,
or the game process. Practice-server setpos text is never part of this decision
and is never sent to CS2.
"""

from __future__ import annotations

from dataclasses import dataclass

from suit_o.models import Snapshot

# Longer needles first so "smokegrenade" is not confused with a shorter token.
_GRENADES = (
    ("smokegrenade", "smoke"),
    ("flashbang", "flash"),
    ("incgrenade", "molotov"),
    ("incendiary", "molotov"),
    ("molotov", "molotov"),
    ("hegrenade", "he"),
)


@dataclass(frozen=True)
class OverlayDecision:
    """Whether a lineup card should be on screen, and why not."""

    visible: bool
    map_key: str
    side: str
    reason: str
    grenade: str = ""


def held_grenade(name: str | None) -> str | None:
    """Map a GSI weapon name to smoke, flash, molotov, or he.

    ``weapon_incgrenade`` is the CT incendiary and uses the molotov lineups.
    Anything else, including rifles, is not a grenade lineup.
    """

    if not name:
        return None
    token = name.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    for needle, kind in _GRENADES:
        if needle in token:
            return kind
    return None


def is_smoke_grenade(name: str | None) -> bool:
    """True for the CS2 smoke grenade name. Other grenades are not smokes."""

    return held_grenade(name) == "smoke"


def is_alive(health: int | None) -> bool:
    """A missing health value is not treated as alive."""

    return health is not None and health > 0


def decide_overlay(
    *,
    map_key: str,
    side: str,
    active_weapon: str | None,
    health: int | None,
    round_phase: str | None,
    user_hidden: bool,
    enabled: bool = True,
) -> OverlayDecision:
    """Show a card while a living player holds a smoke, flash, molotov, or HE."""

    key = map_key.strip().lower()
    team = side.strip().lower()
    grenade = held_grenade(active_weapon) or ""

    def hidden(reason: str) -> OverlayDecision:
        return OverlayDecision(False, key, team, reason, grenade)

    if not enabled:
        return hidden("disabled")
    if user_hidden:
        return hidden("hidden")
    if not grenade:
        return hidden("not-grenade")
    if not is_alive(health):
        return hidden("dead")
    if (round_phase or "").strip().lower() == "over":
        return hidden("round-over")
    if not key:
        return hidden("no-map")
    if team not in {"t", "ct"}:
        return hidden("no-side")
    return OverlayDecision(True, key, team, grenade, grenade)


def decision_from_snapshot(
    snapshot: Snapshot | None,
    *,
    user_hidden: bool,
    enabled: bool = True,
    map_key: str = "",
    side: str = "",
    active_weapon: str | None = None,
    health: int | None = None,
    round_phase: str | None = None,
) -> OverlayDecision:
    """Fill blanks from ``snapshot`` and evaluate the trigger.

    Callers pass the remembered fields. A section missing from this payload
    does not erase them, because GSI sometimes omits a block it already sent.
    """

    if snapshot is not None:
        if snapshot.map_present and snapshot.map_token:
            map_key = snapshot.map_token
        if snapshot.round_present and snapshot.round_phase is not None:
            round_phase = snapshot.round_phase
        own = snapshot.own
        if own is not None:
            if own.team in {"T", "CT"}:
                side = own.team.lower()
            if own.health is not None:
                health = own.health
            if own.weapons_seen:
                active_weapon = own.active_weapon
    return decide_overlay(
        map_key=map_key,
        side=side,
        active_weapon=active_weapon,
        health=health,
        round_phase=round_phase,
        user_hidden=user_hidden,
        enabled=enabled,
    )

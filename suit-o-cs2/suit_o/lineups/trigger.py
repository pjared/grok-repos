"""When the smoke overlay is allowed to be on screen.

The decision uses the latest GSI snapshot only: map, side, the weapon in
hand, health, and round phase. It does not know about pixels, hotkey APIs,
or the game process.
"""

from __future__ import annotations

from dataclasses import dataclass

from suit_o.models import Snapshot

_SMOKE_NAMES = {"weapon_smokegrenade", "smokegrenade"}


@dataclass(frozen=True)
class OverlayDecision:
    """Whether a lineup card should be on screen, and why not."""

    visible: bool
    map_key: str
    side: str
    reason: str


def is_smoke_grenade(name: str | None) -> bool:
    """True for the CS2 smoke grenade name. Other grenades are not smokes."""

    if not name:
        return False
    token = name.strip().lower().replace(" ", "").replace("-", "")
    if token in _SMOKE_NAMES:
        return True
    return token.endswith("smokegrenade")


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
    """Show a card only while a living player is holding a smoke in a live round."""

    key = map_key.strip().lower()
    team = side.strip().lower()
    if not enabled:
        return OverlayDecision(False, key, team, "disabled")
    if user_hidden:
        return OverlayDecision(False, key, team, "hidden")
    if not is_smoke_grenade(active_weapon):
        return OverlayDecision(False, key, team, "not-smoke")
    if not is_alive(health):
        return OverlayDecision(False, key, team, "dead")
    if (round_phase or "").strip().lower() == "over":
        return OverlayDecision(False, key, team, "round-over")
    if not key:
        return OverlayDecision(False, key, team, "no-map")
    if team not in {"t", "ct"}:
        return OverlayDecision(False, key, team, "no-side")
    return OverlayDecision(True, key, team, "smoke")


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

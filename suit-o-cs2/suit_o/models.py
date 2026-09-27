"""Shared types for game snapshots, detected events, and spoken lines."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    """Events Suit-O can react to.

    Clutch is intentionally absent. Own-player GSI data does not include a
    reliable count of alive teammates, and Suit-O does not subscribe to
    all-player data.
    """

    MATCH_START = "match_start"
    MATCH_END = "match_end"
    WARMUP = "warmup"
    IDLE = "idle"
    ROUND_FREEZETIME = "round_freezetime"
    BUY_LOW_MONEY = "buy_low_money"
    BOMB_PLANTED = "bomb_planted"
    BOMB_DEFUSED = "bomb_defused"
    BOMB_EXPLODED = "bomb_exploded"
    LOW_HEALTH = "low_health"
    KILL = "kill"
    HEADSHOT_KILL = "headshot_kill"
    MULTI_KILL_2 = "multi_kill_2"
    MULTI_KILL_3 = "multi_kill_3"
    MULTI_KILL_4 = "multi_kill_4"
    ACE = "ace"
    DEATH = "death"
    ROUND_WON = "round_won"
    ROUND_LOST = "round_lost"


# Spoken lines may only interpolate these. They are all on the player's HUD.
VISIBLE_CONTEXT_KEYS = ("map", "money", "health", "round_kills", "team")


@dataclass(frozen=True)
class OwnPlayer:
    """Last observed state for the local player, never a spectated teammate."""

    steamid: str
    activity: str | None = None
    team: str | None = None
    health: int | None = None
    money: int | None = None
    round_kills: int | None = None
    round_killhs: int | None = None
    deaths: int | None = None
    # Name of the weapon currently in hand, such as weapon_smokegrenade.
    # The rest of the inventory is not stored.
    active_weapon: str | None = None
    weapons_seen: bool = False


@dataclass(frozen=True)
class Snapshot:
    """One GSI payload, reduced to fields Suit-O is allowed to use.

    Bomb coordinates, other players, and the weapon inventory are not stored.
    ``map_token`` is the CS2 map id (``de_dust2``). ``map_name`` is the short
    name used in spoken lines. ``active_weapon`` on ``own`` is only the item
    in hand, so a smoke lineup can be shown without keeping the loadout.
    """

    map_present: bool = False
    map_name: str | None = None
    map_token: str | None = None
    map_phase: str | None = None
    round_present: bool = False
    round_phase: str | None = None
    round_number: int | None = None
    win_team: str | None = None
    bomb_known: bool = False
    bomb: str | None = None
    own: OwnPlayer | None = None


@dataclass(frozen=True)
class DetectedEvent:
    """An event emitted by diffing snapshots. Priority is applied later."""

    type: EventType
    context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GameEvent:
    """A detected event plus the configured priority used for line selection."""

    type: EventType
    priority: int
    context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Utterance:
    """One line handed to the speech backend."""

    event_type: str
    text: str
    priority: int

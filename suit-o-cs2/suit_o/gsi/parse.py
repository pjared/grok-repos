"""Turn a GSI JSON object into a Snapshot.

Only the local player's HUD state, the public round/map phase, and the public
bomb condition (planted, defused, exploded) are kept. Bomb coordinates and
weapon lists are never read, so they cannot leak into lines.
"""

from __future__ import annotations

from suit_o.models import OwnPlayer, Snapshot

_BOMB_CONDITIONS = ("exploded", "defused", "planted")
_BOMB_IGNORE = {"carried", "dropped", "planting", "defusing", "none", ""}


def parse_payload(data: dict) -> Snapshot | None:
    """Parse one GSI body.

    Returns None for heartbeats that carry no game sections. Those must not
    clear the last known match.
    """

    if not isinstance(data, dict):
        return None
    has_game = any(key in data for key in ("map", "round", "player", "bomb"))
    if not has_game:
        return None

    provider = data.get("provider") if isinstance(data.get("provider"), dict) else {}
    provider_steam = _as_str(provider.get("steamid"))

    map_block = data.get("map") if isinstance(data.get("map"), dict) else None
    round_block = data.get("round") if isinstance(data.get("round"), dict) else None
    player_block = data.get("player") if isinstance(data.get("player"), dict) else None
    bomb_known = round_block is not None or isinstance(data.get("bomb"), dict)

    map_name = None
    map_phase = None
    round_number = None
    if map_block is not None:
        map_name = _pretty_map(_as_str(map_block.get("name")))
        map_phase = _lower(map_block.get("phase"))
        round_number = _as_int(map_block.get("round"))

    round_phase = None
    win_team = None
    if round_block is not None:
        round_phase = _lower(round_block.get("phase"))
        win_team = _normalize_team(round_block.get("win_team"))

    own: OwnPlayer | None = None
    if player_block is not None:
        player_steam = _as_str(player_block.get("steamid"))
        if provider_steam and player_steam and player_steam == provider_steam:
            state = player_block.get("state") if isinstance(player_block.get("state"), dict) else {}
            stats = (
                player_block.get("match_stats")
                if isinstance(player_block.get("match_stats"), dict)
                else {}
            )
            # player.weapons is intentionally not read.
            own = OwnPlayer(
                steamid=player_steam,
                activity=_lower(player_block.get("activity")),
                team=_normalize_team(player_block.get("team")),
                health=_as_int(state.get("health")),
                money=_as_int(state.get("money")),
                round_kills=_as_int(state.get("round_kills")),
                round_killhs=_as_int(state.get("round_killhs")),
                deaths=_as_int(stats.get("deaths")),
            )

    return Snapshot(
        map_present=map_block is not None,
        map_name=map_name,
        map_phase=map_phase,
        round_present=round_block is not None,
        round_phase=round_phase,
        round_number=round_number,
        win_team=win_team,
        bomb_known=bomb_known,
        bomb=_bomb_condition(data) if bomb_known else None,
        own=own,
    )


def _bomb_condition(data: dict) -> str | None:
    """Public bomb condition only. Position is never read."""

    found: list[str] = []
    round_block = data.get("round") if isinstance(data.get("round"), dict) else {}
    bomb_block = data.get("bomb") if isinstance(data.get("bomb"), dict) else {}
    for raw in (round_block.get("bomb"), bomb_block.get("state")):
        if not isinstance(raw, str):
            continue
        value = raw.strip().lower()
        if value in _BOMB_IGNORE:
            continue
        if value in _BOMB_CONDITIONS:
            found.append(value)
    for preferred in _BOMB_CONDITIONS:
        if preferred in found:
            return preferred
    return None


def _pretty_map(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = name.strip()
    for prefix in ("de_", "cs_", "ar_"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return cleaned.replace("_", " ")


def _normalize_team(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().upper()
    if token in {"CT", "C"}:
        return "CT"
    if token in {"T", "TERRORIST"}:
        return "T"
    return None


def _lower(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text or None


def _as_str(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("-").isdigit():
            return int(stripped)
    return None

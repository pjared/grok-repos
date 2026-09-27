"""Synthetic GSI payloads shaped like CS2's live feed.

The simulator posts these. Tests build smaller variants with the same helper.
Weapon lists and bomb coordinates can be attached for negative tests; the
parser does not read them.
"""

from __future__ import annotations

LOCAL_STEAM_ID = "76561198000000001"
OTHER_STEAM_ID = "76561198000000002"
DEFAULT_TOKEN = "suito-local-change-me"


def make_payload(
    *,
    token: str = DEFAULT_TOKEN,
    steamid: str = LOCAL_STEAM_ID,
    player_steamid: str | None = None,
    include_player: bool = True,
    include_map: bool = True,
    include_round: bool = True,
    activity: str = "playing",
    team: str = "CT",
    name: str = "Player",
    map_name: str = "de_dust2",
    map_phase: str = "live",
    mode: str = "competitive",
    round_number: int = 1,
    round_phase: str = "live",
    win_team: str | None = None,
    health: int | None = 100,
    money: int | None = 8000,
    round_kills: int | None = 0,
    round_killhs: int | None = 0,
    deaths: int | None = 0,
    kills: int = 0,
    bomb: str | None = None,
    bomb_position: str | None = None,
    weapons: dict | None = None,
    allplayers: dict | None = None,
    timestamp: int = 1,
) -> dict:
    payload: dict = {
        "auth": {"token": token},
        "provider": {
            "name": "Counter-Strike 2",
            "appid": 730,
            "version": 14030,
            "steamid": steamid,
            "timestamp": timestamp,
        },
    }
    if include_map:
        payload["map"] = {
            "mode": mode,
            "name": map_name,
            "phase": map_phase,
            "round": round_number,
            "team_ct": {"score": 0},
            "team_t": {"score": 0},
        }
    if include_round:
        round_block: dict = {"phase": round_phase}
        if win_team:
            round_block["win_team"] = win_team
        if bomb in {"planted", "defused", "exploded"}:
            round_block["bomb"] = bomb
        payload["round"] = round_block
    if bomb is not None or bomb_position is not None:
        bomb_block: dict = {}
        if bomb is not None:
            bomb_block["state"] = bomb
        if bomb_position is not None:
            bomb_block["position"] = bomb_position
        payload["bomb"] = bomb_block
    if include_player:
        state: dict = {}
        if health is not None:
            state["health"] = health
        if money is not None:
            state["money"] = money
        if round_kills is not None:
            state["round_kills"] = round_kills
        if round_killhs is not None:
            state["round_killhs"] = round_killhs
        state["armor"] = 100
        state["helmet"] = True
        player = {
            "steamid": player_steamid or steamid,
            "name": name,
            "team": team,
            "activity": activity,
            "state": state,
            "match_stats": {
                "kills": kills,
                "assists": 0,
                "deaths": 0 if deaths is None else deaths,
                "mvps": 0,
                "score": kills,
            },
        }
        if weapons is not None:
            player["weapons"] = weapons
        payload["player"] = player
    if allplayers is not None:
        payload["allplayers"] = allplayers
    return payload


def heartbeat(token: str = DEFAULT_TOKEN, steamid: str = LOCAL_STEAM_ID) -> dict:
    """Provider keepalive with no game sections. Must not move match state."""

    return {
        "auth": {"token": token},
        "provider": {
            "name": "Counter-Strike 2",
            "appid": 730,
            "version": 14030,
            "steamid": steamid,
            "timestamp": 0,
        },
    }

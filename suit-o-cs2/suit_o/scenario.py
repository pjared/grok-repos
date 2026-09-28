"""Ordered synthetic match used by the simulator.

Each step is a full-enough GSI snapshot. The first gameplay snapshot is only
a baseline. Later steps are transitions that, together, cover every event.
"""

from __future__ import annotations

from suit_o.gsi.payloads import LOCAL_STEAM_ID, heartbeat, make_payload

# Planted on a coordinate the player might not be looking at. Suit-O must
# never speak this string; the bomb beep is public, the position is not.
BOMB_POSITION_SENTINEL = "9999, 8888, 7777"


def build_menu_scenario(token: str, steamid: str = LOCAL_STEAM_ID) -> list[dict]:
    """CS2 already sitting in the main menu. No match is invented.

    The first post is the launch snapshot and should greet once. The second
    is another menu heartbeat and should stay quiet.
    """

    common = {
        "token": token,
        "steamid": steamid,
        "include_map": False,
        "include_round": False,
        "activity": "menu",
        "health": 100,
        "money": 0,
    }
    return [
        make_payload(**common, timestamp=1),
        make_payload(**common, timestamp=2),
    ]


def build_scenario(token: str, steamid: str = LOCAL_STEAM_ID) -> list[dict]:
    common = {"token": token, "steamid": steamid}
    steps: list[dict] = [heartbeat(token, steamid)]

    def add(**kwargs) -> None:
        steps.append(make_payload(**common, timestamp=len(steps), **kwargs))

    # Baseline: already live. No events.
    add(map_phase="live", round_phase="live", round_number=1, money=8000, health=100)
    # Menu. Map block omitted so we do not invent a match end.
    add(include_map=False, include_round=False, activity="menu", health=100, money=8000)
    # Warmup.
    add(map_phase="warmup", round_phase="live", round_number=0, activity="playing", money=8000)
    # Warmup -> live. Match start, not a buy-phase line.
    add(map_phase="live", round_phase="live", round_number=1, money=8000, health=100, round_kills=0)
    # Rich freeze: generic round start.
    add(round_phase="freezetime", round_number=1, money=8000, health=100, round_kills=0)
    add(round_phase="live", round_number=1, money=8000, health=100, round_kills=0, round_killhs=0)
    # Body kill.
    add(round_kills=1, round_killhs=0, health=100, weapons={"weapon_0": {"name": "weapon_m4a1"}})
    # Headshot that is also the second kill.
    add(round_kills=2, round_killhs=1, health=100)
    add(round_kills=3, round_killhs=1, health=100)
    add(round_kills=4, round_killhs=1, health=100)
    add(round_kills=5, round_killhs=1, health=100)
    # Damage into the low-health band.
    add(round_kills=5, round_killhs=1, health=22)
    # Our plant. Only the T side plants, and the position must be ignored.
    add(
        team="T",
        round_kills=5,
        round_killhs=1,
        health=22,
        bomb="planted",
        bomb_position=BOMB_POSITION_SENTINEL,
    )
    add(round_kills=5, round_killhs=1, health=0, deaths=1, bomb="planted")
    # CT player, T win.
    add(
        round_phase="over",
        win_team="T",
        round_kills=5,
        health=0,
        deaths=1,
        bomb=None,
    )
    # Halftime. Coming back to live must not look like a new match.
    add(
        map_phase="intermission",
        round_phase="over",
        round_number=1,
        health=0,
        deaths=1,
        round_kills=5,
        round_killhs=1,
    )
    # New round, pistol money: low-buy line instead of the generic freeze line.
    add(
        round_number=2,
        round_phase="freezetime",
        money=600,
        health=100,
        round_kills=0,
        round_killhs=0,
        deaths=1,
    )
    add(
        round_number=2,
        round_phase="live",
        money=600,
        health=100,
        round_kills=0,
        round_killhs=0,
        deaths=1,
    )
    add(round_number=2, round_phase="live", health=100, round_kills=0, bomb="planted")
    add(
        round_number=2,
        round_phase="over",
        win_team="CT",
        health=100,
        round_kills=0,
        bomb="defused",
    )
    # Round 3, then the bomb explodes and T win the round.
    add(
        round_number=3,
        round_phase="live",
        money=8000,
        health=100,
        round_kills=0,
        round_killhs=0,
        deaths=1,
    )
    add(round_number=3, round_phase="live", health=100, round_kills=0, bomb="planted")
    add(
        round_number=3,
        round_phase="over",
        win_team="T",
        health=80,
        round_kills=0,
        bomb="exploded",
    )
    add(map_phase="gameover", round_phase="over", round_number=3, health=80, round_kills=0)
    # Leave, then finish a second match ahead on the scoreboard.
    add(include_map=False, include_round=False, activity="menu", health=100, money=8000)
    add(map_phase="live", round_phase="live", round_number=1, team="CT", money=8000, health=100)
    add(
        map_phase="gameover",
        round_phase="live",
        round_number=1,
        team="CT",
        health=100,
        round_kills=0,
        ct_score=13,
        t_score=5,
    )
    return steps

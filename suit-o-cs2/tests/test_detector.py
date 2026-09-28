"""Event detection from synthetic GSI snapshots."""

from __future__ import annotations

from suit_o.config import Thresholds
from suit_o.events.detector import EventDetector
from suit_o.gsi.parse import parse_payload
from suit_o.gsi.payloads import OTHER_STEAM_ID, heartbeat, make_payload
from suit_o.models import VISIBLE_CONTEXT_KEYS, EventType
from suit_o.scenario import BOMB_POSITION_SENTINEL, build_scenario


def thresholds() -> Thresholds:
    return Thresholds(
        low_health=30,
        full_buy_money_ct=4100,
        full_buy_money_t=3700,
        full_buy_money_unknown=4000,
    )


def feed(detector: EventDetector, payload: dict):
    snapshot = parse_payload(payload)
    assert snapshot is not None
    return detector.update(snapshot)


def types_of(events) -> list[EventType]:
    return [event.type for event in events]


def test_heartbeat_is_not_a_snapshot():
    assert parse_payload(heartbeat()) is None


def test_parser_drops_position_weapons_and_other_players():
    payload = make_payload(
        bomb="planted",
        bomb_position=BOMB_POSITION_SENTINEL,
        weapons={"weapon_0": {"name": "weapon_awp", "ammo_clip": 5}},
        allplayers={
            "enemy-steamid-marker": {"state": {"health": 12}, "position": "1, 2, 3"}
        },
    )
    snapshot = parse_payload(payload)
    blob = repr(snapshot)
    assert snapshot is not None
    assert snapshot.bomb == "planted"
    assert snapshot.ct_score == 0
    assert snapshot.t_score == 0
    assert "9999" not in blob
    assert "awp" not in blob
    assert "enemy-steamid-marker" not in blob


def test_first_snapshot_is_baseline():
    detector = EventDetector(thresholds())
    assert feed(detector, make_payload()) == []
    assert feed(detector, make_payload()) == []


def test_warmup_idle_match_boundaries():
    detector = EventDetector(thresholds())
    first_menu = feed(detector, make_payload(activity="menu", include_map=False))
    assert types_of(first_menu) == [EventType.MENU_GREETING]
    idle_again = feed(detector, make_payload(activity="menu", include_map=False))
    assert idle_again == []

    warmup = feed(detector, make_payload(map_phase="warmup", activity="playing"))
    assert types_of(warmup) == [EventType.WARMUP]
    assert feed(detector, make_payload(map_phase="warmup", activity="playing")) == []

    started = feed(detector, make_payload(map_phase="live", round_phase="live"))
    assert types_of(started) == [EventType.MATCH_START]

    menu = feed(detector, make_payload(activity="menu", include_map=False, include_round=False))
    assert types_of(menu) == [EventType.IDLE, EventType.MENU_GREETING]
    assert feed(detector, make_payload(activity="menu", include_map=False, include_round=False)) == []


def test_intermission_is_not_a_new_match():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(map_phase="live"))
    half = feed(detector, make_payload(map_phase="intermission"))
    assert types_of(half) == [EventType.HALFTIME]
    assert feed(detector, make_payload(map_phase="intermission")) == []
    assert feed(detector, make_payload(map_phase="live")) == []


def test_match_end_once():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(map_phase="live"))
    ended = feed(detector, make_payload(map_phase="gameover"))
    assert types_of(ended) == [EventType.MATCH_END]
    assert feed(detector, make_payload(map_phase="gameover")) == []


def test_match_won_only_when_our_score_is_higher():
    won = EventDetector(thresholds())
    feed(won, make_payload(team="CT", map_phase="live"))
    assert types_of(feed(won, make_payload(team="CT", map_phase="gameover", ct_score=13, t_score=9))) == [
        EventType.MATCH_WON
    ]

    other_side = EventDetector(thresholds())
    feed(other_side, make_payload(team="T", map_phase="live"))
    assert types_of(
        feed(other_side, make_payload(team="T", map_phase="gameover", ct_score=8, t_score=13))
    ) == [EventType.MATCH_WON]

    lost = EventDetector(thresholds())
    feed(lost, make_payload(team="CT", map_phase="live"))
    assert types_of(feed(lost, make_payload(team="CT", map_phase="gameover", ct_score=5, t_score=13))) == [
        EventType.MATCH_END
    ]

    tied = EventDetector(thresholds())
    feed(tied, make_payload(team="CT", map_phase="live"))
    assert types_of(feed(tied, make_payload(team="CT", map_phase="gameover", ct_score=12, t_score=12))) == [
        EventType.MATCH_END
    ]

    missing = EventDetector(thresholds())
    feed(missing, make_payload(team="CT", map_phase="live"))
    payload = make_payload(team="CT", map_phase="gameover")
    del payload["map"]["team_ct"]
    del payload["map"]["team_t"]
    assert types_of(feed(missing, payload)) == [EventType.MATCH_END]


def test_freeze_versus_low_buy_and_team_thresholds():
    rich = EventDetector(thresholds())
    feed(rich, make_payload(team="CT", money=8000, round_phase="live"))
    freeze = feed(rich, make_payload(team="CT", money=8000, round_phase="freezetime"))
    assert types_of(freeze) == [EventType.ROUND_FREEZETIME]
    assert feed(rich, make_payload(team="CT", money=8000, round_phase="freezetime")) == []

    ct_short = EventDetector(thresholds())
    feed(ct_short, make_payload(team="CT", money=4000, round_phase="live"))
    assert types_of(feed(ct_short, make_payload(team="CT", money=4000, round_phase="freezetime"))) == [
        EventType.BUY_LOW_MONEY
    ]

    ct_exact = EventDetector(thresholds())
    feed(ct_exact, make_payload(team="CT", money=4100, round_phase="live"))
    assert types_of(feed(ct_exact, make_payload(team="CT", money=4100, round_phase="freezetime"))) == [
        EventType.ROUND_FREEZETIME
    ]

    terrorist_ok = EventDetector(thresholds())
    feed(terrorist_ok, make_payload(team="T", money=3800, round_phase="live"))
    assert types_of(
        feed(terrorist_ok, make_payload(team="T", money=3800, round_phase="freezetime"))
    ) == [EventType.ROUND_FREEZETIME]

    terrorist_short = EventDetector(thresholds())
    feed(terrorist_short, make_payload(team="T", money=3600, round_phase="live"))
    bought = feed(terrorist_short, make_payload(team="T", money=3600, round_phase="freezetime"))
    assert types_of(bought) == [EventType.BUY_LOW_MONEY]
    assert bought[0].context["money"] == 3600


def test_warmup_freeze_does_not_announce_a_buy():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(map_phase="live", round_phase="live", money=500))
    events = feed(
        detector,
        make_payload(map_phase="warmup", round_phase="freezetime", money=500),
    )
    assert EventType.BUY_LOW_MONEY not in types_of(events)
    assert EventType.ROUND_FREEZETIME not in types_of(events)
    assert EventType.WARMUP in types_of(events)


def test_new_round_freeze_fires_again():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(round_number=1, round_phase="freezetime", money=8000))
    assert feed(detector, make_payload(round_number=1, round_phase="freezetime", money=8000)) == []
    again = feed(detector, make_payload(round_number=2, round_phase="freezetime", money=8000))
    assert types_of(again) == [EventType.ROUND_FREEZETIME]


def test_bomb_transitions_ignore_position_and_planting():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(round_phase="live"))
    assert feed(detector, make_payload(bomb="planting")) == []
    assert feed(detector, make_payload(bomb="dropped")) == []

    planted = feed(
        detector,
        make_payload(bomb="planted", bomb_position=BOMB_POSITION_SENTINEL),
    )
    assert types_of(planted) == [EventType.BOMB_PLANTED]
    assert "9999" not in repr(planted[0].context)
    assert set(planted[0].context) <= set(VISIBLE_CONTEXT_KEYS)
    assert feed(detector, make_payload(bomb="planted", bomb_position=BOMB_POSITION_SENTINEL)) == []

    defused = feed(detector, make_payload(bomb="defused", round_phase="over", win_team="CT"))
    assert EventType.BOMB_DEFUSED in types_of(defused)
    assert EventType.ROUND_WON in types_of(defused)

    detector = EventDetector(thresholds())
    feed(detector, make_payload(team="CT", round_phase="live"))
    feed(detector, make_payload(team="CT", bomb="planted"))
    exploded = feed(
        detector,
        make_payload(team="CT", bomb="exploded", round_phase="over", win_team="T"),
    )
    assert EventType.BOMB_EXPLODED in types_of(exploded)
    assert EventType.ROUND_LOST in types_of(exploded)


def test_our_plant_is_the_t_side_and_a_missing_team_is_not():
    us = EventDetector(thresholds())
    feed(us, make_payload(team="T", round_phase="live"))
    assert types_of(feed(us, make_payload(team="T", bomb="planted"))) == [EventType.BOMB_PLANTED_US]

    unknown = EventDetector(thresholds())
    feed(unknown, make_payload(team="", round_phase="live"))
    assert types_of(feed(unknown, make_payload(team="", bomb="planted"))) == [EventType.BOMB_PLANTED]


def test_kills_headshots_and_highest_multikill_only():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(round_kills=0, round_killhs=0))

    body = feed(detector, make_payload(round_kills=1, round_killhs=0))
    assert types_of(body) == [EventType.KILL]

    hs = feed(detector, make_payload(round_kills=2, round_killhs=1))
    assert set(types_of(hs)) == {EventType.MULTI_KILL_2, EventType.HEADSHOT_KILL}

    missing_hs = EventDetector(thresholds())
    feed(missing_hs, make_payload(round_kills=0, round_killhs=0))
    body_only = feed(missing_hs, make_payload(round_kills=1, round_killhs=None))
    assert types_of(body_only) == [EventType.KILL]

    jumped = EventDetector(thresholds())
    feed(jumped, make_payload(round_kills=1, round_killhs=0))
    leap = feed(jumped, make_payload(round_kills=5, round_killhs=1))
    assert EventType.ACE in types_of(leap)
    assert EventType.MULTI_KILL_4 not in types_of(leap)
    assert EventType.MULTI_KILL_3 not in types_of(leap)
    assert EventType.MULTI_KILL_2 not in types_of(leap)
    assert EventType.HEADSHOT_KILL in types_of(leap)


def test_round_reset_does_not_invent_kills():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(round_number=1, round_kills=5, round_phase="live"))
    reset = feed(
        detector,
        make_payload(round_number=2, round_kills=0, round_killhs=0, round_phase="live", health=100),
    )
    assert types_of(reset) == []
    nxt = feed(detector, make_payload(round_number=2, round_kills=1, round_killhs=0))
    assert types_of(nxt) == [EventType.KILL]


def test_low_health_only_after_damage_and_death_is_separate():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(health=100))
    assert feed(detector, make_payload(health=80)) == []
    hurt = feed(detector, make_payload(health=22))
    assert types_of(hurt) == [EventType.LOW_HEALTH]
    assert hurt[0].context["health"] == 22
    again = feed(detector, make_payload(health=15))
    assert types_of(again) == [EventType.LOW_HEALTH]
    assert feed(detector, make_payload(health=15)) == []
    assert feed(detector, make_payload(health=40)) == []
    died = feed(detector, make_payload(health=0, deaths=1))
    assert types_of(died) == [EventType.DEATH]
    assert EventType.LOW_HEALTH not in types_of(died)


def test_spectated_player_cannot_create_kill_or_health_events():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(team="CT", round_kills=0, health=100, round_phase="live"))
    peeked = feed(
        detector,
        make_payload(
            player_steamid=OTHER_STEAM_ID,
            team="T",
            round_kills=5,
            round_killhs=5,
            health=10,
            round_phase="live",
        ),
    )
    assert peeked == []
    still_us = feed(detector, make_payload(team="CT", round_kills=0, health=100))
    assert still_us == []
    our_kill = feed(detector, make_payload(team="CT", round_kills=1, health=100))
    assert types_of(our_kill) == [EventType.KILL]


def test_round_result_while_spectating_uses_remembered_team_only():
    detector = EventDetector(thresholds())
    feed(detector, make_payload(team="CT", round_phase="live", health=100))
    events = feed(
        detector,
        make_payload(
            player_steamid=OTHER_STEAM_ID,
            team="T",
            round_kills=4,
            health=20,
            round_phase="over",
            win_team="CT",
        ),
    )
    assert types_of(events) == [EventType.ROUND_WON]

    unknown = EventDetector(thresholds())
    feed(unknown, make_payload(player_steamid=OTHER_STEAM_ID, round_phase="live"))
    assert (
        feed(
            unknown,
            make_payload(
                player_steamid=OTHER_STEAM_ID,
                round_phase="over",
                win_team="T",
                round_kills=3,
            ),
        )
        == []
    )


def test_missing_provider_steamid_fails_closed():
    detector = EventDetector(thresholds())
    payload = make_payload(round_kills=0)
    del payload["provider"]["steamid"]
    feed(detector, payload)
    nxt = make_payload(round_kills=1)
    del nxt["provider"]["steamid"]
    assert feed(detector, nxt) == []


def test_scenario_covers_every_event_without_leaking_position():
    detector = EventDetector(thresholds())
    seen: set[EventType] = set()
    for payload in build_scenario("suito-local-change-me"):
        snapshot = parse_payload(payload)
        if snapshot is None:
            continue
        for event in detector.update(snapshot):
            seen.add(event.type)
            assert "9999" not in repr(event.context)
            assert "weapon_" not in repr(event.context)
            assert set(event.context) <= set(VISIBLE_CONTEXT_KEYS)
    assert seen == set(EventType)

"""Line selection: cooldowns, rate limit, priority bypass, no immediate repeat."""

from __future__ import annotations

import random
import re

from suit_o.config import DEFAULT_LINES_PATH
from suit_o.lines.provider import YamlLineProvider, _render
from suit_o.models import VISIBLE_CONTEXT_KEYS, EventType, GameEvent


def provider(lines: dict, **kwargs) -> YamlLineProvider:
    defaults = dict(
        default_cooldown=0,
        min_interval=0,
        preempt_min_priority=70,
        rng=random.Random(0),
    )
    defaults.update(kwargs)
    return YamlLineProvider(lines, **defaults)


def event(kind: EventType, priority: int, **context) -> GameEvent:
    return GameEvent(kind, priority, context)


def test_no_immediate_repeat_until_the_pool_is_one_line():
    chooser = provider({"kill": ["a", "b", "c"]})
    last = None
    for tick in range(30):
        line = chooser.select(event(EventType.KILL, 36), float(tick))
        assert line in {"a", "b", "c"}
        if last is not None:
            assert line != last
        last = line

    single = provider({"kill": ["only"]})
    assert single.select(event(EventType.KILL, 36), 0) == "only"
    assert single.select(event(EventType.KILL, 36), 1) == "only"


def test_per_event_cooldown_does_not_block_a_different_event():
    chooser = provider(
        {"kill": ["k1", "k2"], "death": ["d1", "d2"]},
        cooldowns={"kill": 10},
        default_cooldown=0,
    )
    assert chooser.select(event(EventType.KILL, 36), 0) is not None
    assert chooser.select(event(EventType.KILL, 36), 9) is None
    assert chooser.select(event(EventType.DEATH, 82), 9) is not None
    assert chooser.select(event(EventType.KILL, 36), 10) is not None


def test_rate_limit_blocks_small_events_and_big_moments_bypass_it():
    chooser = provider(
        {"kill": ["k"], "warmup": ["w"], "ace": ["ace"]},
        min_interval=5,
        preempt_min_priority=70,
    )
    assert chooser.select(event(EventType.KILL, 36), 0) == "k"
    assert chooser.select(event(EventType.WARMUP, 14), 1) is None
    assert chooser.select(event(EventType.ACE, 100), 1) == "ace"
    assert chooser.select(event(EventType.WARMUP, 14), 2) is None
    assert chooser.select(event(EventType.WARMUP, 14), 6) == "w"


def test_high_priority_still_respects_its_own_cooldown():
    chooser = provider(
        {"ace": ["a", "b"]},
        cooldowns={"ace": 10},
        min_interval=5,
        preempt_min_priority=70,
    )
    assert chooser.select(event(EventType.ACE, 100), 0) is not None
    assert chooser.select(event(EventType.ACE, 100), 1) is None
    assert chooser.select(event(EventType.ACE, 100), 10) is not None


def test_mute_suppresses_without_burning_the_pool():
    chooser = provider({"kill": ["k"]})
    chooser.set_muted(True)
    assert chooser.select(event(EventType.KILL, 36), 0) is None
    chooser.set_muted(False)
    assert chooser.select(event(EventType.KILL, 36), 0) == "k"


def test_renders_only_visible_context():
    chooser = provider({"low_health": ["{health} health on {map}."]})
    line = chooser.select(event(EventType.LOW_HEALTH, 44, health=12, map="dust2"), 0)
    assert line == "12 health on dust2."


def test_shipped_lines_cover_every_event():
    chooser = YamlLineProvider.from_file(
        DEFAULT_LINES_PATH,
        cooldowns={},
        default_cooldown=0,
        min_interval=0,
        preempt_min_priority=70,
        rng=random.Random(1),
    )
    for kind in EventType:
        lines = chooser.lines_for(kind)
        assert 1 <= len(lines) <= 10, kind
        assert len(lines) == len(set(lines)), kind
        for line in lines:
            keys = set(re.findall(r"\{(\w+)\}", line))
            assert keys <= set(VISIBLE_CONTEXT_KEYS)
            spoken = _render(
                line,
                {"health": 12, "money": 600, "map": "dust2", "round_kills": 2, "team": "CT"},
            )
            assert spoken.strip()
            assert "{" not in spoken
        picked = chooser.select(event(kind, 100), now=float(len(kind.value)))
        assert picked
        assert "{" not in picked
    for kind in EventType:
        lines = chooser.lines_for(kind)
        # Enough variety that a line is not heard every round.
        assert len(lines) >= 5, kind
        # A cloned voice pre-renders every stock line. A live number would fall
        # back to the Windows voice mid-match.
        assert not any("{" in line for line in lines), kind
    # Lines Suit-O wrote for the new events stay in, reworded where they echoed
    # the game's own catchphrases.
    kept = {
        EventType.ROUND_FREEZETIME: "New round! Five people on the other team would like you gone. So, uh, maybe don't let them. I love you.",
        EventType.ACE: "Wait, was that all five? Are you cheating? I'm not accusing anyone. I'm just writing the developers a very long email. With attachments.",
        EventType.DEATH: "Your health bar is empty. I'm no doctor. I'm not anything, actually. But that seems bad.",
        EventType.ROUND_WON: "We won the round! I helped. I didn't do anything, but I was here, and that's a kind of helping.",
        EventType.HALFTIME: "Halftime, switching sides! Not me, though. I'm always on your side. I literally live in your computer.",
    }
    for kind, line in kept.items():
        assert line in chooser.lines_for(kind), kind
    everything = " ".join(line for kind in EventType for line in chooser.lines_for(kind))
    for phrase in ("readings indicate", "biometric", "driving to your house", "not your dad", "just you now"):
        assert phrase not in everything, phrase

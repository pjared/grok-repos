"""How much Suit-O talks. Three levels, set on the Voice tab.

Quiet speaks only big moments. Normal skips routine filler and leaves more room
between lines. Chatty speaks at every event, as Suit-O always did. The same
level sets how long chat replies are.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CHATTINESS = "normal"
LEVELS = ("quiet", "normal", "chatty")
LABELS = {"quiet": "Quiet", "normal": "Normal", "chatty": "Chatty"}
HINTS = {
    "quiet": "Only big moments: bomb plants, deaths, multi-kills, aces, and the match result.",
    "normal": "Skips round-start, warmup, and idle chatter, and leaves more room between lines.",
    "chatty": "Talks at every event.",
}
# The menu greeting has its own switch on the Listener tab, so chattiness
# leaves it alone.
EXEMPT_EVENTS = frozenset({"menu_greeting"})


@dataclass(frozen=True)
class ChattinessRule:
    min_priority: int
    interval_scale: float
    cooldown_scale: float
    reply_rule: str
    reply_tokens: int
    # Events that speak at this level even below ``min_priority``.
    also: frozenset[str] = frozenset()


RULES = {
    "quiet": ChattinessRule(
        min_priority=70,
        interval_scale=2.0,
        cooldown_scale=1.5,
        reply_rule="Reply in one short sentence. Say as little as you can.",
        reply_tokens=80,
        also=frozenset({"match_won", "match_end"}),
    ),
    "normal": ChattinessRule(
        min_priority=30,
        interval_scale=1.5,
        cooldown_scale=1.0,
        reply_rule="Keep every reply to one or two short sentences.",
        reply_tokens=200,
    ),
    "chatty": ChattinessRule(
        min_priority=0,
        interval_scale=1.0,
        cooldown_scale=1.0,
        reply_rule="You may ramble a little, up to three short sentences.",
        reply_tokens=300,
    ),
}


class ChattinessError(ValueError):
    """Not one of quiet, normal, or chatty."""


def normalize_chattiness(value: object) -> str:
    """Accept a level or its label, in any case."""

    text = str(value or "").strip().casefold()
    for level, label in LABELS.items():
        if text in {level, label.casefold()}:
            return level
    raise ChattinessError("chattiness must be quiet, normal, or chatty")


def rule_for(level: str) -> ChattinessRule:
    return RULES[normalize_chattiness(level)]

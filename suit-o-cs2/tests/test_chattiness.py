"""Chattiness: how much Suit-O talks in a match and in chat."""

from __future__ import annotations

import shutil
from pathlib import Path

from suit_o.app import SuitOApp
from suit_o.chat.session import ChatSession
from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from suit_o.lines.chattiness import (
    ChattinessError,
    DEFAULT_CHATTINESS,
    LEVELS,
    normalize_chattiness,
    rule_for,
)
from suit_o.lines.provider import YamlLineProvider
from suit_o.models import EventType, GameEvent
from suit_o.speech.stub import StubSpeechBackend

LINES = {
    "round_freezetime": ["round start"],
    "warmup": ["warmup"],
    "idle": ["idle"],
    "menu_greeting": ["hello"],
    "kill": ["kill"],
    "round_won": ["won"],
    "death": ["dead"],
    "ace": ["ace"],
    "match_won": ["gg"],
}


def _event(kind: EventType, priority: int) -> GameEvent:
    return GameEvent(kind, priority, {})


def _provider(level: str, *, min_interval: float = 0.0) -> YamlLineProvider:
    return YamlLineProvider(LINES, min_interval=min_interval, preempt_min_priority=70, chattiness=level)


def test_levels_accept_labels_and_reject_anything_else():
    assert LEVELS == ("quiet", "normal", "chatty")
    assert DEFAULT_CHATTINESS == "normal"
    assert normalize_chattiness("Quiet") == "quiet"
    assert normalize_chattiness(" CHATTY ") == "chatty"
    try:
        normalize_chattiness("loud")
    except ChattinessError as exc:
        assert "quiet, normal, or chatty" in str(exc)
    else:
        raise AssertionError("an unknown level was accepted")


def test_quiet_keeps_only_big_moments_and_the_menu_greeting():
    quiet = _provider("quiet")
    assert quiet.decide(_event(EventType.ROUND_FREEZETIME, 24), 0).status == "chattiness"
    assert quiet.decide(_event(EventType.KILL, 36), 10).status == "chattiness"
    assert quiet.decide(_event(EventType.ROUND_WON, 60), 20).status == "chattiness"
    assert quiet.select(_event(EventType.DEATH, 82), 30) == "dead"
    assert quiet.select(_event(EventType.ACE, 100), 40) == "ace"
    assert quiet.select(_event(EventType.MENU_GREETING, 12), 50) == "hello"
    assert quiet.select(_event(EventType.MATCH_WON, 49), 60) == "gg"


def test_normal_drops_filler_and_chatty_speaks_at_everything():
    normal = _provider("normal")
    assert normal.decide(_event(EventType.ROUND_FREEZETIME, 24), 0).status == "chattiness"
    assert normal.decide(_event(EventType.WARMUP, 14), 10).status == "chattiness"
    assert normal.decide(_event(EventType.IDLE, 10), 20).status == "chattiness"
    assert normal.select(_event(EventType.KILL, 36), 30) == "kill"
    assert normal.select(_event(EventType.ROUND_WON, 60), 40) == "won"

    chatty = _provider("chatty")
    for number, (kind, priority) in enumerate(
        [(EventType.ROUND_FREEZETIME, 24), (EventType.WARMUP, 14), (EventType.IDLE, 10), (EventType.KILL, 36)]
    ):
        assert chatty.decide(_event(kind, priority), number * 10).status == "spoken"


def test_quieter_levels_leave_more_room_between_small_lines():
    chatty = _provider("chatty", min_interval=2.0)
    normal = _provider("normal", min_interval=2.0)
    for provider in (chatty, normal):
        assert provider.select(_event(EventType.KILL, 36), 0) == "kill"
    assert chatty.select(_event(EventType.ROUND_WON, 60), 2.5) == "won"
    assert normal.decide(_event(EventType.ROUND_WON, 60), 2.5).status == "lower priority"
    assert normal.select(_event(EventType.ROUND_WON, 60), 3.1) == "won"


def test_chat_reply_length_follows_chattiness():
    sent: list[list[dict]] = []
    level = {"value": "quiet"}
    session = ChatSession(chattiness=lambda: level["value"])

    def generate(messages):
        sent.append(messages)
        yield "Ok."

    list(session.reply("hi", paused=lambda: False, generate=generate, speak=lambda _s: None))
    assert rule_for("quiet").reply_rule in sent[-1][0]["content"]
    level["value"] = "chatty"
    list(session.reply("hi", paused=lambda: False, generate=generate, speak=lambda _s: None))
    assert rule_for("chatty").reply_rule in sent[-1][0]["content"]
    assert rule_for("quiet").reply_tokens < rule_for("normal").reply_tokens < rule_for("chatty").reply_tokens


def test_the_choice_is_saved_locally_and_applies_right_away(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    shutil.copy(DEFAULT_CONFIG_PATH, config_path)
    shutil.copytree(DEFAULT_CONFIG_PATH.parent / "lines", tmp_path / "lines")
    before = config_path.read_bytes()
    config = load_config(config_path)
    assert config.chattiness == "normal"
    app = SuitOApp(config, backend=StubSpeechBackend(), config_path=config_path)
    try:
        assert app.lines.chattiness == "normal"
        assert app.save_chattiness("Quiet") == "quiet"
        assert app.lines.chattiness == "quiet"
        assert app.config.chattiness == "quiet"
        try:
            app.save_chattiness("shouting")
        except ConfigError:
            pass
        else:
            raise AssertionError("an unknown level was saved")
    finally:
        app.stop()
    assert config_path.read_bytes() == before
    assert load_config(config_path).chattiness == "quiet"
    local = (tmp_path / "config.local.yaml").read_text(encoding="utf-8")
    assert "chattiness: quiet" in local

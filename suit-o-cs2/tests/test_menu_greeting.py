"""Main-menu Premier greeting: once per visit, then a ten-minute quiet."""

from __future__ import annotations

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config, parse_config
from suit_o.events.detector import EventDetector
from suit_o.gsi.parse import parse_payload
from suit_o.gsi.payloads import make_payload
from suit_o.lines.provider import YamlLineProvider
from suit_o.models import EventType, GameEvent
from suit_o.speech.stub import StubSpeechBackend
from tests.test_detector import thresholds


def _types(detector: EventDetector, payload: dict) -> list[EventType]:
    snapshot = parse_payload(payload)
    assert snapshot is not None
    return [event.type for event in detector.update(snapshot)]


def test_restart_flag_skips_only_the_opening_greeting():
    detector = EventDetector(thresholds(), greeted=True)
    menu = dict(activity="menu", include_map=False, include_round=False)
    assert EventType.MENU_GREETING not in _types(detector, make_payload(**menu))
    assert EventType.MENU_GREETING not in _types(detector, make_payload(map_phase="live"))
    returned = _types(detector, make_payload(**menu))
    assert EventType.MENU_GREETING in returned


def test_reload_keeps_the_detector_and_does_not_greet_again(tmp_path):
    path = tmp_path / "config.yaml"
    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    text = text.replace("lines/lines.yaml", (DEFAULT_CONFIG_PATH.parent / "lines" / "lines.yaml").as_posix())
    path.write_text(text, encoding="utf-8")
    app = SuitOApp(load_config(path), backend=StubSpeechBackend(), config_path=path)
    menu = dict(activity="menu", include_map=False, include_round=False)
    app._handle(make_payload(**menu))
    detector = app.detector
    assert detector.greeted_this_session is True
    applied = app.reload_content()
    assert applied.applied is True
    assert app.detector is detector
    app._handle(make_payload(**menu))
    spoken = [
        item.message
        for item in app.activity()
        if item.message.startswith("menu_greeting: ") and "skipped" not in item.message
    ]
    assert len(spoken) == 1


def test_first_connect_greets_once_until_a_match_ends():
    detector = EventDetector(thresholds())
    menu = dict(activity="menu", include_map=False, include_round=False)
    assert _types(detector, make_payload(**menu)) == [EventType.MENU_GREETING]
    assert _types(detector, make_payload(**menu)) == []
    assert _types(detector, make_payload(activity="playing", include_map=False, include_round=False)) == []
    back = _types(detector, make_payload(**menu))
    assert EventType.MENU_GREETING not in back
    assert EventType.IDLE in back

    played = EventDetector(thresholds())
    assert EventType.MENU_GREETING not in _types(played, make_payload(map_phase="live"))
    returned = _types(played, make_payload(**menu))
    assert returned == [EventType.IDLE, EventType.MENU_GREETING]
    assert _types(played, make_payload(**menu)) == []

    delayed = EventDetector(thresholds())
    assert EventType.MENU_GREETING not in _types(delayed, make_payload(map_phase="live"))
    assert EventType.MENU_GREETING not in _types(
        delayed, make_payload(activity="playing", include_map=False, include_round=False)
    )
    arrived = _types(delayed, make_payload(**menu))
    assert EventType.MENU_GREETING in arrived


def test_textinput_flip_does_not_greet_again():
    detector = EventDetector(thresholds())
    quiet = dict(include_map=False, include_round=False)
    assert _types(detector, make_payload(activity="menu", **quiet)) == [EventType.MENU_GREETING]
    assert _types(detector, make_payload(activity="textinput", **quiet)) == []
    assert EventType.MENU_GREETING not in _types(detector, make_payload(activity="menu", **quiet))
    assert _types(detector, make_payload(activity="textinput", **quiet)) == []

    played = EventDetector(thresholds())
    assert EventType.MENU_GREETING not in _types(played, make_payload(activity="playing", map_phase="live"))
    assert EventType.MENU_GREETING not in _types(played, make_payload(activity="textinput", map_phase="live"))
    assert EventType.MENU_GREETING not in _types(played, make_payload(activity="playing", map_phase="live"))
    returned = _types(played, make_payload(activity="menu", **quiet))
    assert EventType.MENU_GREETING in returned
    assert EventType.MENU_GREETING not in _types(played, make_payload(activity="textinput", **quiet))
    assert EventType.MENU_GREETING not in _types(played, make_payload(activity="menu", **quiet))


def test_greeting_cooldown_is_ten_minutes():
    chooser = YamlLineProvider(
        {"menu_greeting": ["Ready for Premier?"]},
        default_cooldown=0,
        cooldowns={"menu_greeting": 600},
        min_interval=0,
        preempt_min_priority=70,
    )
    event = GameEvent(EventType.MENU_GREETING, 12, {})
    assert chooser.decide(event, 0).status == "spoken"
    assert chooser.decide(event, 60).status == "cooldown"
    assert chooser.decide(event, 599).status == "cooldown"
    assert chooser.decide(event, 600).status == "spoken"


def test_app_greets_on_the_menu_and_the_toggle_skips_it(tmp_path):
    moments = iter([0.0, 1.0, 2.0, 3.0, 60.0, 61.0, 600.0])
    app = SuitOApp(
        load_config(DEFAULT_CONFIG_PATH),
        backend=StubSpeechBackend(),
        config_path=DEFAULT_CONFIG_PATH,
        clock=lambda: next(moments),
    )
    assert app.config.menu_greeting is True
    assert app.config.cooldowns["menu_greeting"] == 600
    menu = dict(activity="menu", include_map=False, include_round=False)

    def greetings() -> list[str]:
        return [
            item.message
            for item in app.activity()
            if item.message.startswith("menu_greeting: ") and "skipped" not in item.message
        ]

    app._handle(make_payload(**menu))
    app._handle(make_payload(activity="textinput", include_map=False, include_round=False))
    app._handle(make_payload(**menu))
    assert len(greetings()) == 1
    assert any(snippet in greetings()[0] for snippet in ("Premier", "Ready to queue?"))

    app._handle(make_payload(map_phase="live"))
    app._handle(make_payload(**menu))
    assert len(greetings()) == 1
    assert any(item.message == "menu_greeting: skipped (cooldown)" for item in app.activity())

    app._handle(make_payload(map_phase="live"))
    app._handle(make_payload(**menu))
    assert len(greetings()) == 2

    quiet = SuitOApp(
        load_config(DEFAULT_CONFIG_PATH),
        backend=StubSpeechBackend(),
        config_path=tmp_path / "config.yaml",
    )
    quiet.config.menu_greeting = False
    quiet._handle(make_payload(**menu))
    assert not any(
        item.message.startswith("menu_greeting: ") and "skipped" not in item.message
        for item in quiet.activity()
    )
    assert any(item.message == "menu_greeting: skipped (disabled)" for item in quiet.activity())

    copy = tmp_path / "config.yaml"
    copy.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    saved = SuitOApp(
        load_config(DEFAULT_CONFIG_PATH),
        backend=StubSpeechBackend(),
        config_path=copy,
    )
    saved.save_menu_greeting(False)
    assert load_config(copy).menu_greeting is False
    saved.save_menu_greeting(True)
    assert load_config(copy).menu_greeting is True
    local = copy.with_name("config.local.yaml")
    assert not local.exists() or "menu_greeting" not in local.read_text(encoding="utf-8")


def test_config_rejects_a_non_boolean_menu_greeting():
    raw = __import__("yaml").safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    raw["menu_greeting"] = "yes"
    try:
        parse_config(raw)
    except ConfigError as exc:
        assert "menu_greeting" in str(exc)
    else:
        raise AssertionError("a string menu_greeting was accepted")

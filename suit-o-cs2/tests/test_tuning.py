"""Voice tuning, SAPI markup, and config persistence. No window."""

from __future__ import annotations

import sys
from pathlib import Path

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from suit_o.speech.stub import StubSpeechBackend
from suit_o.speech.tuning import (
    TuningError,
    VoiceTuning,
    list_sapi_voice_names,
    normalize_tuning,
    prepare_utterance,
    resolve_voice_name,
    selected_voice_label,
    voice_menu_labels,
)

DAVID = "Microsoft David Desktop"
ZIRA = "Microsoft Zira Desktop"
VOICES = [DAVID, ZIRA]


def test_normalize_clamps_known_levels_and_rejects_the_rest():
    tuned = normalize_tuning(
        VoiceTuning(voice="  Engine default ", rate=185, volume=1, pitch=0, pause_ms=0, emphasis="MILD")
    )
    assert tuned.voice == ""
    assert tuned.emphasis == "mild"
    assert tuned.volume == 1.0

    for bad in (
        VoiceTuning(rate=79),
        VoiceTuning(rate=True),  # type: ignore[arg-type]
        VoiceTuning(pitch=11),
        VoiceTuning(pause_ms=-1),
        VoiceTuning(emphasis="loud"),
        VoiceTuning(volume=True),  # type: ignore[arg-type]
    ):
        try:
            normalize_tuning(bad)
            raised = False
        except TuningError:
            raised = True
        assert raised


def test_resolve_voice_name_prefers_exact_then_one_substring():
    assert resolve_voice_name("", VOICES) == ""
    assert resolve_voice_name("windows default", VOICES) == ""
    assert resolve_voice_name("zira", VOICES) == ZIRA
    assert resolve_voice_name(DAVID, VOICES) == DAVID
    assert resolve_voice_name("Custom Clone", None) == "Custom Clone"
    try:
        resolve_voice_name("Microsoft", VOICES)
        ambiguous = False
    except TuningError as exc:
        ambiguous = True
        assert DAVID in str(exc)
        assert ZIRA in str(exc)
    assert ambiguous
    try:
        resolve_voice_name("Hazel", VOICES)
        missing = False
    except TuningError:
        missing = True
    assert missing

    labels = voice_menu_labels(VOICES, "Missing Voice")
    assert labels[0] == "Engine default"
    assert "Missing Voice" in labels
    assert selected_voice_label("", VOICES) == "Engine default"
    assert selected_voice_label("zira", VOICES) == ZIRA


def test_prepare_utterance_keeps_plain_lines_and_marks_up_the_rest():
    assert prepare_utterance("  Hello  ", VoiceTuning()) == ("Hello", False)
    assert prepare_utterance("   ", VoiceTuning(pitch=2)) == ("", False)

    pitched, uses_pitch = prepare_utterance("Hello", VoiceTuning(pitch=-2))
    assert uses_pitch
    assert pitched == '<pitch absmiddle="-2">Hello</pitch>'

    paused, uses_pause = prepare_utterance("Hello", VoiceTuning(pause_ms=80))
    assert uses_pause
    assert paused == '<silence msec="80"/>Hello'

    mild, uses_mild = prepare_utterance("Hello", VoiceTuning(emphasis="mild"))
    assert uses_mild
    assert mild == "<emph>Hello</emph>"

    strong, uses_strong = prepare_utterance("Hello", VoiceTuning(pitch=8, emphasis="strong"))
    assert uses_strong
    assert strong == '<pitch absmiddle="10"><emph>Hello</emph></pitch>'

    escaped, uses_escape = prepare_utterance('A & B < "C"', VoiceTuning())
    assert uses_escape
    assert escaped == "A &amp; B &lt; &quot;C&quot;"


def test_sapi_voice_list_is_empty_off_windows():
    if sys.platform == "win32":
        return
    assert list_sapi_voice_names() == []


def test_app_saves_tuning_and_preview_leaves_it_alone(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    original = path.read_bytes()
    config = load_config(DEFAULT_CONFIG_PATH)
    backend = StubSpeechBackend()
    app = SuitOApp(
        config,
        backend=backend,
        config_path=path,
        voices=lambda: list(VOICES),
    )
    app.start()
    try:
        try:
            app.apply_tuning(VoiceTuning(voice="Microsoft"))
            ambiguous = False
        except ConfigError as exc:
            ambiguous = True
            assert "more than one" in str(exc)
        assert ambiguous
        assert app.config.speech.voice == ""

        applied = app.apply_tuning(
            VoiceTuning(voice="zira", rate=160, volume=0.5, pitch=2, pause_ms=120, emphasis="strong")
        )
        assert applied.voice == ZIRA
        app.set_muted(True)
        spoken = app.preview_voice(
            "Hello & friends",
            VoiceTuning(voice="david", rate=220, volume=0.5, pitch=-3, pause_ms=40, emphasis="mild"),
        )
        assert spoken == "Hello & friends"
        assert app.speech.wait_until(lambda: backend.spoken == ["Hello & friends"], 2)
        assert app.config.speech.voice == ZIRA
        assert app.config.speech.rate == 160
        assert app.config.speech.pitch == 2
        assert app.config.speech.emphasis == "strong"
        assert backend.spoken_tuning[0].voice == DAVID
        assert backend.spoken_tuning[0].pitch == -3
        assert backend.spoken_tuning[0].emphasis == "mild"
        assert backend.tuning is not None
        assert backend.tuning.pitch == 2
        assert backend.tuning.voice == ZIRA
        app.save_preferences()
        reset = app.reset_tuning()
        assert reset.rate == 185
        assert reset.pitch == 0
        assert reset.voice == ""
        assert reset.emphasis == "none"
        app.set_muted(False)
        app.save_preferences()
    finally:
        app.stop()

    assert path.read_bytes() == original
    saved = load_config(path)
    assert saved.speech.voice == ""
    assert saved.speech.rate == 185
    assert saved.speech.pitch == 0
    assert saved.speech.pause_ms == 0
    assert saved.speech.emphasis == "none"
    assert saved.speech.volume == 0.85
    assert saved.mute is False

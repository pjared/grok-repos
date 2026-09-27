"""Daily speech log: spoken lines, mute and cooldown skips, and pruning."""

from __future__ import annotations

import json
import time
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config, parse_config
from suit_o.gsi.payloads import make_payload
from suit_o.lines.provider import YamlLineProvider
from suit_o.models import EventType, GameEvent
from suit_o.simulate import post_payload, simulation_config
from suit_o.speech.stub import StubSpeechBackend
from suit_o.speechlog import SpeechLog, SpeechLogEntry


def _entry(at: float, **overrides) -> SpeechLogEntry:
    values = dict(
        at=at,
        event="kill",
        text="Nice.",
        status="spoken",
        map_name="mirage",
        round_number=8,
        voice="Microsoft Zira Desktop",
    )
    values.update(overrides)
    return SpeechLogEntry(**values)


def test_daily_file_records_the_line_and_prunes_old_days(tmp_path: Path):
    today = datetime(2026, 9, 27, 15, 4, 5)
    log = SpeechLog(tmp_path, keep_days=14, now=lambda: today.timestamp())
    first = log.append(_entry(today.timestamp(), text="Nice.\nshot"))
    second = log.append(
        _entry(today.timestamp() + 1, status="cooldown", text="", event="kill")
    )
    assert first == second
    assert first.name == "speech-2026-09-27.jsonl"
    rows = [json.loads(line) for line in first.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["time"] == "2026-09-27T15:04:05"
    assert rows[0]["event"] == "kill"
    assert rows[0]["text"] == "Nice. shot"
    assert rows[0]["status"] == "spoken"
    assert rows[0]["map"] == "mirage"
    assert rows[0]["round"] == 8
    assert rows[0]["voice"] == "Microsoft Zira Desktop"
    assert rows[1]["status"] == "cooldown"
    assert "token" not in first.read_text(encoding="utf-8")

    stale = today.date() - timedelta(days=14)
    kept = today.date() - timedelta(days=13)
    (tmp_path / f"speech-{stale.isoformat()}.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / f"speech-{kept.isoformat()}.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("leave this", encoding="utf-8")
    removed = log.prune()
    assert [path.name for path in removed] == [f"speech-{stale.isoformat()}.jsonl"]
    assert not (tmp_path / f"speech-{stale.isoformat()}.jsonl").exists()
    assert (tmp_path / f"speech-{kept.isoformat()}.jsonl").is_file()
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "leave this"
    assert first.is_file()

    try:
        SpeechLog(tmp_path, keep_days=0)
    except ValueError as exc:
        assert "keep_days" in str(exc)
    else:
        raise AssertionError("keep_days of 0 was accepted")


def test_config_rejects_a_bad_keep_days():
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    raw["logs"] = {"keep_days": True}
    try:
        parse_config(raw)
    except ConfigError as exc:
        assert "logs.keep_days" in str(exc)
    else:
        raise AssertionError("a boolean keep_days was accepted")
    loaded = load_config(DEFAULT_CONFIG_PATH)
    assert loaded.logs.keep_days == 14


def test_app_logs_spoken_lines_and_mute_or_cooldown_skips(tmp_path: Path):
    folder = tmp_path / "logs"
    moments = iter([0.0, 3.0, 4.0, 4.0])
    app = SuitOApp(
        load_config(DEFAULT_CONFIG_PATH),
        backend=StubSpeechBackend(),
        config_path=DEFAULT_CONFIG_PATH,
        speech_log_dir=folder,
        clock=lambda: next(moments),
    )
    app.config.speech.voice = "Microsoft Zira Desktop"
    app._handle(make_payload(map_name="de_mirage", round_number=4, round_kills=0, kills=0))
    app._handle(make_payload(map_name="de_mirage", round_number=4, round_kills=1, kills=1))
    app._handle(make_payload(map_name="de_mirage", round_number=4, round_kills=2, kills=2))
    app.set_muted(True)
    app._handle(make_payload(map_name="de_mirage", round_number=4, round_kills=2, kills=2, health=10))

    path = folder / time.strftime("speech-%Y-%m-%d.jsonl", time.localtime())
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    statuses = [row["status"] for row in rows]
    assert "spoken" in statuses
    assert "cooldown" in statuses
    assert "muted" in statuses
    spoken_row = next(row for row in rows if row["status"] == "spoken")
    assert spoken_row["map"] == "mirage"
    assert spoken_row["round"] == 4
    assert spoken_row["voice"] == "Microsoft Zira Desktop"
    assert spoken_row["text"]
    assert spoken_row["event"]
    messages = [item.message for item in app.activity()]
    assert any(message.endswith("skipped (cooldown)") for message in messages)
    assert any(message.endswith("skipped (muted)") for message in messages)
    assert any(": " in message and "skipped" not in message for message in messages)


def test_silence_reasons_include_no_line_and_lower_priority():
    chooser = YamlLineProvider(
        {"kill": ["Nice."]},
        default_cooldown=0,
        min_interval=10,
        preempt_min_priority=70,
    )
    kill = GameEvent(EventType.KILL, 36, {})
    death = GameEvent(EventType.DEATH, 36, {})
    assert chooser.decide(kill, 0).status == "spoken"
    assert chooser.decide(death, 1).status == "no matching line"
    assert chooser.decide(kill, 2).status == "lower priority"


def test_payload_minutes_and_the_token_are_redacted(tmp_path: Path):
    token = "suito-secret-token-9f3a"
    wrong = "wrong-token-value-77"
    start = datetime(2026, 9, 27, 15, 4, 5)
    log = SpeechLog(tmp_path, keep_days=14, now=lambda: start.timestamp(), secrets=(token,))
    log.append(
        _entry(
            start.timestamp(),
            text=f"heard {token} in the line",
            map_name=f"map-{token}",
            voice=token,
        )
    )
    log.note_rejected(start.timestamp(), f"bad token {token} {wrong}")
    assert log.note_payload(start.timestamp()) is None
    assert log.note_payload(start.timestamp() + 20) is None
    rolled = log.note_payload(start.timestamp() + 60)
    assert rolled is not None
    assert rolled.count == 2
    assert rolled.first == "2026-09-27T15:04:05"
    assert rolled.last == "2026-09-27T15:04:25"

    body = (tmp_path / "speech-2026-09-27.jsonl").read_text(encoding="utf-8")
    assert token not in body
    assert "[redacted]" in body
    rows = [json.loads(line) for line in body.splitlines()]
    assert rows[0]["text"] == "heard [redacted] in the line"
    assert rows[0]["map"] == "map-[redacted]"
    assert rows[0]["voice"] == "[redacted]"
    assert rows[1]["kind"] == "rejected"
    assert rows[1]["status"] == f"bad token [redacted] {wrong}"
    assert "auth" not in rows[1]
    payload = rows[2]
    assert payload["kind"] == "payload"
    assert payload["status"] == "received"
    assert payload["count"] == 2
    assert payload["first"] == "2026-09-27T15:04:05"
    assert payload["last"] == "2026-09-27T15:04:25"


def test_rejected_gsi_post_does_not_write_the_token(tmp_path: Path):
    folder = tmp_path / "logs"
    config = simulation_config(DEFAULT_CONFIG_PATH)
    real = config.server.token
    wrong = "wrong-token-value-77"
    app = SuitOApp(
        config,
        backend=StubSpeechBackend(),
        speech_log_dir=folder,
        line_provider=YamlLineProvider({}),
    )
    app.start()
    try:
        host, port = app.server_address
        url = f"http://{host}:{port}/"
        bad = make_payload(token=wrong, map_name="de_mirage", round_number=2)
        bad["player"]["name"] = real
        try:
            post_payload(url, bad)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
            exc.read()
        else:
            raise AssertionError("a bad token was accepted")
        post_payload(url, make_payload(token=real, map_name="de_mirage", round_number=2, round_kills=0))
        post_payload(url, make_payload(token=real, map_name="de_mirage", round_number=2, round_kills=1, kills=1))
    finally:
        app.stop()

    files = list(folder.glob("speech-*.jsonl"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert real not in body
    assert wrong not in body
    rows = [json.loads(line) for line in body.splitlines()]
    assert any(row["kind"] == "rejected" and row["status"] == "bad token" for row in rows)
    assert any(row["kind"] == "payload" and row["count"] >= 1 for row in rows)
    assert any(row["status"] == "no matching line" for row in rows)
    assert all("auth" not in row for row in rows)

"""Post the synthetic match at a local Suit-O and require a line for every event.

Speech uses the stub backend, so this does not play audio. Cooldowns and the
global rate limit are cleared for the run; otherwise a burst of test events
would be swallowed and the check would be meaningless.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH, Config, ConfigError, load_config
from suit_o.models import EventType
from suit_o.scenario import BOMB_POSITION_SENTINEL, build_scenario
from suit_o.speech.stub import StubSpeechBackend

logger = logging.getLogger(__name__)


def simulation_config(path: Path) -> Config:
    config = load_config(path)
    config.speech.backend = "stub"
    config.mute = False
    config.default_cooldown = 0
    config.cooldowns = {event.value: 0.0 for event in EventType}
    config.min_interval = 0
    config.server.port = 0
    return config


def post_payload(url: str, payload: dict, timeout: float = 2.0) -> int:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()
        return int(response.status)


def run_simulation(config: Config, *, backend: StubSpeechBackend | None = None) -> list[str]:
    """Start Suit-O, post the scenario, and return spoken event types in order."""

    speech = backend or StubSpeechBackend()
    app = SuitOApp(config, backend=speech)
    app.start()
    try:
        host, port = app.server_address
        url = f"http://{host}:{port}/"
        payloads = build_scenario(config.server.token)
        for index, payload in enumerate(payloads, start=1):
            post_payload(url, payload)
            # Wait until this snapshot has been applied and any line has
            # finished. That keeps big-moment preemption from eating the
            # previous step's line during the scripted run.
            if not app.wait_for_payloads(index, timeout=5):
                raise RuntimeError(
                    f"Timed out after payload {index} "
                    f"(processed {app.processed} of {len(payloads)})"
                )
        return [item.event_type for item in app.speech.history]
    finally:
        app.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="suit-o-simulate",
        description="Post a synthetic CS2 match at Suit-O with speech stubbed.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    try:
        config = simulation_config(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    backend = StubSpeechBackend()
    try:
        spoken = run_simulation(config, backend=backend)
    except (RuntimeError, urllib.error.URLError, OSError) as exc:
        print(f"Simulator failed: {exc}", file=sys.stderr)
        return 1

    print("Suit-O simulator transcript (TTS stubbed):")
    for event_type, text in zip(spoken, backend.spoken, strict=False):
        print(f"  [{event_type}] {text}")
        if BOMB_POSITION_SENTINEL in text:
            print("Simulator failed: a line included the bomb position.", file=sys.stderr)
            return 1

    expected = {event.value for event in EventType}
    got = set(spoken)
    missing = sorted(expected - got)
    if missing:
        print("Missing events: " + ", ".join(missing), file=sys.stderr)
        return 1
    print(f"All {len(expected)} events produced a line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

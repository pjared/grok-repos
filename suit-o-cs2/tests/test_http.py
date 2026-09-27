"""GSI HTTP server: auth, fast return, and the mute control."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from suit_o.app import SuitOApp
from suit_o.config import DEFAULT_CONFIG_PATH
from suit_o.gsi.payloads import make_payload
from suit_o.scenario import build_scenario
from suit_o.simulate import post_payload, simulation_config
from tests.test_speech import HoldBackend


def test_token_rejection_mute_and_nonblocking_post():
    config = simulation_config(DEFAULT_CONFIG_PATH)
    backend = HoldBackend()
    app = SuitOApp(config, backend=backend)
    app.start()
    try:
        host, port = app.server_address
        url = f"http://{host}:{port}/"
        payloads = build_scenario(config.server.token)

        bad = make_payload(token="wrong-token-value")
        try:
            post_payload(url, bad)
            rejected = False
        except urllib.error.HTTPError as exc:
            rejected = exc.code == 401
            exc.read()
        assert rejected

        request = urllib.request.Request(
            url,
            data=b"{",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=2)
            bad_json = False
        except urllib.error.HTTPError as exc:
            bad_json = exc.code == 400
            exc.read()
        assert bad_json

        post_payload(url, payloads[0])
        post_payload(url, payloads[1])
        started = time.monotonic()
        status = post_payload(url, payloads[2], timeout=1)
        elapsed = time.monotonic() - started
        assert status == 200
        assert elapsed < 0.75
        assert backend.started.wait(2)
        assert not backend.release.is_set()

        mute_request = urllib.request.Request(url + "mute", data=b"{}", method="POST")
        with urllib.request.urlopen(mute_request, timeout=2) as response:
            body = json.loads(response.read().decode("utf-8"))
        assert body["muted"] is True

        with urllib.request.urlopen(f"http://{host}:{port}/status", timeout=2) as response:
            status_body = json.loads(response.read().decode("utf-8"))
        assert status_body["muted"] is True
    finally:
        app.stop()

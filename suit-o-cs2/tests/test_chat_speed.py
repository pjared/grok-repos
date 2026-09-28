"""Chat latency helpers: warm-up, reply caps, and a bounded context. No Tk and no network."""

from __future__ import annotations

import json

from suit_o.chat import stt as chat_stt
from suit_o.chat.llm import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    KEEP_ALIVE,
    MAX_REPLY_TOKENS,
    ChatSettings,
    stream_reply,
    warm_model,
)
from suit_o.chat.session import MAX_CONTEXT_TURNS, ChatSession


def test_warm_model_loads_ollama_without_a_prompt_or_key():
    settings = ChatSettings("ollama", DEFAULT_OLLAMA_URL, DEFAULT_MODEL, "", "")
    seen: list[tuple[str, dict, dict]] = []

    def post(url, payload, headers):
        seen.append((url, payload, headers))
        yield json.dumps({"done": True})

    assert warm_model(settings, post=post) is True
    assert seen == [(
        "http://localhost:11434/api/generate",
        {"model": DEFAULT_MODEL, "keep_alive": KEEP_ALIVE},
        {},
    )]

    def down(_url, _payload, _headers):
        raise OSError("connection refused")
        yield ""

    assert warm_model(settings, post=down) is False

    remote = ChatSettings("openai", DEFAULT_OLLAMA_URL, "gpt-4o-mini", "http://127.0.0.1:9/v1", "sk-test")

    def boom(_url, _payload, _headers):
        raise AssertionError("a remote endpoint was asked to warm up")
        yield ""

    assert warm_model(remote, post=boom) is False


def test_replies_keep_the_model_loaded_and_are_capped():
    payloads: list[dict] = []

    def post(_url, payload, _headers):
        payloads.append(payload)
        yield json.dumps({"message": {"content": "Hi."}})
        yield "data: " + json.dumps({"choices": [{"delta": {"content": "Hi."}}]})

    local = ChatSettings("ollama", DEFAULT_OLLAMA_URL, DEFAULT_MODEL, "", "")
    assert "".join(stream_reply(local, [], post=post)) == "Hi."
    assert payloads[-1]["keep_alive"] == KEEP_ALIVE
    assert payloads[-1]["options"] == {"num_predict": MAX_REPLY_TOKENS}

    remote = ChatSettings("openai", DEFAULT_OLLAMA_URL, "gpt-4o-mini", "http://127.0.0.1:9/v1", "sk-test")
    assert "".join(stream_reply(remote, [], post=post)) == "Hi."
    assert payloads[-1]["max_tokens"] == MAX_REPLY_TOKENS
    assert "keep_alive" not in payloads[-1]


def test_only_recent_turns_are_sent_but_the_persona_always_is():
    session = ChatSession()
    sent: list[list[dict]] = []

    def generate(messages):
        sent.append(messages)
        yield "Okay."

    for number in range(MAX_CONTEXT_TURNS):
        list(session.reply(f"message {number}", paused=lambda: False, generate=generate, speak=lambda _s: None))
    last = sent[-1]
    assert last[0]["role"] == "system"
    assert len(last) == MAX_CONTEXT_TURNS + 1
    assert last[-1] == {"role": "user", "content": f"message {MAX_CONTEXT_TURNS - 1}"}
    assert {"role": "user", "content": "message 0"} not in last
    assert len(session.turns) == MAX_CONTEXT_TURNS * 2


def test_preload_is_a_no_op_without_faster_whisper(monkeypatch):
    monkeypatch.setattr(chat_stt, "whisper_available", lambda: False)
    assert chat_stt.preload_stt() is False

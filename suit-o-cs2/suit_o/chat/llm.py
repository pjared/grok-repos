"""Pluggable chat models. The default is a local Ollama server.

An OpenAI-compatible endpoint is optional. Its URL and key come from the
environment or ``config.local.yaml``. They are never written to ``config.yaml``
and never logged.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from suit_o.config import read_yaml_mapping
from suit_o.local_config import local_config_path

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2"

OLLAMA_SETUP = (
    "Ollama isn't running. Install it from https://ollama.com, start it, "
    f"and pull a model: ollama pull {DEFAULT_MODEL}. "
    f"Suit-O talks to {DEFAULT_OLLAMA_URL}."
)
OPENAI_SETUP = (
    "This chat backend needs an OpenAI-compatible endpoint. "
    "Put chat.openai_url and chat.openai_key in config.local.yaml, "
    "or set SUIT_O_OPENAI_BASE_URL and SUIT_O_OPENAI_API_KEY. "
    "Suit-O does not write the key into config.yaml or the log."
)

Post = Callable[[str, dict, dict], Iterable[str]]


class ChatError(RuntimeError):
    """The model could not answer. The message is safe to show."""


@dataclass(frozen=True)
class ChatSettings:
    backend: str
    ollama_url: str
    model: str
    openai_url: str
    openai_key: str


def load_chat_settings(config_path: Path | None = None) -> ChatSettings:
    """Defaults, then config.yaml, then the local file, then environment variables."""

    chat: dict = {}
    if config_path is not None and Path(config_path).is_file():
        raw = read_yaml_mapping(Path(config_path))
        if isinstance(raw.get("chat"), dict):
            chat.update(raw["chat"])
        local_path = local_config_path(Path(config_path))
        if local_path.is_file():
            local = read_yaml_mapping(local_path, empty_ok=True)
            if isinstance(local.get("chat"), dict):
                chat.update(local["chat"])
    backend = _text(os.environ.get("SUIT_O_CHAT_BACKEND") or chat.get("backend") or "ollama").lower()
    if backend not in {"ollama", "openai"}:
        raise ChatError("chat.backend must be ollama or openai")
    ollama_url = _text(os.environ.get("SUIT_O_OLLAMA_URL") or chat.get("ollama_url") or DEFAULT_OLLAMA_URL)
    model = _text(os.environ.get("SUIT_O_CHAT_MODEL") or chat.get("model") or DEFAULT_MODEL)
    openai_url = _text(
        os.environ.get("SUIT_O_OPENAI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or chat.get("openai_url")
        or ""
    )
    openai_key = _text(
        os.environ.get("SUIT_O_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or chat.get("openai_key")
        or ""
    )
    return ChatSettings(
        backend=backend,
        ollama_url=ollama_url.rstrip("/") or DEFAULT_OLLAMA_URL,
        model=model or DEFAULT_MODEL,
        openai_url=openai_url.rstrip("/"),
        openai_key=openai_key,
    )


def stream_reply(
    settings: ChatSettings,
    messages: list[dict],
    *,
    post: Post | None = None,
) -> Iterator[str]:
    """Yield text fragments. ``post`` is the HTTP body stream, so tests stay offline."""

    sender = post or _http_lines
    try:
        if settings.backend == "openai":
            yield from _openai(settings, messages, sender)
        else:
            yield from _ollama(settings, messages, sender)
    except ChatError:
        raise
    except Exception as exc:
        detail = _redact(str(exc), settings.openai_key)
        if settings.backend == "openai":
            raise ChatError(f"{OPENAI_SETUP} {detail}".strip()) from exc
        raise ChatError(f"{OLLAMA_SETUP} {detail}".strip()) from exc


def _ollama(settings: ChatSettings, messages: list[dict], post: Post) -> Iterator[str]:
    url = settings.ollama_url.rstrip("/") + "/api/chat"
    payload = {"model": settings.model, "messages": messages, "stream": True}
    try:
        lines = post(url, payload, {})
    except OSError as exc:
        raise ChatError(_redact(f"{OLLAMA_SETUP} {exc}", settings.openai_key)) from exc
    for line in lines:
        piece = _ollama_token(line)
        if piece:
            yield piece


def _openai(settings: ChatSettings, messages: list[dict], post: Post) -> Iterator[str]:
    if not settings.openai_url or not settings.openai_key:
        raise ChatError(OPENAI_SETUP)
    base = settings.openai_url.rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1"):
        url = base + "/chat/completions"
    else:
        url = base + "/v1/chat/completions"
    payload = {"model": settings.model, "messages": messages, "stream": True}
    headers = {"Authorization": f"Bearer {settings.openai_key}"}
    try:
        lines = post(url, payload, headers)
    except OSError as exc:
        raise ChatError(_redact(f"{OPENAI_SETUP} {exc}", settings.openai_key)) from exc
    for line in lines:
        piece = _openai_token(line)
        if piece:
            yield piece


def _ollama_token(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    try:
        row = json.loads(text)
    except json.JSONDecodeError:
        return ""
    message = row.get("message") if isinstance(row, dict) else None
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "")


def _openai_token(line: str) -> str:
    text = line.strip()
    if not text.startswith("data:"):
        return ""
    data = text[5:].strip()
    if data == "[DONE]" or not data:
        return ""
    try:
        row = json.loads(data)
    except json.JSONDecodeError:
        return ""
    choices = row.get("choices") if isinstance(row, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
    if not isinstance(delta, dict):
        return ""
    return str(delta.get("content") or "")


def _redact(text: str, secret: str) -> str:
    cleaned = secret.strip()
    if cleaned and cleaned in text:
        return text.replace(cleaned, "[redacted]")
    return text


def _http_lines(url: str, payload: dict, headers: dict) -> Iterator[str]:
    """Stream one HTTP response. Tests do not call this."""

    import urllib.error
    import urllib.request

    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.URLError as exc:
        raise OSError(str(exc.reason)) from exc
    with response:
        for raw in response:
            yield raw.decode("utf-8", errors="replace")


def _text(value: object) -> str:
    return str(value or "").strip()

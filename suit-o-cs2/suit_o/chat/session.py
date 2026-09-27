"""In-memory chat. Nothing here is written to disk."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from suit_o.chat.persona import PERSONA_PATH, load_persona

PAUSED = "paused during match"
_SENTENCE = re.compile(r"[.!?]+(?:\s+|$)")


@dataclass
class ChatTurn:
    role: str
    text: str


@dataclass
class ChatSession:
    """One conversation. ``clear`` drops it. The persona file is read each reply."""

    persona_path: Path = PERSONA_PATH
    turns: list[ChatTurn] = field(default_factory=list)
    _cancel: bool = False
    _epoch: int = 0

    def clear(self) -> None:
        """Drop the conversation and abandon any reply that is still streaming."""

        self._cancel = True
        self.turns.clear()
        self._epoch += 1

    def stop(self) -> None:
        self._cancel = True

    def reply(
        self,
        user_text: str,
        *,
        paused: Callable[[], bool],
        generate: Callable[[list[dict]], Iterator[str]],
        speak: Callable[[str], None],
    ) -> Iterator[tuple[str, str]]:
        """Stream ``("token", text)`` pieces. Speak each finished sentence.

        A live match yields ``("status", "paused during match")`` and does not
        call the model or ``speak``.
        """

        text = user_text.strip()
        if not text:
            return
        if paused():
            yield ("status", PAUSED)
            return
        self._cancel = False
        epoch = self._epoch
        self.turns.append(ChatTurn("user", text))
        messages = self._messages()
        parts: list[str] = []
        pending = ""
        try:
            for token in generate(messages):
                if epoch != self._epoch or self._cancel or paused():
                    break
                piece = str(token)
                if not piece:
                    continue
                parts.append(piece)
                pending += piece
                yield ("token", piece)
                while True:
                    sentence, pending = _take_sentence(pending)
                    if sentence is None:
                        break
                    if epoch != self._epoch or self._cancel or paused():
                        pending = ""
                        break
                    speak(sentence)
                    yield ("sentence", sentence)
        finally:
            if epoch != self._epoch:
                return
            if pending.strip() and not self._cancel and not paused():
                speak(pending.strip())
                yield ("sentence", pending.strip())
            answer = "".join(parts).strip()
            if answer:
                self.turns.append(ChatTurn("assistant", answer))

    def _messages(self) -> list[dict]:
        messages = [{"role": "system", "content": load_persona(self.persona_path)}]
        messages.extend({"role": turn.role, "content": turn.text} for turn in self.turns)
        return messages


def _take_sentence(buffer: str) -> tuple[str | None, str]:
    match = _SENTENCE.search(buffer)
    if match is None:
        return None, buffer
    sentence = buffer[: match.end()].strip()
    rest = buffer[match.end() :]
    if not sentence:
        return None, rest
    return sentence, rest

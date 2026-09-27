"""Load and validate Suit-O's YAML config.

Push-to-talk is reserved. v1 reads the key names only to reject a bind that
matches the user's Counter-Strike voice key. It never opens a microphone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from suit_o.models import EventType

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DEFAULT_LINES_PATH = PROJECT_ROOT / "lines" / "lines.yaml"

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Playback-device names that would feed a virtual microphone or voice chat.
# Compared against the configured string and against the resolved device name.
_DISALLOWED_DEVICE_PHRASES = (
    "microphone",
    "vb-audio",
    "voicemeeter",
    "stereo mix",
    "virtual cable",
    "cable input",
    "cable output",
    "voice chat",
    "wave link",
)
_DISALLOWED_DEVICE_EXACT = frozenset({"mic", "microphone", "cable", "mic in"})


class ConfigError(ValueError):
    """The config file is present but not safe to run."""


@dataclass
class ServerConfig:
    host: str
    port: int
    token: str


@dataclass
class RemoteSpeechConfig:
    """Reserved for a future LAN HTTP TTS server. Unused in v1."""

    url: str = ""


@dataclass
class SpeechConfig:
    backend: str
    voice: str
    rate: int
    volume: float
    output_device: str
    remote: RemoteSpeechConfig = field(default_factory=RemoteSpeechConfig)


@dataclass
class PttConfig:
    keybind: str
    cs2_voice_key: str


@dataclass
class Thresholds:
    low_health: int
    full_buy_money_ct: int
    full_buy_money_t: int
    full_buy_money_unknown: int

    def full_buy_money(self, team: str | None) -> int:
        if team == "CT":
            return self.full_buy_money_ct
        if team == "T":
            return self.full_buy_money_t
        return self.full_buy_money_unknown


@dataclass
class Config:
    server: ServerConfig
    speech: SpeechConfig
    mute: bool
    default_cooldown: float
    cooldowns: dict[str, float]
    min_interval: float
    preempt_min_priority: int
    priority: dict[str, int]
    thresholds: Thresholds
    ptt: PttConfig
    lines_path: Path
    warnings: list[str] = field(default_factory=list)

    def priority_for(self, event_type: EventType) -> int:
        return self.priority[event_type.value]


def normalize_keybind(value: str) -> str:
    """Compare key names loosely: case and interior spaces do not matter."""

    return "".join(value.strip().lower().split())


def is_disallowed_output_device(name: str) -> bool:
    """True when a device name looks like a mic or a virtual cable into one.

    Suit-O plays on a headset or speakers. Names that typically show up as
    the recording side of a voice-chat route are rejected.
    """

    cleaned = name.strip().lower()
    if not cleaned:
        return False
    if cleaned in _DISALLOWED_DEVICE_EXACT:
        return True
    return any(phrase in cleaned for phrase in _DISALLOWED_DEVICE_PHRASES)


def load_config(path: Path | None = None) -> Config:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path} must contain a YAML mapping")
    return parse_config(raw, config_path=config_path)


def parse_config(raw: dict, *, config_path: Path | None = None) -> Config:
    warnings: list[str] = []
    server_raw = _mapping(raw, "server")
    speech_raw = _mapping(raw, "speech")
    remote_raw = speech_raw.get("remote") or {}
    if remote_raw and not isinstance(remote_raw, dict):
        raise ConfigError("speech.remote must be a mapping")
    cooldown_raw = _mapping(raw, "cooldowns")
    rate_raw = _mapping(raw, "rate_limit")
    priority_raw = _mapping(raw, "priority")
    threshold_raw = _mapping(raw, "thresholds")
    ptt_raw = _mapping(raw, "ptt")

    host = str(server_raw.get("host", "127.0.0.1")).strip()
    if host.lower() == "localhost":
        host = "127.0.0.1"
    if host not in LOOPBACK_HOSTS and host != "127.0.0.1":
        raise ConfigError(
            "server.host must be a loopback address (127.0.0.1). "
            "Suit-O does not accept game state from the network."
        )

    port = _as_int(server_raw.get("port", 3000), "server.port")
    if port != 0 and not 1 <= port <= 65535:
        raise ConfigError("server.port must be 0 (ephemeral) or between 1 and 65535")

    token = server_raw.get("token")
    if not isinstance(token, str) or not token.strip():
        raise ConfigError("server.token must be a non-empty string")
    token = token.strip()
    if len(token) < 8:
        raise ConfigError("server.token must be at least 8 characters")
    if token == "suito-local-change-me":
        warnings.append(
            "server.token is still the sample value. Change it in config.yaml "
            "and in gamestate_integration_suito.cfg before using a shared PC."
        )

    backend = str(speech_raw.get("backend", "pyttsx3")).strip().lower()
    if backend not in {"pyttsx3", "stub", "remote"}:
        raise ConfigError(
            "speech.backend must be 'pyttsx3', 'stub', or 'remote' "
            "(remote is reserved and not implemented)"
        )
    if backend == "remote":
        raise ConfigError(
            "speech.backend 'remote' is reserved for a future HTTP TTS server "
            "on the home LAN and is not implemented in v1. Use 'pyttsx3'."
        )

    voice = str(speech_raw.get("voice") or "").strip()
    rate = _as_int(speech_raw.get("rate", 185), "speech.rate")
    if not 80 <= rate <= 400:
        raise ConfigError("speech.rate must be between 80 and 400 words per minute")
    volume = speech_raw.get("volume", 0.85)
    if isinstance(volume, bool) or not isinstance(volume, (int, float)):
        raise ConfigError("speech.volume must be a number from 0.0 to 1.0")
    volume_f = float(volume)
    if not 0.0 <= volume_f <= 1.0:
        raise ConfigError("speech.volume must be between 0.0 and 1.0")

    output_device = str(speech_raw.get("output_device") or "").strip()
    if is_disallowed_output_device(output_device):
        raise ConfigError(
            "speech.output_device looks like a microphone or a virtual cable "
            "into voice chat. Choose a playback device (headset or speakers), "
            "or leave it blank to use the Windows default playback device."
        )

    remote_url = str((remote_raw or {}).get("url") or "").strip()
    if remote_url:
        warnings.append(
            "speech.remote.url is reserved for a future version and is ignored. "
            "v1 does not call a remote TTS server."
        )

    mute = bool(raw.get("mute", False))

    default_cooldown = _as_float(
        cooldown_raw.get("default_seconds", 6), "cooldowns.default_seconds"
    )
    if default_cooldown < 0:
        raise ConfigError("cooldowns.default_seconds cannot be negative")
    per_event_raw = cooldown_raw.get("per_event") or {}
    if not isinstance(per_event_raw, dict):
        raise ConfigError("cooldowns.per_event must be a mapping")
    known = {item.value for item in EventType}
    cooldowns: dict[str, float] = {}
    for name, value in per_event_raw.items():
        key = str(name)
        if key not in known:
            warnings.append(f"Ignoring unknown cooldown event '{key}'")
            continue
        seconds = _as_float(value, f"cooldowns.per_event.{key}")
        if seconds < 0:
            raise ConfigError(f"cooldowns.per_event.{key} cannot be negative")
        cooldowns[key] = seconds

    min_interval = _as_float(
        rate_raw.get("min_interval_seconds", 2.0), "rate_limit.min_interval_seconds"
    )
    if min_interval < 0:
        raise ConfigError("rate_limit.min_interval_seconds cannot be negative")

    preempt_min = _as_int(raw.get("preempt_min_priority", 70), "preempt_min_priority")

    if not priority_raw:
        raise ConfigError("priority must list every event")
    priority: dict[str, int] = {}
    for name, value in priority_raw.items():
        key = str(name)
        if key not in known:
            warnings.append(f"Ignoring unknown priority event '{key}'")
            continue
        priority[key] = _as_int(value, f"priority.{key}")
    missing = sorted(known - set(priority))
    if missing:
        raise ConfigError("priority is missing events: " + ", ".join(missing))

    low_health = _as_int(threshold_raw.get("low_health", 30), "thresholds.low_health")
    if not 1 <= low_health <= 99:
        raise ConfigError("thresholds.low_health must be between 1 and 99")
    full_ct = _as_int(
        threshold_raw.get("full_buy_money_ct", 4100), "thresholds.full_buy_money_ct"
    )
    full_t = _as_int(
        threshold_raw.get("full_buy_money_t", 3700), "thresholds.full_buy_money_t"
    )
    full_unknown = _as_int(
        threshold_raw.get("full_buy_money_unknown", 4000),
        "thresholds.full_buy_money_unknown",
    )
    for label, amount in (
        ("full_buy_money_ct", full_ct),
        ("full_buy_money_t", full_t),
        ("full_buy_money_unknown", full_unknown),
    ):
        if amount < 0:
            raise ConfigError(f"thresholds.{label} cannot be negative")

    keybind = str(ptt_raw.get("keybind") or "")
    voice_key = str(ptt_raw.get("cs2_voice_key") or "")
    if keybind.strip():
        warnings.append(
            "ptt.keybind is reserved for a future push-to-talk and does nothing "
            "in v1. Suit-O will not open a microphone or join voice chat."
        )
        if normalize_keybind(keybind) == normalize_keybind(voice_key) and normalize_keybind(
            keybind
        ):
            raise ConfigError(
                "ptt.keybind must be different from ptt.cs2_voice_key "
                f"({voice_key!r}). Suit-O must not share Counter-Strike's voice key."
            )

    lines_value = raw.get("lines_file", "lines/lines.yaml")
    lines_path = Path(str(lines_value))
    if not lines_path.is_absolute():
        base = config_path.parent if config_path is not None else PROJECT_ROOT
        lines_path = (base / lines_path).resolve()

    return Config(
        server=ServerConfig(host=host, port=port, token=token),
        speech=SpeechConfig(
            backend=backend,
            voice=voice,
            rate=rate,
            volume=volume_f,
            output_device=output_device,
            remote=RemoteSpeechConfig(url=remote_url),
        ),
        mute=mute,
        default_cooldown=default_cooldown,
        cooldowns=cooldowns,
        min_interval=min_interval,
        preempt_min_priority=preempt_min,
        priority=priority,
        thresholds=Thresholds(
            low_health=low_health,
            full_buy_money_ct=full_ct,
            full_buy_money_t=full_t,
            full_buy_money_unknown=full_unknown,
        ),
        ptt=PttConfig(keybind=keybind.strip(), cs2_voice_key=voice_key.strip()),
        lines_path=lines_path,
        warnings=warnings,
    )


def _mapping(raw: dict, key: str) -> dict:
    value = raw.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a mapping")
    return value


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{label} must be an integer")
    return value


def _as_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} must be a number")
    return float(value)

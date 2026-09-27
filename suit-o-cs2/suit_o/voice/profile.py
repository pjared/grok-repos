"""Named voice profiles stored under a local ``voices/`` folder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from suit_o.voice.runtime import MODEL_ID

CLONE_PREFIX = "Clone: "


class ProfileError(ValueError):
    """A voice profile name or folder is not usable."""


@dataclass(frozen=True)
class VoiceProfile:
    name: str
    slug: str
    model: str
    directory: Path
    reference_wav: Path
    prompt_wav: Path
    duration_seconds: float
    created: str

    @property
    def label(self) -> str:
        return clone_label(self.name)


def clone_label(name: str) -> str:
    return f"{CLONE_PREFIX}{name}"


def is_clone_label(label: str) -> bool:
    return label.strip().startswith(CLONE_PREFIX)


def profile_name_from_label(label: str) -> str:
    if not is_clone_label(label):
        raise ProfileError(f"{label!r} is not a cloned voice")
    name = label.strip()[len(CLONE_PREFIX) :].strip()
    if not name:
        raise ProfileError("The cloned voice needs a name")
    return name


def voices_root(path: Path) -> Path:
    return Path(path)


def slugify(name: str) -> str:
    """Folder name for a profile. Rejects path tricks."""

    cleaned = name.strip()
    if not cleaned:
        raise ProfileError("The voice needs a name")
    if any(mark in cleaned for mark in ("/", "\\", ":", "\0")):
        raise ProfileError("The voice name cannot include a path")
    slug_chars: list[str] = []
    for char in cleaned.lower():
        if char.isalnum():
            slug_chars.append(char)
        elif char in {" ", "-", "_"}:
            if slug_chars and slug_chars[-1] != "-":
                slug_chars.append("-")
    slug = "".join(slug_chars).strip("-")[:40]
    if not slug:
        raise ProfileError("The voice name needs a letter or number")
    return slug


def list_profiles(root: Path) -> list[VoiceProfile]:
    """Profiles in ``root``, sorted by name. Missing or broken folders are skipped."""

    base = voices_root(root)
    if not base.is_dir():
        return []
    found: list[VoiceProfile] = []
    for folder in sorted(base.iterdir(), key=lambda item: item.name.lower()):
        if not folder.is_dir():
            continue
        try:
            found.append(load_profile(folder))
        except ProfileError:
            continue
    found.sort(key=lambda item: item.name.lower())
    return found


def load_profile(folder: Path) -> VoiceProfile:
    meta_path = folder / "profile.yaml"
    if not meta_path.is_file():
        raise ProfileError(f"No profile.yaml in {folder}")
    raw = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProfileError(f"{meta_path} must be a mapping")
    name = str(raw.get("name") or "").strip()
    slug = str(raw.get("slug") or folder.name).strip()
    model = str(raw.get("model") or "").strip()
    if not name or not slug:
        raise ProfileError(f"{meta_path} is missing a name")
    reference = folder / str(raw.get("reference") or "reference.wav")
    prompt = folder / str(raw.get("prompt") or "prompt.wav")
    if not reference.is_file() or not prompt.is_file():
        raise ProfileError(f"{name} is missing its reference audio")
    try:
        duration = float(raw.get("duration_seconds") or 0)
    except (TypeError, ValueError) as exc:
        raise ProfileError(f"{name} has a bad duration") from exc
    return VoiceProfile(
        name=name,
        slug=slug,
        model=model or MODEL_ID,
        directory=folder,
        reference_wav=reference,
        prompt_wav=prompt,
        duration_seconds=duration,
        created=str(raw.get("created") or ""),
    )


def find_profile(root: Path, name: str) -> VoiceProfile:
    """Find a profile by display name or slug."""

    needle = name.strip().lower()
    if not needle:
        raise ProfileError("Choose a cloned voice")
    matches = [
        profile
        for profile in list_profiles(root)
        if profile.name.lower() == needle or profile.slug == needle
    ]
    if not matches:
        known = ", ".join(profile.name for profile in list_profiles(root)) or "(none)"
        raise ProfileError(f"No cloned voice named {name!r}. Profiles: {known}")
    return matches[0]


def write_profile(
    root: Path,
    name: str,
    reference_wav: Path,
    prompt_wav: Path,
    duration_seconds: float,
    sample_rate: int,
) -> VoiceProfile:
    """Create ``voices/<slug>/`` and return the profile. Does not run the model."""

    slug = slugify(name)
    base = voices_root(root)
    folder = base / slug
    suffix = 2
    while folder.exists() and not (folder / "profile.yaml").is_file():
        folder = base / f"{slug}-{suffix}"
        suffix += 1
    if folder.exists() and (folder / "profile.yaml").is_file():
        existing = load_profile(folder)
        if existing.name.lower() != name.strip().lower():
            folder = base / f"{slug}-{suffix}"
            while folder.exists():
                suffix += 1
                folder = base / f"{slug}-{suffix}"
    folder.mkdir(parents=True, exist_ok=True)
    reference_dest = folder / "reference.wav"
    prompt_dest = folder / "prompt.wav"
    if Path(reference_wav).resolve() != reference_dest.resolve():
        reference_dest.write_bytes(Path(reference_wav).read_bytes())
    if Path(prompt_wav).resolve() != prompt_dest.resolve():
        prompt_dest.write_bytes(Path(prompt_wav).read_bytes())
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "name": name.strip(),
        "slug": folder.name,
        "model": MODEL_ID,
        "created": created,
        "duration_seconds": round(float(duration_seconds), 2),
        "sample_rate": int(sample_rate),
        "reference": "reference.wav",
        "prompt": "prompt.wav",
    }
    text = yaml.safe_dump(payload, sort_keys=False)
    (folder / "profile.yaml").write_text(text, encoding="utf-8")
    (folder / "cache").mkdir(exist_ok=True)
    return load_profile(folder)

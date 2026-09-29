"""Suit-O's own icon: the one you upload from the header.

The image is squared, resized, and saved as a PNG and a Windows .ico in the
gitignored ``branding/`` folder, so Update never replaces it. The window,
the taskbar, and the Desktop shortcut use it.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from suit_o.config import PROJECT_ROOT

BRANDING_DIR = PROJECT_ROOT / "branding"
ICON_PNG = "icon.png"
ICON_SMALL = "icon-small.png"
ICON_ICO = "icon.ico"
ICON_SIZE = 256
SMALL_SIZE = 28
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".ico")
# Windows groups taskbar buttons by this id. Without it, Suit-O shows Python's icon.
APP_ID = "SuitO.Desktop"
SHORTCUT_TARGET = "Start Suit-O GUI.vbs"


class BrandingError(RuntimeError):
    """The image could not be used. The message is safe to show."""


def icon_file(folder: Path = BRANDING_DIR, name: str = ICON_PNG) -> Path | None:
    path = Path(folder) / name
    return path if path.is_file() else None


def save_icon(source: Path, folder: Path = BRANDING_DIR) -> Path:
    """Square, resize, and save ``source`` as Suit-O's icon. Returns the PNG path."""

    source = Path(source)
    if source.suffix.lower() not in IMAGE_TYPES:
        raise BrandingError("Pick a PNG, JPEG, WebP, BMP, GIF, or ICO image.")
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise BrandingError("Setting an icon needs Pillow. Click Update to install it.") from exc
    try:
        with Image.open(source) as opened:
            opened.load()
            image = opened.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise BrandingError(f"Could not read {source.name} as an image.") from exc
    if image.width < 16 or image.height < 16:
        raise BrandingError("That image is too small. Use one at least 64 by 64 pixels.")
    square = ImageOps.fit(image, (ICON_SIZE, ICON_SIZE), method=Image.LANCZOS)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    png = folder / ICON_PNG
    _save_atomic(lambda path: square.save(path, format="PNG"), png)
    small = square.resize((SMALL_SIZE, SMALL_SIZE), Image.LANCZOS)
    _save_atomic(lambda path: small.save(path, format="PNG"), folder / ICON_SMALL)
    _save_atomic(lambda path: square.save(path, format="ICO", sizes=ICO_SIZES), folder / ICON_ICO)
    return png


def remove_icon(folder: Path = BRANDING_DIR) -> None:
    for name in (ICON_PNG, ICON_SMALL, ICON_ICO):
        try:
            (Path(folder) / name).unlink()
        except FileNotFoundError:
            continue


def set_windows_app_id(*, platform: str | None = None, shell32=None) -> bool:
    """Give Suit-O its own taskbar identity, so the taskbar shows its icon."""

    if (platform or sys.platform) != "win32":
        return False
    try:
        if shell32 is None:
            import ctypes

            shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        return False
    return True


def shortcut_command(ico: Path) -> list[str]:
    """PowerShell that points every Desktop shortcut for Suit-O at ``ico``.

    Only shortcuts whose target or arguments name the Suit-O launcher change.
    Prints how many it updated.
    """

    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        "$desktops = @([Environment]::GetFolderPath('Desktop'), "
        "(Join-Path $env:PUBLIC 'Desktop')) | Where-Object { $_ -and (Test-Path $_) } | "
        "Select-Object -Unique; "
        "$count = 0; "
        "foreach ($dir in $desktops) { "
        "Get-ChildItem -LiteralPath $dir -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object { "
        "$link = $shell.CreateShortcut($_.FullName); "
        f"if (($link.TargetPath + ' ' + $link.Arguments) -like '*{SHORTCUT_TARGET}*') {{ "
        f"$link.IconLocation = '{_ps_quote(str(ico))},0'; $link.Save(); $count++ }} }} }}; "
        "Write-Output $count"
    )
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script]


def update_desktop_shortcut(
    ico: Path,
    *,
    runner: Callable[[list[str]], tuple[int, str]] | None = None,
    platform: str | None = None,
) -> int:
    """Point the Desktop shortcut at ``ico``. Returns how many shortcuts changed."""

    if (platform or sys.platform) != "win32":
        return 0
    code, output = (runner or _run_hidden)(shortcut_command(ico))
    if code != 0:
        return 0
    try:
        return int(output.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return 0


def _ps_quote(text: str) -> str:
    """Escape for a single-quoted PowerShell string."""

    return text.replace("'", "''")


def _run_hidden(args: list[str]) -> tuple[int, str]:
    import subprocess

    from suit_o.procs import hidden_window_kwargs

    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            **hidden_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return completed.returncode, completed.stdout or ""


def _save_atomic(write: Callable[[Path], None], dest: Path) -> None:
    temp = dest.with_name(dest.name + ".tmp")
    write(temp)
    temp.replace(dest)

"""Suit-O's uploaded icon: image handling, the taskbar id, and the Desktop shortcut."""

from __future__ import annotations

from pathlib import Path

from suit_o.branding import (
    APP_ID,
    ICON_ICO,
    ICON_PNG,
    ICON_SIZE,
    ICON_SMALL,
    SHORTCUT_TARGET,
    SMALL_SIZE,
    BrandingError,
    icon_file,
    remove_icon,
    save_icon,
    set_windows_app_id,
    shortcut_command,
    update_desktop_shortcut,
)


def _image(path: Path, size: tuple[int, int], mode: str = "RGB") -> Path:
    import pytest

    Image = pytest.importorskip("PIL.Image")

    Image.new(mode, size, (200, 30, 30)).save(path)
    return path


def test_any_image_becomes_a_square_png_small_png_and_ico(tmp_path: Path):
    import pytest

    Image = pytest.importorskip("PIL.Image")

    source = _image(tmp_path / "photo.jpg", (640, 360))
    folder = tmp_path / "branding"
    png = save_icon(source, folder)
    assert png == folder / ICON_PNG
    with Image.open(png) as saved:
        assert saved.size == (ICON_SIZE, ICON_SIZE)
    with Image.open(folder / ICON_SMALL) as small:
        assert small.size == (SMALL_SIZE, SMALL_SIZE)
    with Image.open(folder / ICON_ICO) as ico:
        assert ico.format == "ICO"
        assert (16, 16) in ico.info.get("sizes", set()) or ico.size[0] >= 16
    assert not list(folder.glob("*.tmp"))
    assert icon_file(folder) == png

    remove_icon(folder)
    assert icon_file(folder) is None
    remove_icon(folder)


def test_bad_files_are_refused_with_a_plain_message(tmp_path: Path):
    text = tmp_path / "notes.txt"
    text.write_text("hi", encoding="utf-8")
    fake = tmp_path / "broken.png"
    fake.write_text("not an image", encoding="utf-8")
    tiny = _image(tmp_path / "tiny.png", (8, 8))
    for path, words in ((text, "PNG, JPEG"), (fake, "Could not read"), (tiny, "too small")):
        try:
            save_icon(path, tmp_path / "branding")
        except BrandingError as exc:
            assert words in str(exc)
        else:
            raise AssertionError(f"{path.name} was accepted")
    assert icon_file(tmp_path / "branding") is None


def test_the_taskbar_id_is_set_only_on_windows():
    calls: list[str] = []

    class _Shell:
        def SetCurrentProcessExplicitAppUserModelID(self, value):  # noqa: N802
            calls.append(value)

    assert set_windows_app_id(platform="linux", shell32=_Shell()) is False
    assert set_windows_app_id(platform="win32", shell32=_Shell()) is True
    assert calls == [APP_ID]


def test_only_suit_o_shortcuts_on_the_desktop_are_changed():
    ico = Path(r"C:\Users\Someone\Suit-O's\branding\icon.ico")
    command = shortcut_command(ico)
    assert command[0] == "powershell"
    script = command[-1]
    assert SHORTCUT_TARGET in script
    assert "Suit-O''s" in script
    assert "IconLocation" in script

    seen: list[list[str]] = []
    assert update_desktop_shortcut(ico, runner=lambda args: seen.append(args) or (0, "1\n"), platform="win32") == 1
    assert update_desktop_shortcut(ico, runner=lambda args: (1, ""), platform="win32") == 0
    assert update_desktop_shortcut(ico, runner=lambda args: (0, "oops"), platform="win32") == 0
    assert update_desktop_shortcut(ico, runner=lambda args: seen.append(args) or (0, "1"), platform="linux") == 0
    assert len(seen) == 1


def test_the_header_shows_a_placeholder_then_the_uploaded_icon(tmp_path: Path, monkeypatch):
    import shutil

    from tkutil import open_tk_or_skip

    from suit_o import branding
    from suit_o.app import SuitOApp
    from suit_o.config import DEFAULT_CONFIG_PATH, load_config
    from suit_o.speech.stub import StubSpeechBackend

    probe = open_tk_or_skip()
    probe.destroy()
    from suit_o.gui.window import SuitOWindow

    folder = tmp_path / "branding"
    monkeypatch.setattr(branding, "BRANDING_DIR", folder)
    monkeypatch.setattr(branding.icon_file, "__defaults__", (folder, ICON_PNG))
    monkeypatch.setattr(branding.save_icon, "__defaults__", (folder,))
    monkeypatch.setattr(branding.remove_icon, "__defaults__", (folder,))
    config = tmp_path / "config.yaml"
    shutil.copy(DEFAULT_CONFIG_PATH, config)
    shutil.copytree(DEFAULT_CONFIG_PATH.parent / "lines", tmp_path / "lines")
    app = SuitOApp(load_config(config), backend=StubSpeechBackend(), config_path=config)
    window = SuitOWindow(app)
    try:
        assert window.icon_button.cget("text") == "+ Icon"
        source = _image(tmp_path / "suit.png", (300, 300))
        monkeypatch.setattr("tkinter.filedialog.askopenfilename", lambda **_kw: str(source))
        monkeypatch.setattr(window, "_update_shortcut_icon", lambda ico: None)
        window._choose_icon()
        assert window.icon_button.cget("text") == ""
        assert window.icon_button.cget("image")
        assert (folder / ICON_ICO).is_file()
        window._remove_icon()
        assert window.icon_button.cget("text") == "+ Icon"
    finally:
        window.root.destroy()
        app.stop()

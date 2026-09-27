"""python -m suit_o.gui

Starts the same listener as ``python -m suit_o`` and opens the desktop
window. On Windows, pythonw runs this without a console.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from suit_o.config import DEFAULT_CONFIG_PATH, PROJECT_ROOT, ConfigError, load_config

logger = logging.getLogger("suit_o")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="suit-o-gui",
        description="Suit-O desktop window. Listens for CS2 and speaks on a playback device.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml (default: suit-o-cs2/config.yaml)",
    )
    parser.add_argument("--mute", action="store_true", help="Start muted")
    args = parser.parse_args(argv)
    _configure_logging()
    try:
        return _run(args.config, start_muted=args.mute)
    except Exception:
        logger.exception("Suit-O GUI failed")
        _show_fatal("Suit-O could not start. See suit-o.log in the suit-o-cs2 folder.")
        return 1


def _run(config_path: Path, *, start_muted: bool) -> int:
    try:
        config = load_config(config_path)
    except (ConfigError, OSError, ValueError) as exc:
        logger.error("Config error: %s", exc)
        _show_fatal(f"Config error: {exc}")
        return 2
    if start_muted:
        config.mute = True
    for warning in config.warnings:
        logger.warning("%s", warning)

    from suit_o.app import SuitOApp

    try:
        app = SuitOApp(config, config_path=config_path)
    except NotImplementedError as exc:
        logger.error("%s", exc)
        _show_fatal(str(exc))
        return 2

    try:
        app.start(console=False)
    except OSError as exc:
        message = (
            f"Could not listen on {config.server.host}:{config.server.port}: {exc}\n"
            "Another program is using that port, or the address is not available."
        )
        logger.error("%s", message)
        _show_fatal(message)
        return 1

    try:
        from suit_o.gui.window import SuitOWindow
    except ImportError as exc:
        logger.error("%s", exc)
        app.stop()
        _show_fatal(
            "Suit-O's window needs tkinter, which is included with the official "
            "Python installer from python.org."
        )
        return 2

    try:
        SuitOWindow(app).run()
    finally:
        app.stop()
    return 0


def _configure_logging() -> None:
    handlers: list[logging.Handler] = []
    try:
        handlers.append(logging.FileHandler(PROJECT_ROOT / "suit-o.log", encoding="utf-8"))
    except OSError:
        pass
    if sys.stderr is not None:
        try:
            handlers.append(logging.StreamHandler(sys.stderr))
        except Exception:
            pass
    if not handlers:
        handlers.append(logging.NullHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


def _show_fatal(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Suit-O", message)
        root.destroy()
    except Exception:
        if sys.stderr is not None:
            print(message, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

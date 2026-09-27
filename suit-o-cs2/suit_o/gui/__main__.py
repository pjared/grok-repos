"""python -m suit_o.gui

Starts the same listener as ``python -m suit_o`` and opens the desktop
window. On Windows, pythonw runs this without a console.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from suit_o.config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from suit_o.local_config import migrate_user_settings
from suit_o.reload import consume_activity_handoff, consume_restart_state, write_activity_handoff, write_restart_state

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
        _show_fatal("Suit-O could not start.")
        return 1


def _run(config_path: Path, *, start_muted: bool) -> int:
    try:
        try:
            migrate_user_settings(config_path)
        except (ConfigError, OSError, ValueError) as exc:
            logger.warning("Could not move personal settings into config.local.yaml: %s", exc)
        token_warning = _ensure_personal_token(config_path)
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

    restart = consume_restart_state(config_path)
    try:
        app = SuitOApp(config, config_path=config_path)
    except NotImplementedError as exc:
        if restart is not None:
            write_restart_state(config_path, restart)
        logger.error("%s", exc)
        _show_fatal(str(exc))
        return 2
    if restart is not None and restart.greeted:
        app.detector.mark_greeted()
    if token_warning:
        app.note(token_warning)

    app.restore_activity(consume_activity_handoff())
    try:
        app.start(console=False)
    except OSError as exc:
        if restart is not None:
            write_restart_state(config_path, restart)
        write_activity_handoff(
            [(entry.at, entry.message) for entry in app.activity()],
            secret=config.server.token,
        )
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
        SuitOWindow(app, restart_state=restart).run()
    finally:
        app.stop()
    return 0


def _ensure_personal_token(config_path: Path) -> str:
    """Keep or write the GSI token. The token is not logged. Returns a window warning."""

    try:
        from suit_o.gsi_token import ensure_personal_token

        warning = ensure_personal_token(config_path).warning
    except Exception:
        logger.warning("Could not write a personal GSI token.")
        return ""
    if warning:
        logger.warning("%s", warning)
    return warning


def _configure_logging() -> None:
    from suit_o.logging_setup import configure_logging

    configure_logging()


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

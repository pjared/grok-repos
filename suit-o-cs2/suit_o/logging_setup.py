"""Console logging only. Suit-O does not keep a log file."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from suit_o.config import PROJECT_ROOT

LOG_NAME = "suit-o.log"


def log_path(root: Path | None = None) -> Path:
    return (PROJECT_ROOT if root is None else Path(root)) / LOG_NAME


def discard_log_file(root: Path | None = None) -> None:
    """Delete a leftover ``suit-o.log`` once. Missing is fine."""

    try:
        log_path(root).unlink(missing_ok=True)
    except OSError:
        return


def configure_logging(root: Path | None = None) -> None:
    """Log to the console, drop any file handler, and delete ``suit-o.log``."""

    discard_log_file(root)
    handlers: list[logging.Handler] = []
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

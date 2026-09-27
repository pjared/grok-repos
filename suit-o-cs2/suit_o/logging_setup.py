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
    """Delete a leftover ``suit-o.log`` once. Missing is fine.

    A handler still attached to that file is closed first. Windows will not
    delete a file another handle in this process has open.
    """

    path = log_path(root)
    _release_log_handlers(path)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _release_log_handlers(path: Path) -> None:
    logger = logging.getLogger()
    for handler in list(logger.handlers):
        if not isinstance(handler, logging.FileHandler):
            continue
        base = getattr(handler, "baseFilename", "")
        if not base or not _same_log(Path(base), path):
            continue
        logger.removeHandler(handler)
        try:
            handler.flush()
            handler.close()
        except OSError:
            pass


def _same_log(candidate: Path, path: Path) -> bool:
    if candidate.name != LOG_NAME and path.name != LOG_NAME:
        return False
    try:
        return candidate.resolve() == path.resolve()
    except OSError:
        return candidate.name == path.name == LOG_NAME


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

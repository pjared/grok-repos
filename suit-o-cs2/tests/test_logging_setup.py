"""Startup logging does not keep suit-o.log."""

from __future__ import annotations

import logging
from pathlib import Path

from suit_o.logging_setup import configure_logging, discard_log_file


def test_startup_deletes_the_log_and_drops_file_handlers(tmp_path: Path):
    log = tmp_path / "suit-o.log"
    log.write_text("old line\n", encoding="utf-8")
    root = logging.getLogger()
    previous = list(root.handlers)
    file_handler = logging.FileHandler(log, encoding="utf-8")
    root.addHandler(file_handler)
    try:
        configure_logging(tmp_path)
        assert not log.exists()
        assert not any(isinstance(handler, logging.FileHandler) for handler in root.handlers)
        discard_log_file(tmp_path)
        assert not (tmp_path / "suit-o.log").exists()
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        for handler in previous:
            root.addHandler(handler)

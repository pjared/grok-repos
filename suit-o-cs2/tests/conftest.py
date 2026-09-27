"""Keep pytest away from the developer's config.local.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest

from suit_o.local_config import LOCAL_CONFIG_NAME, redirect_project_local_config


@pytest.fixture(autouse=True)
def isolate_project_local_config(tmp_path: Path):
    """Reads and writes of the shipped local config go to a throwaway file."""

    sink = tmp_path / "project-local-sink" / LOCAL_CONFIG_NAME
    sink.parent.mkdir(parents=True, exist_ok=True)
    redirect_project_local_config(sink)
    yield sink
    redirect_project_local_config(None)

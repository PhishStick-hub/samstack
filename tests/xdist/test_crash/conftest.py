"""Crash test conftest: forces gw0 Docker startup failure.

Uses an invalid sam_image to trigger container start failure in gw0.
gw0 writes "error" key to shared state; gw1+ wait_for_state_key
detects it and calls pytest.fail().
"""

from __future__ import annotations

from pathlib import Path

import pytest

from samstack.settings import SamStackSettings

FIXTURE_DIR = Path(__file__).parent.parent.parent.parent / "fixtures" / "hello_world"


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="nonexistent:latest",
        project_root=FIXTURE_DIR,
        log_dir="logs/sam",
        add_gitignore=False,
    )

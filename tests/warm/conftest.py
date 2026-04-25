"""Integration test config for warm container verification."""

from __future__ import annotations

from pathlib import Path

import pytest

from samstack.settings import SamStackSettings

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "warm_check"


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        project_root=FIXTURE_DIR,
        log_dir="logs/sam",
        add_gitignore=False,
    )


@pytest.fixture(scope="session")
def warm_functions() -> list[str]:
    return ["WarmCheckFunction"]

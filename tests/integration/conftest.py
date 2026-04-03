"""
Shared fixtures for integration tests against a real LocalStack instance.
SAM build/api/lambda fixtures are NOT needed here — only LocalStack infrastructure.
"""

from __future__ import annotations

import pytest

from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
    )

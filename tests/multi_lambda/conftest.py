"""Integration fixtures for the multi-Lambda mock scenario.

Configures samstack against ``tests/fixtures/multi_lambda`` and defines
function-scoped wrappers that auto-clear each mock between tests. Run this
suite in isolation::

    uv run pytest tests/multi_lambda/ -v
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from samstack.mock import LambdaMock
from samstack.settings import SamStackSettings

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "multi_lambda"


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        project_root=FIXTURE_DIR,
        template="template.test.yaml",
        log_dir="logs/sam",
        add_gitignore=False,
    )


@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Inject the HTTP URL Lambda A uses to reach Mock B through API Gateway."""
    sam_env_vars["Parameters"]["LAMBDA_B_URL"] = "http://sam-api:3000/mock-b"
    return sam_env_vars


@pytest.fixture(scope="session", autouse=True)
def _mock_b_session(
    make_lambda_mock: Callable[..., LambdaMock],
) -> LambdaMock:
    # autouse forces registration before ``sam_build`` reads ``sam_env_vars``
    # and writes env_vars.json — otherwise Mock B's env vars never reach the
    # Lambda container.
    return make_lambda_mock("MockBFunction", alias="mock-b")


@pytest.fixture
def mock_b(_mock_b_session: LambdaMock) -> Iterator[LambdaMock]:
    """Function-scoped wrapper: clears spy + response queue before each test."""
    _mock_b_session.clear()
    yield _mock_b_session

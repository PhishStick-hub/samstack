"""
Configure samstack to use the hello_world test fixture project.
All integration tests share one session: build → start-api → start-lambda → tests.
"""

from __future__ import annotations

from pathlib import Path

import boto3
import pytest
from mypy_boto3_s3 import S3Client

from samstack.settings import SamStackSettings

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hello_world"
INTEGRATION_BUCKET = "samstack-integration-test"

_UNIT_FILES = frozenset(
    {"test_settings.py", "test_process.py", "test_errors.py", "test_plugin.py"}
)
_CRASH_FILES = frozenset(
    {"test_subcontainer_teardown.py", "test_ryuk_crash.py", "test_warm_crash.py"}
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parts = item.path.parts
        name = item.path.name
        if "unit" in parts or name in _UNIT_FILES:
            item.add_marker(pytest.mark.unit)
        elif "warm" in parts:
            item.add_marker(pytest.mark.warm)
        elif "multi_lambda" in parts:
            item.add_marker(pytest.mark.multi)
        elif "test_crash" in parts:
            item.add_marker(pytest.mark.xdist_crash)
        elif "xdist" in parts:
            item.add_marker(pytest.mark.xdist)
        elif name in _CRASH_FILES:
            item.add_marker(pytest.mark.crash)
        else:
            item.add_marker(pytest.mark.integration)


# multi_lambda/, warm/, and xdist/ each pin samstack_settings to a different
# fixture project. Session-scoped SAM fixtures (sam_build, sam_api,
# sam_lambda_endpoint) cache the first resolution across the whole run, so
# mixing suites in one session makes tests hit the wrong template. Ignore
# them unless explicitly targeted on the CLI.
def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    path_str = str(collection_path)
    for suite in ("multi_lambda", "warm", "xdist"):
        if suite in path_str:
            args = config.invocation_params.args
            explicit = any(suite in str(arg) for arg in args)
            return None if explicit else True
    return None


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
    return ["HelloWorldFunction"]


@pytest.fixture(scope="session")
def warm_api_routes() -> dict[str, str]:
    return {"HelloWorldFunction": "/hello"}


@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Extend default env vars with TEST_BUCKET for localstack integration test."""
    sam_env_vars["Parameters"]["TEST_BUCKET"] = INTEGRATION_BUCKET
    return sam_env_vars


@pytest.fixture(scope="session")
def s3_client(localstack_endpoint: str) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


@pytest.fixture(scope="session")
def integration_bucket(s3_client: S3Client) -> str:
    s3_client.create_bucket(Bucket=INTEGRATION_BUCKET)
    return INTEGRATION_BUCKET

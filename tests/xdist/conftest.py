"""Integration test config for xdist parallel test suite.

Shares Docker infra (LocalStack + SAM) across all xdist workers.
Run with: uv run pytest tests/xdist/ -v -n 2 --timeout=300
"""

from __future__ import annotations

from pathlib import Path

import boto3
import pytest
from mypy_boto3_s3 import S3Client

from samstack.settings import SamStackSettings

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "hello_world"
INTEGRATION_BUCKET = "samstack-xdist-integration-test"


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        project_root=FIXTURE_DIR,
        log_dir="logs/sam",
        add_gitignore=False,
    )


@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Extend default env vars with TEST_BUCKET for xdist integration tests."""
    sam_env_vars["Parameters"]["TEST_BUCKET"] = INTEGRATION_BUCKET
    return sam_env_vars


@pytest.fixture(scope="session")
def s3_client(localstack_endpoint: str) -> S3Client:
    """Session-scoped boto3 S3 client pointed at LocalStack."""
    return boto3.client(
        "s3",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


@pytest.fixture(scope="session")
def integration_bucket(s3_client: S3Client) -> str:
    """Create the integration test bucket before any test uses it."""
    s3_client.create_bucket(Bucket=INTEGRATION_BUCKET)
    return INTEGRATION_BUCKET


@pytest.fixture(scope="session")
def warm_functions() -> list[str]:
    return ["HelloWorldFunction"]


@pytest.fixture(scope="session")
def warm_api_routes() -> dict[str, str]:
    return {"HelloWorldFunction": "/hello"}

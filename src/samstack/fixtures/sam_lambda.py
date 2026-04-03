from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import boto3
import pytest

if TYPE_CHECKING:
    from mypy_boto3_lambda import LambdaClient

from samstack._constants import LOCALSTACK_ACCESS_KEY, LOCALSTACK_SECRET_KEY
from samstack.fixtures._sam_container import _run_sam_service
from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def sam_lambda_extra_args() -> list[str]:
    """
    Extra CLI args appended to `sam local start-lambda` after the defaults.

    Override in your conftest.py:

        @pytest.fixture(scope="session")
        def sam_lambda_extra_args() -> list[str]:
            return ["--debug"]
    """
    return []


@pytest.fixture(scope="session")
def sam_lambda_endpoint(
    samstack_settings: SamStackSettings,
    sam_build: None,
    docker_network: str,
    sam_lambda_extra_args: list[str],
) -> Iterator[str]:
    """
    Start `sam local start-lambda` in Docker. Yields the endpoint URL
    http://127.0.0.1:{lambda_port} for use with boto3 Lambda client.
    Logs written to {log_dir}/start-lambda.log.
    """
    with _run_sam_service(
        settings=samstack_settings,
        docker_network=docker_network,
        subcommand="start-lambda",
        port=samstack_settings.lambda_port,
        warm_containers="EAGER",
        settings_extra_args=samstack_settings.start_lambda_args,
        fixture_extra_args=sam_lambda_extra_args,
        log_filename="start-lambda.log",
        wait_mode="port",
    ) as endpoint:
        yield endpoint


@pytest.fixture(scope="session")
def lambda_client(
    samstack_settings: SamStackSettings,
    sam_lambda_endpoint: str,
) -> LambdaClient:
    """
    Boto3 Lambda client pointed at the local SAM Lambda endpoint.

    Use this to invoke functions directly without HTTP:
        result = lambda_client.invoke(FunctionName="MyFunction", Payload=b"{}")
    """
    return boto3.client(
        "lambda",
        endpoint_url=sam_lambda_endpoint,
        region_name=samstack_settings.region,
        aws_access_key_id=LOCALSTACK_ACCESS_KEY,
        aws_secret_access_key=LOCALSTACK_SECRET_KEY,
    )

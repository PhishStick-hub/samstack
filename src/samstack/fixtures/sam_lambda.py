from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal

import boto3
import pytest
from botocore.config import Config

if TYPE_CHECKING:
    from mypy_boto3_lambda import LambdaClient

from samstack._constants import LOCALSTACK_ACCESS_KEY, LOCALSTACK_SECRET_KEY
from samstack._errors import SamStartupError
from samstack._xdist import StateKeys, xdist_shared_session
from samstack.fixtures._sam_container import _run_sam_service
from samstack.settings import SamStackSettings

_logger = logging.getLogger("samstack")


def _warm_containers_mode(warm_functions: list[str]) -> Literal["LAZY", "EAGER"]:
    return "LAZY" if warm_functions else "EAGER"


def _pre_warm_functions(
    endpoint: str,
    function_names: list[str],
    region: str,
) -> None:
    """Invoke each listed Lambda once to ensure warm containers are ready.

    Prints a summary to stderr, then invokes each function sequentially
    via a temporary boto3 Lambda client.  Hard-fails on any error.
    """
    if not function_names:
        return

    _logger.info("pre-warming %d function(s)", len(function_names))
    client: Any = boto3.client(
        "lambda",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=LOCALSTACK_ACCESS_KEY,
        aws_secret_access_key=LOCALSTACK_SECRET_KEY,
        config=Config(read_timeout=120, connect_timeout=120),
    )
    for func_name in function_names:
        try:
            response = client.invoke(
                FunctionName=func_name,
                InvocationType="RequestResponse",
                Payload=b"{}",
            )
        except Exception as exc:
            raise SamStartupError(
                port=0,
                log_tail=f"Pre-warm invoke failed for function '{func_name}': {exc}",
            ) from exc
        if response.get("FunctionError"):
            payload_bytes = response.get("Payload", b"")
            payload_text: str
            if hasattr(payload_bytes, "read"):
                payload_text = payload_bytes.read().decode(errors="replace")
            else:
                payload_text = str(payload_bytes)
            raise SamStartupError(
                port=0,
                log_tail=f"Pre-warm function '{func_name}' returned "
                f"FunctionError='{response['FunctionError']}': "
                f"{payload_text}",
            )


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
    warm_functions: list[str],
) -> Iterator[str]:
    """Start `sam local start-lambda` in Docker. Yields endpoint URL http://127.0.0.1:{lambda_port}.

    Under xdist: gw0 starts the container and writes the endpoint to shared state;
    gw1+ workers poll for the endpoint and yield it without any Docker calls.
    Logs written to {log_dir}/start-lambda.log.
    """

    @contextmanager
    def _on_controller() -> Iterator[tuple[str, str]]:
        with _run_sam_service(
            settings=samstack_settings,
            docker_network=docker_network,
            subcommand="start-lambda",
            port=samstack_settings.lambda_port,
            warm_containers=_warm_containers_mode(warm_functions),
            settings_extra_args=samstack_settings.start_lambda_args,
            fixture_extra_args=sam_lambda_extra_args,
            log_filename="start-lambda.log",
            wait_mode="port",
            network_alias="sam-lambda",
        ) as endpoint:
            _pre_warm_functions(endpoint, warm_functions, samstack_settings.region)
            # state_value == user_resource == the endpoint URL.
            yield endpoint, endpoint

    with xdist_shared_session(
        StateKeys.SAM_LAMBDA_ENDPOINT,
        on_controller=_on_controller,
        error_prefix="sam_lambda_endpoint container failed to start",
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

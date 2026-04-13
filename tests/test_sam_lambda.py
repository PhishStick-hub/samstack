"""sam local start-lambda: direct Lambda invocation via boto3."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_lambda import LambdaClient


def test_invoke_hello_world_returns_200(lambda_client: LambdaClient) -> None:
    result = lambda_client.invoke(
        FunctionName="HelloWorldFunction",
        Payload=b"{}",
    )
    assert result["StatusCode"] == 200


def test_invoke_hello_world_returns_message(lambda_client: LambdaClient) -> None:
    result = lambda_client.invoke(
        FunctionName="HelloWorldFunction",
        Payload=b"{}",
    )
    payload = json.loads(result["Payload"].read())
    body = json.loads(payload["body"])
    assert body["message"] == "hello"


def test_invoke_does_not_raise_function_error(lambda_client: LambdaClient) -> None:
    result = lambda_client.invoke(
        FunctionName="HelloWorldFunction",
        Payload=b"{}",
    )
    assert "FunctionError" not in result

"""Verify pre-warmed function stays warm across start-lambda invocations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_lambda import LambdaClient


def test_warm_across_invocations(lambda_client: LambdaClient) -> None:
    """Two consecutive invocations return the same instance_id (warm container)."""
    r1 = lambda_client.invoke(
        FunctionName="WarmCheckFunction",
        Payload=b"{}",
    )
    payload1 = json.loads(r1["Payload"].read())
    body1 = json.loads(payload1["body"])
    id1 = body1["instance_id"]

    r2 = lambda_client.invoke(
        FunctionName="WarmCheckFunction",
        Payload=b"{}",
    )
    payload2 = json.loads(r2["Payload"].read())
    body2 = json.loads(payload2["body"])
    id2 = body2["instance_id"]

    assert id1 == id2, f"Container was not warm: {id1} != {id2}"


def test_warm_function_returns_200(lambda_client: LambdaClient) -> None:
    """Pre-warmed function responds successfully."""
    result = lambda_client.invoke(
        FunctionName="WarmCheckFunction",
        Payload=b"{}",
    )
    assert result["StatusCode"] == 200
    assert "FunctionError" not in result

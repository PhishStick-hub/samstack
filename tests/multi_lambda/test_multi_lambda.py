"""End-to-end multi-Lambda tests with HTTP + invoke mocking.

Lambda A is the unit under test. Mock B is a ``samstack.mock`` spy exposed via
both API Gateway and direct invoke. Each scenario verifies:

1. Lambda A sends the expected request (method, path, body) to Mock B.
2. Lambda A consumes Mock B's response correctly (static default or queued override).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from mypy_boto3_lambda import LambdaClient

    from samstack.mock import LambdaMock

import requests


# --- HTTP path: Lambda A → API Gateway → Mock B ----------------------------


@pytest.mark.parametrize(
    "sub_path,method",
    [
        ("/orders/42", "POST"),
        ("/users/u1", "POST"),
    ],
)
def test_http_call_path_recorded(
    sam_api: str,
    mock_b: LambdaMock,
    sub_path: str,
    method: str,
) -> None:
    requests.post(
        f"{sam_api}/lambda-a/http",
        json={"path": sub_path, "method": method, "payload": {"x": 1}},
        timeout=15,
    )
    call = mock_b.calls.one
    assert call.method == method
    assert call.path == sub_path
    assert call.body == {"x": 1}


def test_http_default_response_consumed(sam_api: str, mock_b: LambdaMock) -> None:
    resp = requests.post(
        f"{sam_api}/lambda-a/http",
        json={"path": "/ping", "method": "POST", "payload": {}},
        timeout=15,
    )
    assert resp.status_code == 200
    # Mock B's default HTTP response body is ``{}`` → Lambda A returns that.
    assert resp.json() == {}


def test_http_response_override(sam_api: str, mock_b: LambdaMock) -> None:
    mock_b.next_response(
        {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"id": "abc", "total": 42}),
        }
    )
    resp = requests.post(
        f"{sam_api}/lambda-a/http",
        json={"path": "/orders", "method": "POST", "payload": {"qty": 3}},
        timeout=15,
    )
    assert resp.json() == {"id": "abc", "total": 42}
    assert mock_b.calls.one.body == {"qty": 3}


# --- Invoke path: Lambda A → boto3 client → Mock B -------------------------


def test_invoke_captures_payload(sam_api: str, mock_b: LambdaMock) -> None:
    requests.post(
        f"{sam_api}/lambda-a/invoke",
        json={"payload": {"order_id": "xyz"}},
        timeout=30,
    )
    call = mock_b.calls.one
    assert call.method == "INVOKE"
    assert call.path is None
    assert call.body == {"order_id": "xyz"}


def test_invoke_response_override(
    lambda_client: LambdaClient,
    mock_b: LambdaMock,
) -> None:
    mock_b.next_response({"result": "ok", "items": [1, 2, 3]})
    lambda_client.invoke(
        FunctionName="LambdaAFunction",
        Payload=json.dumps({"target": "b", "payload": {"q": "go"}}).encode(),
    )
    assert mock_b.calls.one.body == {"q": "go"}


def test_response_queue_ordered(
    lambda_client: LambdaClient,
    mock_b: LambdaMock,
) -> None:
    mock_b.response_queue(
        [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
        ]
    )
    for tag in ("a", "b", "c"):
        lambda_client.invoke(
            FunctionName="LambdaAFunction",
            Payload=json.dumps({"target": "b", "payload": {"tag": tag}}).encode(),
        )
    tags = [call.body["tag"] for call in mock_b.calls]
    assert tags == ["a", "b", "c"]


# --- Filter API ------------------------------------------------------------


def test_calls_matching_filter(sam_api: str, mock_b: LambdaMock) -> None:
    requests.post(
        f"{sam_api}/lambda-a/http",
        json={"path": "/orders", "method": "POST", "payload": {"total": 100}},
        timeout=15,
    )
    requests.post(
        f"{sam_api}/lambda-a/http",
        json={"path": "/health", "method": "GET", "payload": {}},
        timeout=15,
    )
    orders = mock_b.calls.matching(path="/orders", method="POST")
    assert orders.one.body == {"total": 100}

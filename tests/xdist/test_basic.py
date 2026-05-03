"""Basic xdist integration tests for samstack fixtures.

Validates that samstack fixtures (sam_api, lambda_client, s3_*)
work correctly under pytest-xdist with shared Docker infrastructure.
"""

from __future__ import annotations

import json
from uuid import uuid4

import requests
from mypy_boto3_lambda import LambdaClient
from mypy_boto3_s3 import S3Client

from samstack.resources.s3 import S3Bucket


def test_get_hello_from_sam_api(sam_api: str) -> None:
    """GET /hello returns 200 with hello message."""
    resp = requests.get(f"{sam_api}/hello", timeout=30)
    assert resp.status_code == 200
    assert resp.json() == {"message": "hello"}


def test_post_hello_writes_to_s3(
    sam_api: str,
    s3_client: S3Client,
    integration_bucket: str,
) -> None:
    """POST /hello writes body to the integration bucket; verify via S3 client."""
    payload = {"test_id": uuid4().hex[:8]}
    resp = requests.post(
        f"{sam_api}/hello",
        json=payload,
        timeout=30,
    )
    assert resp.status_code == 201
    response_data = resp.json()
    assert "key" in response_data

    key = response_data["key"]
    obj = s3_client.get_object(Bucket=integration_bucket, Key=key)
    stored = json.loads(obj["Body"].read().decode())
    assert stored == payload


def test_lambda_direct_invoke(lambda_client: LambdaClient) -> None:
    """lambda_client.invoke returns 200 for HelloWorldFunction.

    Direct invoke returns the full API Gateway response format;
    the body contains the JSON payload.
    """
    resp = lambda_client.invoke(
        FunctionName="HelloWorldFunction",
        Payload=b"{}",
    )
    assert resp["StatusCode"] == 200
    payload = json.loads(resp["Payload"].read().decode())
    body = json.loads(payload["body"])
    assert body == {"message": "hello"}


def test_xdist_shared_localstack(s3_bucket: S3Bucket) -> None:
    """Under -n 2, LocalStack is accessible from all workers.

    Each worker creates a uniquely named object and reads it back.
    """
    key = f"shared-test-{uuid4().hex[:8]}.json"
    data = {"worker_data": uuid4().hex[:8]}

    s3_bucket.put(key, data)
    result = s3_bucket.get_json(key)

    assert result == data

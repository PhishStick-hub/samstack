"""Lambda interacts with LocalStack S3 via shared Docker network."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def test_post_hello_writes_to_s3(
    sam_api: str,
    s3_client: S3Client,
    integration_bucket: str,
) -> None:
    payload = {"item": "book", "qty": 1}
    response = requests.post(
        f"{sam_api}/hello",
        json=payload,
        timeout=15,
    )
    assert response.status_code == 201

    body = response.json()
    key = body["key"]
    assert key.startswith("uploads/")

    obj = s3_client.get_object(Bucket=integration_bucket, Key=key)
    stored = json.loads(obj["Body"].read())
    assert stored["item"] == "book"


def test_post_hello_returns_key(sam_api: str, integration_bucket: str) -> None:
    response = requests.post(f"{sam_api}/hello", json={"x": 1}, timeout=15)
    assert response.status_code == 201
    assert "key" in response.json()

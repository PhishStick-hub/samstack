"""Inlined copy of ``samstack.mock.spy_handler`` for the integration fixture.

A real user project would instead install ``samstack`` into the mock Lambda
and write::

    from samstack.mock import spy_handler as handler

The fixture inlines the logic so ``sam build`` does not need to pull the
library from PyPI during the repo's own integration tests.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError


_DEFAULT_HTTP_RESPONSE: dict[str, Any] = {
    "statusCode": 200,
    "headers": {"content-type": "application/json"},
    "body": "{}",
}
_DEFAULT_INVOKE_RESPONSE: dict[str, Any] = {}

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("AWS_ENDPOINT_URL_S3") or None,
        )
    return _s3


def _is_http_event(event: dict[str, Any]) -> bool:
    return "httpMethod" in event or "requestContext" in event


def _parse_body(event: dict[str, Any]) -> Any:
    body = event.get("body")
    if body is None:
        return None
    headers = event.get("headers") or {}
    content_type = ""
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == "content-type":
            content_type = str(value).lower()
            break
    if "json" in content_type:
        try:
            return json.loads(body)
        except (json.JSONDecodeError, TypeError, ValueError):
            return body
    return body


def _normalize(event: dict[str, Any]) -> dict[str, Any]:
    if _is_http_event(event):
        return {
            "method": event.get("httpMethod") or "",
            "path": event.get("path"),
            "headers": dict(event.get("headers") or {}),
            "query": dict(event.get("queryStringParameters") or {}),
            "body": _parse_body(event),
            "raw_event": event,
        }
    return {
        "method": "INVOKE",
        "path": None,
        "headers": {},
        "query": {},
        "body": event,
        "raw_event": event,
    }


def _spy_key(name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"spy/{name}/{stamp}-{uuid4().hex[:8]}.json"


def _queue_key(name: str) -> str:
    return f"mock-responses/{name}/queue.json"


def handler(event: dict[str, Any], _context: Any) -> Any:
    bucket = os.environ.get("MOCK_SPY_BUCKET")
    name = os.environ.get("MOCK_FUNCTION_NAME")
    if not bucket or not name:
        raise RuntimeError(
            "mock handler: MOCK_SPY_BUCKET and MOCK_FUNCTION_NAME must be set"
        )
    client = _client()

    call = _normalize(event)
    client.put_object(
        Bucket=bucket,
        Key=_spy_key(name),
        Body=json.dumps(call, default=str).encode(),
    )

    key = _queue_key(name)
    queued: dict[str, Any] | None = None
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
        try:
            queue = json.loads(obj["Body"].read())
        except (json.JSONDecodeError, ValueError):
            queue = None
        if isinstance(queue, list) and queue and isinstance(queue[0], dict):
            queued = queue[0]
            rest = queue[1:]
            if rest:
                client.put_object(
                    Bucket=bucket, Key=key, Body=json.dumps(rest).encode()
                )
            else:
                client.delete_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code not in ("NoSuchKey", "404"):
            raise

    if queued is not None:
        return queued
    return _DEFAULT_HTTP_RESPONSE if _is_http_event(event) else _DEFAULT_INVOKE_RESPONSE

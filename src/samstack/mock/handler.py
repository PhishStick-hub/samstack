"""Spy handler for use as a mock Lambda function inside SAM integration tests.

This module is intended to run **inside** a Lambda container — it depends only
on the Python standard library and boto3 (which is pre-installed in the AWS
Lambda runtime). It must not import any other samstack module.

Usage: place a two-line handler next to a mock's test config::

    # tests/mocks/mock_b/handler.py
    from samstack.mock import spy_handler as handler

Environment variables (set by ``make_lambda_mock``):

- ``MOCK_SPY_BUCKET``    — S3 bucket name where captured events land.
- ``MOCK_FUNCTION_NAME`` — short alias used in S3 prefixes (one per mock).
- ``AWS_ENDPOINT_URL_S3`` — picked up automatically by boto3.

Keys written:

- Calls:    ``spy/<name>/<iso-timestamp>-<uuid>.json``  (one object per call, lex-sorted = chrono)
- Queue:    ``mock-responses/<name>/queue.json``       (JSON list of canned responses)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


_DEFAULT_HTTP_RESPONSE: dict[str, Any] = {
    "statusCode": 200,
    "headers": {"content-type": "application/json"},
    "body": "{}",
}
_DEFAULT_INVOKE_RESPONSE: dict[str, Any] = {}

_s3: S3Client | None = None


def _client() -> S3Client:
    """Return a cached boto3 S3 client. Safe to reuse across warm invocations."""
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("AWS_ENDPOINT_URL_S3") or None,
        )
    return _s3


def _is_http_event(event: dict[str, Any]) -> bool:
    """Detect API Gateway Lambda-proxy events."""
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
    """Convert a raw Lambda event into a structured Call-shaped dict."""
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
    # UTC ISO-8601 with microseconds + uuid → lex sort == chronological order.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"spy/{name}/{stamp}-{uuid4().hex[:8]}.json"


def _queue_key(name: str) -> str:
    return f"mock-responses/{name}/queue.json"


def _capture(client: S3Client, bucket: str, name: str, event: dict[str, Any]) -> None:
    call = _normalize(event)
    payload = json.dumps(call, default=str).encode()
    client.put_object(Bucket=bucket, Key=_spy_key(name), Body=payload)


def _pop_response(client: S3Client, bucket: str, name: str) -> dict[str, Any] | None:
    """Pop the head of the response queue, return it; return None when empty/missing."""
    key = _queue_key(name)
    try:
        obj = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            return None
        raise
    try:
        queue = json.loads(obj["Body"].read())
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(queue, list) or not queue:
        return None
    head = queue[0]
    if not isinstance(head, dict):
        return None
    rest = queue[1:]
    if rest:
        client.put_object(Bucket=bucket, Key=key, Body=json.dumps(rest).encode())
    else:
        client.delete_object(Bucket=bucket, Key=key)
    return head


def spy_handler(event: dict[str, Any], _context: Any) -> Any:
    """AWS Lambda handler that records every call and returns a queued or default response.

    Behavior:
    1. Write the incoming event (normalized) to ``s3://{MOCK_SPY_BUCKET}/spy/{MOCK_FUNCTION_NAME}/``.
    2. If a response queue exists at ``mock-responses/{MOCK_FUNCTION_NAME}/queue.json``,
       pop its head and return it.
    3. Otherwise return a default (HTTP 200 empty JSON for API events, ``{}`` for invokes).
    """
    bucket = os.environ.get("MOCK_SPY_BUCKET")
    name = os.environ.get("MOCK_FUNCTION_NAME")
    if not bucket or not name:
        raise RuntimeError(
            "samstack mock handler: MOCK_SPY_BUCKET and MOCK_FUNCTION_NAME must be set."
        )
    client = _client()
    _capture(client, bucket, name, event)
    queued = _pop_response(client, bucket, name)
    if queued is not None:
        return queued
    default = (
        _DEFAULT_HTTP_RESPONSE if _is_http_event(event) else _DEFAULT_INVOKE_RESPONSE
    )
    return dict(default)

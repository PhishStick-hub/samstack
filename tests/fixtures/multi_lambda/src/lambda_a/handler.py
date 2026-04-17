"""Lambda A: forwards requests to Lambda B over HTTP and via boto3 invoke.

Routes (API Gateway):
- POST /lambda-a/http   → HTTP POST to ``LAMBDA_B_URL`` + return the upstream JSON body
- POST /lambda-a/invoke → boto3 invoke of ``MockBFunction`` + return its payload
- POST /lambda-a/self   → self-invoke via boto3 (hits the SAM lambda endpoint for
  ``LambdaAFunction``, routed by ``AWS_ENDPOINT_URL_LAMBDA``)

Direct invoke (non-HTTP): treats payload ``{"target": "b"}`` as invoke-Mock-B,
``{"target": "self"}`` as self-invoke; anything else returns ``{"ok": true}``.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import request as urlrequest

import boto3


def _http_to_b(body: dict[str, Any]) -> dict[str, Any]:
    base = os.environ["LAMBDA_B_URL"]
    path = body.get("path", "/")
    url = f"{base}{path}"
    payload = json.dumps(body.get("payload", {})).encode()
    req = urlrequest.Request(
        url,
        data=payload,
        method=body.get("method", "POST"),
        headers={"content-type": "application/json"},
    )
    with urlrequest.urlopen(req, timeout=10) as resp:
        raw = resp.read()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"raw": raw.decode(errors="replace")}


def _invoke_b(payload: dict[str, Any]) -> dict[str, Any]:
    client = boto3.client("lambda")
    resp = client.invoke(
        FunctionName="MockBFunction",
        Payload=json.dumps(payload).encode(),
    )
    raw = resp["Payload"].read()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"raw": raw.decode(errors="replace")}


def _invoke_self(payload: dict[str, Any]) -> dict[str, Any]:
    client = boto3.client("lambda")
    resp = client.invoke(
        FunctionName="LambdaAFunction",
        Payload=json.dumps(payload).encode(),
    )
    raw = resp["Payload"].read()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"raw": raw.decode(errors="replace")}


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def handler(event: dict[str, Any], _context: Any) -> Any:
    if "httpMethod" in event:
        path = event.get("path", "")
        body = _parse_body(event)
        if path.endswith("/http"):
            upstream = _http_to_b(body)
        elif path.endswith("/invoke"):
            upstream = _invoke_b(body)
        elif path.endswith("/self"):
            upstream = _invoke_self({"target": "noop"})
        else:
            upstream = {"error": "unknown path", "path": path}
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(upstream),
        }

    target = event.get("target")
    if target == "b":
        return _invoke_b(event.get("payload", {}))
    if target == "self":
        return {"self": True}
    return {"ok": True, "echo": event}

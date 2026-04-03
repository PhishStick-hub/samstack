"""
Hello World Lambda handler for samstack integration tests.

GET  /hello            → 200 {"message": "hello"}
POST /hello            → writes body to S3 bucket TEST_BUCKET → 201 {"key": "<uuid>"}
Direct invoke (no http) → 200 {"message": "hello"}
"""

from __future__ import annotations

import json
import os
from uuid import uuid4

import boto3


def handler(event: dict, context: object) -> dict:
    http_method = event.get("httpMethod") or event.get("requestContext", {}).get(
        "http", {}
    ).get("method")

    if http_method == "POST":
        bucket = os.environ["TEST_BUCKET"]
        key = f"uploads/{uuid4().hex}.json"
        body = event.get("body", "{}")
        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("AWS_ENDPOINT_URL"),
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        )
        s3.put_object(Bucket=bucket, Key=key, Body=body.encode())
        return {
            "statusCode": 201,
            "body": json.dumps({"key": key}),
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "hello"}),
    }

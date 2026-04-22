from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class S3Bucket:
    """Thin wrapper around an S3 bucket for use in pytest fixtures."""

    def __init__(self, name: str, client: S3Client) -> None:
        self._name = name
        self._client = client

    @property
    def name(self) -> str:
        return self._name

    @property
    def client(self) -> S3Client:
        return self._client

    def put(self, key: str, data: bytes | str | dict[str, Any]) -> None:
        """Upload an object. Dicts are JSON-serialized; strings are UTF-8 encoded."""
        if isinstance(data, dict):
            body: bytes = json.dumps(data).encode()
        elif isinstance(data, str):
            body = data.encode()
        else:
            body = data
        self._client.put_object(Bucket=self._name, Key=key, Body=body)

    def get(self, key: str) -> bytes:
        """Download an object and return raw bytes."""
        resp = self._client.get_object(Bucket=self._name, Key=key)
        return resp["Body"].read()

    def get_json(self, key: str) -> Any:
        """Download an object and deserialize as JSON."""
        return json.loads(self.get(key))

    def delete(self, key: str) -> None:
        """Delete an object."""
        self._client.delete_object(Bucket=self._name, Key=key)

    def list_keys(self, prefix: str = "") -> list[str]:
        """List object keys, optionally filtered by prefix. Paginates through all pages."""
        paginator = self._client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._name, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

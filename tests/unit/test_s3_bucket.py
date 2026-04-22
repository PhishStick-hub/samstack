from __future__ import annotations

import json
from unittest.mock import MagicMock, create_autospec

import pytest
from mypy_boto3_s3 import S3Client

from samstack.resources.s3 import S3Bucket


@pytest.fixture
def mock_client() -> (
    MagicMock
):  # autospec of S3Client; typed as MagicMock for ty compatibility
    return create_autospec(S3Client, instance=True)


@pytest.fixture
def bucket(mock_client: MagicMock) -> S3Bucket:
    return S3Bucket(name="test-bucket", client=mock_client)


class TestS3BucketPut:
    def test_put_bytes_passthrough(
        self, bucket: S3Bucket, mock_client: MagicMock
    ) -> None:
        bucket.put("key", b"raw bytes")
        mock_client.put_object.assert_called_once_with(  # type: ignore[attr-defined]
            Bucket="test-bucket", Key="key", Body=b"raw bytes"
        )

    def test_put_str_encodes_utf8(
        self, bucket: S3Bucket, mock_client: MagicMock
    ) -> None:
        bucket.put("key", "hello")
        mock_client.put_object.assert_called_once_with(  # type: ignore[attr-defined]
            Bucket="test-bucket", Key="key", Body=b"hello"
        )

    def test_put_dict_serializes_to_json(
        self, bucket: S3Bucket, mock_client: MagicMock
    ) -> None:
        bucket.put("key.json", {"foo": "bar"})
        mock_client.put_object.assert_called_once_with(  # type: ignore[attr-defined]
            Bucket="test-bucket",
            Key="key.json",
            Body=json.dumps({"foo": "bar"}).encode(),
        )


class TestS3BucketGet:
    def test_get_returns_bytes(self, bucket: S3Bucket, mock_client: MagicMock) -> None:
        body_mock = MagicMock()
        body_mock.read.return_value = b"content"
        mock_client.get_object.return_value = {"Body": body_mock}  # type: ignore[attr-defined]

        result = bucket.get("key")

        assert result == b"content"
        mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="key")  # type: ignore[attr-defined]

    def test_get_json_deserializes(
        self, bucket: S3Bucket, mock_client: MagicMock
    ) -> None:
        body_mock = MagicMock()
        body_mock.read.return_value = json.dumps({"x": 1}).encode()
        mock_client.get_object.return_value = {"Body": body_mock}  # type: ignore[attr-defined]

        result = bucket.get_json("key.json")

        assert result == {"x": 1}


class TestS3BucketDelete:
    def test_delete_calls_delete_object(
        self, bucket: S3Bucket, mock_client: MagicMock
    ) -> None:
        bucket.delete("key")
        mock_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="key"
        )  # type: ignore[attr-defined]


def _install_paginator(mock_client: MagicMock, pages: list[dict]) -> MagicMock:
    """Wire mock_client.get_paginator('list_objects_v2').paginate(...) to yield pages."""
    paginator = MagicMock()
    paginator.paginate.return_value = iter(pages)
    mock_client.get_paginator.return_value = paginator  # type: ignore[attr-defined]
    return paginator


class TestS3BucketList:
    def test_list_keys_empty_bucket_returns_empty(
        self, bucket: S3Bucket, mock_client: MagicMock
    ) -> None:
        _install_paginator(mock_client, [{}])

        result = bucket.list_keys()

        assert result == []

    def test_list_keys_returns_keys(
        self, bucket: S3Bucket, mock_client: MagicMock
    ) -> None:
        _install_paginator(
            mock_client, [{"Contents": [{"Key": "a.txt"}, {"Key": "b.txt"}]}]
        )

        result = bucket.list_keys()

        assert result == ["a.txt", "b.txt"]

    def test_list_keys_with_prefix(
        self, bucket: S3Bucket, mock_client: MagicMock
    ) -> None:
        paginator = _install_paginator(
            mock_client, [{"Contents": [{"Key": "uploads/x.json"}]}]
        )

        result = bucket.list_keys(prefix="uploads/")

        mock_client.get_paginator.assert_called_once_with("list_objects_v2")  # type: ignore[attr-defined]
        paginator.paginate.assert_called_once_with(
            Bucket="test-bucket", Prefix="uploads/"
        )
        assert result == ["uploads/x.json"]

    def test_list_keys_paginates_across_multiple_pages(
        self, bucket: S3Bucket, mock_client: MagicMock
    ) -> None:
        """Regression: list_objects_v2 caps at 1000 keys. list_keys must walk all pages."""
        _install_paginator(
            mock_client,
            [
                {"Contents": [{"Key": f"k{i}"} for i in range(1000)]},
                {"Contents": [{"Key": "k1000"}, {"Key": "k1001"}]},
            ],
        )

        result = bucket.list_keys()

        assert len(result) == 1002
        assert result[-1] == "k1001"


class TestS3BucketProperties:
    def test_name_property(self, bucket: S3Bucket, mock_client: MagicMock) -> None:
        assert bucket.name == "test-bucket"

    def test_client_property(self, bucket: S3Bucket, mock_client: MagicMock) -> None:
        assert bucket.client is mock_client

"""Integration tests for S3 resource fixtures against real LocalStack."""

from __future__ import annotations

from collections.abc import Callable


from samstack.resources.s3 import S3Bucket


class TestMakeS3Bucket:
    def test_creates_real_bucket(
        self, make_s3_bucket: Callable[[str], S3Bucket]
    ) -> None:
        bucket = make_s3_bucket("my-data")
        bucket.put("probe.txt", b"ok")
        assert bucket.get("probe.txt") == b"ok"

    def test_uuid_isolation(
        self, make_s3_bucket: Callable[[str], S3Bucket]
    ) -> None:
        b1 = make_s3_bucket("shared")
        b2 = make_s3_bucket("shared")
        assert b1.name != b2.name

    def test_put_get_json_roundtrip(
        self, make_s3_bucket: Callable[[str], S3Bucket]
    ) -> None:
        bucket = make_s3_bucket("json-data")
        bucket.put("record.json", {"hello": "world", "count": 42})
        assert bucket.get_json("record.json") == {"hello": "world", "count": 42}

    def test_list_and_delete(
        self, make_s3_bucket: Callable[[str], S3Bucket]
    ) -> None:
        bucket = make_s3_bucket("list-test")
        bucket.put("a.txt", b"a")
        bucket.put("b.txt", b"b")
        assert set(bucket.list_keys()) == {"a.txt", "b.txt"}
        bucket.delete("a.txt")
        assert bucket.list_keys() == ["b.txt"]

    def test_list_with_prefix(
        self, make_s3_bucket: Callable[[str], S3Bucket]
    ) -> None:
        bucket = make_s3_bucket("prefix-test")
        bucket.put("uploads/x.json", b"x")
        bucket.put("other/y.txt", b"y")
        assert bucket.list_keys(prefix="uploads/") == ["uploads/x.json"]


class TestS3BucketFunctionScoped:
    def test_bucket_put_get_bytes(self, s3_bucket: S3Bucket) -> None:
        s3_bucket.put("key", b"data")
        assert s3_bucket.get("key") == b"data"

    def test_bucket_put_str(self, s3_bucket: S3Bucket) -> None:
        s3_bucket.put("key.txt", "hello world")
        assert s3_bucket.get("key.txt") == b"hello world"

    def test_bucket_list_empty(self, s3_bucket: S3Bucket) -> None:
        assert s3_bucket.list_keys() == []

    def test_client_escape_hatch(self, s3_bucket: S3Bucket) -> None:
        response = s3_bucket.client.list_buckets()
        bucket_names = [b["Name"] for b in response["Buckets"]]
        assert s3_bucket.name in bucket_names

"""Unit tests for INFRA-04: resource fixture per-worker isolation via UUID naming.

Verifies that all 8 resource fixtures (4 function-scoped + 4 session-scoped
factories) produce unique names per call, ensuring xdist workers cannot collide
when sharing a single LocalStack instance.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

import samstack.fixtures.resources as res

UUID8_PATTERN = re.compile(r"-[0-9a-f]{8}$")


def _mock_aws(monkeypatch: pytest.MonkeyPatch, service: str) -> MagicMock:
    """Set up mocks with dynamic return values so each call gets a unique name."""
    client = MagicMock()
    if service == "dynamodb":
        client.create_table = MagicMock()
        client.delete_table = MagicMock()
        monkeypatch.setattr(
            res,
            "_create_dynamo_table",
            lambda client, resource, name, keys: _make_dynamo_mock(name),
        )
    elif service == "sqs":
        client.create_queue = MagicMock(
            side_effect=lambda QueueName, **kw: {
                "QueueUrl": f"http://localstack:4566/queue/{QueueName}"
            }
        )
        client.delete_queue = MagicMock()
    elif service == "sns":
        client.create_topic = MagicMock(
            side_effect=lambda Name, **kw: {
                "TopicArn": f"arn:aws:sns:us-east-1:000000000000:{Name}"
            }
        )
        client.delete_topic = MagicMock()
    else:  # s3
        client.create_bucket = MagicMock()
        client.delete_bucket = MagicMock()

    return client


def _make_dynamo_mock(name: str) -> MagicMock:
    """Return a MagicMock with a real string .name attribute."""
    m = MagicMock()
    m.name = name
    return m


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------


def test_s3_bucket_names_are_unique(monkeypatch):
    """Function-scoped s3_bucket produces a new UUID name each call."""
    client = _mock_aws(monkeypatch, "s3")
    _raw = getattr(res.s3_bucket, "__wrapped__")

    g1 = _raw(client)
    n1 = next(g1).name
    g1.close()

    g2 = _raw(client)
    n2 = next(g2).name
    g2.close()

    assert n1 != n2
    assert n1.startswith("test-")
    assert UUID8_PATTERN.search(n1)


def test_make_s3_bucket_names_are_unique(monkeypatch):
    """Session-scoped make_s3_bucket factory produces unique names per call."""
    client = _mock_aws(monkeypatch, "s3")
    _raw = getattr(res.make_s3_bucket, "__wrapped__")

    g = _raw(client)
    factory = next(g)

    b1 = factory("my-data")
    b2 = factory("my-data")

    assert b1.name != b2.name
    assert b1.name.startswith("my-data-")
    assert UUID8_PATTERN.search(b1.name)

    g.close()


# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------


def test_dynamodb_table_names_are_unique(monkeypatch):
    """Function-scoped dynamodb_table produces a new UUID name each call."""
    client = _mock_aws(monkeypatch, "dynamodb")
    # _create_dynamo_table is already patched by _mock_aws
    fake_resource = MagicMock()
    fake_resource.Table = MagicMock()
    _raw = getattr(res.dynamodb_table, "__wrapped__")

    g1 = _raw(client, fake_resource)
    t1 = next(g1)
    g1.close()

    g2 = _raw(client, fake_resource)
    t2 = next(g2)
    g2.close()

    assert t1.name != t2.name
    assert t1.name.startswith("test-")
    assert UUID8_PATTERN.search(t1.name)


def test_make_dynamodb_table_names_are_unique(monkeypatch):
    """Session-scoped make_dynamodb_table factory produces unique names per call."""
    client = _mock_aws(monkeypatch, "dynamodb")
    fake_resource = MagicMock()
    fake_resource.Table = MagicMock()
    _raw = getattr(res.make_dynamodb_table, "__wrapped__")

    g = _raw(client, fake_resource)
    factory = next(g)

    t1 = factory("orders", {"id": "S"})
    t2 = factory("orders", {"id": "S"})

    assert t1.name != t2.name
    assert t1.name.startswith("orders-")
    assert UUID8_PATTERN.search(t1.name)

    g.close()


# ---------------------------------------------------------------------------
# SQS
# ---------------------------------------------------------------------------


def test_sqs_queue_names_are_unique(monkeypatch):
    """Function-scoped sqs_queue produces a new UUID name each call."""
    client = _mock_aws(monkeypatch, "sqs")
    _raw = getattr(res.sqs_queue, "__wrapped__")

    g1 = _raw(client)
    q1 = next(g1)
    g1.close()

    g2 = _raw(client)
    q2 = next(g2)
    g2.close()

    assert q1.url != q2.url
    assert "test-" in q1.url


def test_make_sqs_queue_names_are_unique(monkeypatch):
    """Session-scoped make_sqs_queue factory produces unique names per call."""
    client = _mock_aws(monkeypatch, "sqs")
    _raw = getattr(res.make_sqs_queue, "__wrapped__")

    g = _raw(client)
    factory = next(g)

    q1 = factory("jobs")
    q2 = factory("jobs")

    assert q1.url != q2.url
    assert "jobs-" in q1.url

    g.close()


# ---------------------------------------------------------------------------
# SNS
# ---------------------------------------------------------------------------


def test_sns_topic_names_are_unique(monkeypatch):
    """Function-scoped sns_topic produces a new UUID name each call."""
    client = _mock_aws(monkeypatch, "sns")
    _raw = getattr(res.sns_topic, "__wrapped__")

    g1 = _raw(client)
    t1 = next(g1)
    g1.close()

    g2 = _raw(client)
    t2 = next(g2)
    g2.close()

    assert t1.arn != t2.arn
    assert "test-" in t1.arn


def test_make_sns_topic_names_are_unique(monkeypatch):
    """Session-scoped make_sns_topic factory produces unique names per call."""
    client = _mock_aws(monkeypatch, "sns")
    _raw = getattr(res.make_sns_topic, "__wrapped__")

    g = _raw(client)
    factory = next(g)

    t1 = factory("notifications")
    t2 = factory("notifications")

    assert t1.arn != t2.arn
    assert "notifications-" in t1.arn

    g.close()


# ---------------------------------------------------------------------------
# Cross-resource + UUID format
# ---------------------------------------------------------------------------


def test_cross_service_names_are_unique(monkeypatch):
    """No cross-resource naming collision (different type prefixes + UUID randomness)."""
    s3_client = _mock_aws(monkeypatch, "s3")
    sqs_client = _mock_aws(monkeypatch, "sqs")

    s3g = getattr(res.s3_bucket, "__wrapped__")(s3_client)
    s3 = next(s3g)
    s3g.close()

    sqsg = getattr(res.sqs_queue, "__wrapped__")(sqs_client)
    sqs = next(sqsg)
    sqsg.close()

    names = {s3.name, sqs.url}
    assert len(names) == 2


def test_uuid_suffix_is_8_hex_chars(monkeypatch):
    """Verify UUID suffix is exactly 8 lowercase hex characters."""
    client = _mock_aws(monkeypatch, "s3")
    _raw = getattr(res.s3_bucket, "__wrapped__")
    g = _raw(client)
    bucket = next(g)

    suffix = bucket.name.rsplit("-", 1)[-1]
    assert len(suffix) == 8
    assert all(c in "0123456789abcdef" for c in suffix)

    g.close()

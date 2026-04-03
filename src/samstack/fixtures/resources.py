"""
LocalStack resource fixtures for testing AWS services.

Provides session-scoped boto3 clients, session-scoped factory fixtures,
and function-scoped convenience fixtures for S3, DynamoDB, SQS, and SNS.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING
from uuid import uuid4

import boto3
import pytest

from samstack._constants import LOCALSTACK_ACCESS_KEY, LOCALSTACK_SECRET_KEY
from samstack.resources.dynamodb import DynamoTable
from samstack.resources.s3 import S3Bucket
from samstack.resources.sns import SnsTopic
from samstack.resources.sqs import SqsQueue
from samstack.settings import SamStackSettings


@contextmanager
def _safe_cleanup(description: str) -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        warnings.warn(
            f"samstack: failed to clean up {description}: {exc}",
            stacklevel=1,
        )


if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_dynamodb.service_resource import DynamoDBServiceResource, Table
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_sns import SNSClient
    from mypy_boto3_sqs import SQSClient


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def s3_client(
    localstack_endpoint: str,
    samstack_settings: SamStackSettings,
) -> S3Client:
    """Session-scoped boto3 S3 client pointed at LocalStack."""
    return boto3.client(
        "s3",
        endpoint_url=localstack_endpoint,
        region_name=samstack_settings.region,
        aws_access_key_id=LOCALSTACK_ACCESS_KEY,
        aws_secret_access_key=LOCALSTACK_SECRET_KEY,
    )


@pytest.fixture(scope="session")
def s3_bucket_factory(
    s3_client: S3Client,
) -> Iterator[Callable[[str], S3Bucket]]:
    """
    Session-scoped factory that creates S3Bucket instances.

    Each call creates a uniquely named bucket. All buckets are deleted
    at end of session.

    Usage::

        def test_something(s3_bucket_factory):
            bucket = s3_bucket_factory("my-data")
            bucket.put("key.json", {"value": 1})
    """
    created: list[S3Bucket] = []

    def _create(name: str) -> S3Bucket:
        actual = f"{name}-{uuid4().hex[:8]}"
        s3_client.create_bucket(Bucket=actual)
        bucket = S3Bucket(name=actual, client=s3_client)
        created.append(bucket)
        return bucket

    yield _create

    for bucket in created:
        with _safe_cleanup(f"S3 bucket '{bucket.name}'"):
            for key in bucket.list_keys():
                bucket.delete(key)
            s3_client.delete_bucket(Bucket=bucket.name)


@pytest.fixture
def s3_bucket(s3_client: S3Client) -> Iterator[S3Bucket]:
    """
    Function-scoped S3Bucket fixture. Fresh bucket per test, deleted after.

    Usage::

        def test_upload(s3_bucket):
            s3_bucket.put("file.txt", b"hello")
            assert s3_bucket.get("file.txt") == b"hello"
    """
    name = f"test-{uuid4().hex[:8]}"
    s3_client.create_bucket(Bucket=name)
    bucket = S3Bucket(name=name, client=s3_client)
    yield bucket
    with _safe_cleanup(f"S3 bucket '{name}'"):
        for key in bucket.list_keys():
            bucket.delete(key)
        s3_client.delete_bucket(Bucket=name)


# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def dynamodb_client(
    localstack_endpoint: str,
    samstack_settings: SamStackSettings,
) -> DynamoDBClient:
    """Session-scoped boto3 DynamoDB low-level client pointed at LocalStack."""
    return boto3.client(
        "dynamodb",
        endpoint_url=localstack_endpoint,
        region_name=samstack_settings.region,
        aws_access_key_id=LOCALSTACK_ACCESS_KEY,
        aws_secret_access_key=LOCALSTACK_SECRET_KEY,
    )


@pytest.fixture(scope="session")
def _dynamodb_resource(
    localstack_endpoint: str,
    samstack_settings: SamStackSettings,
) -> DynamoDBServiceResource:
    """Session-scoped boto3 DynamoDB resource (high-level) for table wrappers."""
    return boto3.resource(
        "dynamodb",
        endpoint_url=localstack_endpoint,
        region_name=samstack_settings.region,
        aws_access_key_id=LOCALSTACK_ACCESS_KEY,
        aws_secret_access_key=LOCALSTACK_SECRET_KEY,
    )


def _create_dynamo_table(
    dynamodb_client: DynamoDBClient,
    resource: DynamoDBServiceResource,
    name: str,
    keys: dict[str, str],
) -> DynamoTable:
    key_pairs = list(keys.items())
    attr_defs = [{"AttributeName": k, "AttributeType": v} for k, v in key_pairs]
    key_schema = [{"AttributeName": key_pairs[0][0], "KeyType": "HASH"}]
    if len(key_pairs) > 1:
        key_schema.append({"AttributeName": key_pairs[1][0], "KeyType": "RANGE"})
    dynamodb_client.create_table(
        TableName=name,
        AttributeDefinitions=attr_defs,
        KeySchema=key_schema,
        BillingMode="PAY_PER_REQUEST",
    )
    table: Table = resource.Table(name)
    return DynamoTable(name=name, table=table)


@pytest.fixture(scope="session")
def dynamodb_table_factory(
    dynamodb_client: DynamoDBClient,
    _dynamodb_resource: DynamoDBServiceResource,
) -> Iterator[Callable[[str, dict[str, str]], DynamoTable]]:
    """
    Session-scoped factory that creates DynamoTable instances.

    Each call creates a uniquely named table. All tables are deleted at end of session.
    Uses the high-level resource API so item values are plain Python types.

    Args:
        name: Base name for the table (UUID suffix appended).
        keys: Mapping of attribute name to type (``"S"``, ``"N"``, or ``"B"``).
              First entry is the HASH key; second (if present) is the RANGE key.

    Usage::

        def test_something(dynamodb_table_factory):
            table = dynamodb_table_factory("orders", {"order_id": "S"})
            table.put_item({"order_id": "1", "total": 99})
    """
    created: list[str] = []

    def _create(name: str, keys: dict[str, str]) -> DynamoTable:
        actual = f"{name}-{uuid4().hex[:8]}"
        table = _create_dynamo_table(dynamodb_client, _dynamodb_resource, actual, keys)
        created.append(actual)
        return table

    yield _create

    for table_name in created:
        with _safe_cleanup(f"DynamoDB table '{table_name}'"):
            dynamodb_client.delete_table(TableName=table_name)


@pytest.fixture
def dynamodb_table(
    dynamodb_client: DynamoDBClient,
    _dynamodb_resource: DynamoDBServiceResource,
) -> Iterator[DynamoTable]:
    """
    Function-scoped DynamoTable fixture. Default key schema: ``{"id": "S"}``.
    Fresh table per test, deleted after.

    Usage::

        def test_store(dynamodb_table):
            dynamodb_table.put_item({"id": "1", "data": "x"})
            assert dynamodb_table.get_item({"id": "1"})["data"] == "x"
    """
    name = f"test-{uuid4().hex[:8]}"
    table = _create_dynamo_table(dynamodb_client, _dynamodb_resource, name, {"id": "S"})
    yield table
    with _safe_cleanup(f"DynamoDB table '{name}'"):
        dynamodb_client.delete_table(TableName=name)


# ---------------------------------------------------------------------------
# SQS
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sqs_client(
    localstack_endpoint: str,
    samstack_settings: SamStackSettings,
) -> SQSClient:
    """Session-scoped boto3 SQS client pointed at LocalStack."""
    return boto3.client(
        "sqs",
        endpoint_url=localstack_endpoint,
        region_name=samstack_settings.region,
        aws_access_key_id=LOCALSTACK_ACCESS_KEY,
        aws_secret_access_key=LOCALSTACK_SECRET_KEY,
    )


@pytest.fixture(scope="session")
def sqs_queue_factory(
    sqs_client: SQSClient,
) -> Iterator[Callable[[str], SqsQueue]]:
    """
    Session-scoped factory that creates SqsQueue instances.

    Each call creates a uniquely named queue. All queues are deleted at end of session.

    Usage::

        def test_something(sqs_queue_factory):
            queue = sqs_queue_factory("jobs")
            queue.send({"task": "process", "id": 1})
    """
    created: list[SqsQueue] = []

    def _create(name: str) -> SqsQueue:
        actual = f"{name}-{uuid4().hex[:8]}"
        resp = sqs_client.create_queue(QueueName=actual)
        queue = SqsQueue(url=resp["QueueUrl"], client=sqs_client)
        created.append(queue)
        return queue

    yield _create

    for queue in created:
        with _safe_cleanup(f"SQS queue '{queue.url}'"):
            sqs_client.delete_queue(QueueUrl=queue.url)


@pytest.fixture
def sqs_queue(sqs_client: SQSClient) -> Iterator[SqsQueue]:
    """
    Function-scoped SqsQueue fixture. Fresh queue per test, deleted after.

    Usage::

        def test_process(sqs_queue):
            sqs_queue.send({"job": "run"})
            messages = sqs_queue.receive()
            assert len(messages) == 1
    """
    name = f"test-{uuid4().hex[:8]}"
    resp = sqs_client.create_queue(QueueName=name)
    queue = SqsQueue(url=resp["QueueUrl"], client=sqs_client)
    yield queue
    with _safe_cleanup(f"SQS queue '{name}'"):
        sqs_client.delete_queue(QueueUrl=queue.url)


# ---------------------------------------------------------------------------
# SNS
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sns_client(
    localstack_endpoint: str,
    samstack_settings: SamStackSettings,
) -> SNSClient:
    """Session-scoped boto3 SNS client pointed at LocalStack."""
    return boto3.client(
        "sns",
        endpoint_url=localstack_endpoint,
        region_name=samstack_settings.region,
        aws_access_key_id=LOCALSTACK_ACCESS_KEY,
        aws_secret_access_key=LOCALSTACK_SECRET_KEY,
    )


@pytest.fixture(scope="session")
def sns_topic_factory(
    sns_client: SNSClient,
) -> Iterator[Callable[[str], SnsTopic]]:
    """
    Session-scoped factory that creates SnsTopic instances.

    Each call creates a uniquely named topic. All topics are deleted at end of session.

    Usage::

        def test_something(sns_topic_factory, sqs_queue_factory):
            topic = sns_topic_factory("notifications")
            queue = sqs_queue_factory("inbox")
            topic.subscribe_sqs(queue_arn)
            topic.publish({"event": "created"})
    """
    created: list[SnsTopic] = []

    def _create(name: str) -> SnsTopic:
        actual = f"{name}-{uuid4().hex[:8]}"
        resp = sns_client.create_topic(Name=actual)
        topic = SnsTopic(arn=resp["TopicArn"], client=sns_client)
        created.append(topic)
        return topic

    yield _create

    for topic in created:
        with _safe_cleanup(f"SNS topic '{topic.arn}'"):
            sns_client.delete_topic(TopicArn=topic.arn)


@pytest.fixture
def sns_topic(sns_client: SNSClient) -> Iterator[SnsTopic]:
    """
    Function-scoped SnsTopic fixture. Fresh topic per test, deleted after.

    Usage::

        def test_notify(sns_topic):
            msg_id = sns_topic.publish("hello")
            assert isinstance(msg_id, str)
    """
    name = f"test-{uuid4().hex[:8]}"
    resp = sns_client.create_topic(Name=name)
    topic = SnsTopic(arn=resp["TopicArn"], client=sns_client)
    yield topic
    with _safe_cleanup(f"SNS topic '{name}'"):
        sns_client.delete_topic(TopicArn=topic.arn)

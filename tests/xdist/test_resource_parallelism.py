"""Resource parallelism tests under pytest-xdist (TEST-03).

Verifies all four AWS resource types (S3, DynamoDB, SQS, SNS) work
simultaneously from multiple xdist workers without cross-worker interference.
Each test uses UUID-based naming to ensure per-worker uniqueness.
"""

from __future__ import annotations

import json
import time
from uuid import uuid4

from mypy_boto3_sqs import SQSClient

from samstack.resources.dynamodb import DynamoTable
from samstack.resources.s3 import S3Bucket
from samstack.resources.sns import SnsTopic
from samstack.resources.sqs import SqsQueue


def test_s3_concurrent_read_write(s3_bucket: S3Bucket) -> None:
    """Each worker creates a uniquely named object and reads it back."""
    key = f"parallel-test-{uuid4().hex[:8]}.json"
    data = {"worker_data": uuid4().hex[:8]}
    s3_bucket.put(key, data)
    result = s3_bucket.get_json(key)
    assert result == data


def test_dynamodb_concurrent_read_write(dynamodb_table: DynamoTable) -> None:
    """Each worker inserts a unique item and reads it back."""
    item = {"id": f"worker-{uuid4().hex[:8]}", "name": "parallel-test"}
    dynamodb_table.put_item(item)
    result = dynamodb_table.get_item({"id": item["id"]})
    assert result is not None
    assert result["name"] == "parallel-test"


def test_sqs_concurrent_send_receive(sqs_queue: SqsQueue) -> None:
    """Each worker sends a unique message and receives it back."""
    msg_id = f"msg-{uuid4().hex[:8]}"
    sqs_queue.send({"message_id": msg_id})
    messages = sqs_queue.receive(max=1, wait=10)
    assert len(messages) == 1
    body = json.loads(messages[0]["Body"])
    assert body["message_id"] == msg_id


def test_sns_concurrent_publish(
    sns_topic: SnsTopic,
    sqs_queue: SqsQueue,
    sqs_client: SQSClient,
) -> None:
    """Each worker publishes to SNS and receives via subscribed SQS queue."""
    # Get queue ARN (SqsQueue wrapper has no .arn property)
    resp = sqs_client.get_queue_attributes(
        QueueUrl=sqs_queue.url,
        AttributeNames=["QueueArn"],
    )
    queue_arn = resp["Attributes"]["QueueArn"]

    sns_topic.subscribe_sqs(queue_arn)
    time.sleep(0.5)  # SNS→SQS propagation on LocalStack needs brief wait

    msg_id = f"sns-{uuid4().hex[:8]}"
    sns_topic.publish({"sns_message_id": msg_id})
    time.sleep(0.5)  # allow delivery

    messages = sqs_queue.receive(max=1, wait=10)
    assert len(messages) >= 1

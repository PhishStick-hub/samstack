"""Integration tests for SQS resource fixtures against real LocalStack."""

from __future__ import annotations

import json
from collections.abc import Callable


from samstack.resources.sqs import SqsQueue


class TestMakeSqsQueue:
    def test_creates_real_queue(
        self, make_sqs_queue: Callable[[str], SqsQueue]
    ) -> None:
        queue = make_sqs_queue("jobs")
        msg_id = queue.send("hello")
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0

    def test_uuid_isolation(self, make_sqs_queue: Callable[[str], SqsQueue]) -> None:
        q1 = make_sqs_queue("events")
        q2 = make_sqs_queue("events")
        assert q1.url != q2.url

    def test_send_receive_str(self, make_sqs_queue: Callable[[str], SqsQueue]) -> None:
        queue = make_sqs_queue("str-test")
        queue.send("ping")
        messages = queue.receive(max_messages=1, wait_seconds=1)
        assert len(messages) == 1
        assert messages[0]["Body"] == "ping"

    def test_send_receive_dict(self, make_sqs_queue: Callable[[str], SqsQueue]) -> None:
        queue = make_sqs_queue("dict-test")
        payload = {"action": "create", "id": 42}
        queue.send(payload)
        messages = queue.receive(max_messages=1, wait_seconds=1)
        assert len(messages) == 1
        assert json.loads(messages[0]["Body"]) == payload

    def test_purge(self, make_sqs_queue: Callable[[str], SqsQueue]) -> None:
        queue = make_sqs_queue("purge-test")
        queue.send("msg1")
        queue.send("msg2")
        queue.purge()
        messages = queue.receive(max_messages=10, wait_seconds=1)
        assert messages == []


class TestSqsQueueFunctionScoped:
    def test_send_receive_roundtrip(self, sqs_queue: SqsQueue) -> None:
        sqs_queue.send("test message")
        messages = sqs_queue.receive(max_messages=1, wait_seconds=1)
        assert len(messages) == 1
        assert messages[0]["Body"] == "test message"

    def test_receive_empty_returns_empty_list(self, sqs_queue: SqsQueue) -> None:
        result = sqs_queue.receive(max_messages=1, wait_seconds=1)
        assert result == []

    def test_client_escape_hatch(self, sqs_queue: SqsQueue) -> None:
        response = sqs_queue.client.get_queue_attributes(
            QueueUrl=sqs_queue.url,
            AttributeNames=["QueueArn"],
        )
        assert "QueueArn" in response["Attributes"]

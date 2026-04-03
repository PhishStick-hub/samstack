from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, create_autospec

import pytest
from mypy_boto3_sqs import SQSClient

from samstack.resources.sqs import SqsQueue


@pytest.fixture
def mock_client() -> (
    MagicMock
):  # autospec of SQSClient; typed as MagicMock for ty compatibility
    return create_autospec(SQSClient, instance=True)


@pytest.fixture
def queue(mock_client: MagicMock) -> SqsQueue:
    return SqsQueue(
        url="https://sqs.us-east-1.amazonaws.com/000000000000/test-queue",
        client=mock_client,
    )


class TestSqsQueueSend:
    def test_send_str_body(self, queue: SqsQueue, mock_client: MagicMock) -> None:
        mock_client.send_message.return_value = {"MessageId": "msg-1"}

        result = queue.send("hello")

        assert result == "msg-1"
        mock_client.send_message.assert_called_once_with(
            QueueUrl=queue.url, MessageBody="hello"
        )

    def test_send_dict_serializes_to_json(
        self, queue: SqsQueue, mock_client: MagicMock
    ) -> None:
        mock_client.send_message.return_value = {"MessageId": "msg-2"}
        payload: dict[str, Any] = {"action": "process", "id": 42}

        result = queue.send(payload)

        assert result == "msg-2"
        mock_client.send_message.assert_called_once_with(
            QueueUrl=queue.url, MessageBody=json.dumps(payload)
        )

    def test_send_forwards_kwargs(
        self, queue: SqsQueue, mock_client: MagicMock
    ) -> None:
        mock_client.send_message.return_value = {"MessageId": "msg-3"}

        queue.send("msg", DelaySeconds=10)

        mock_client.send_message.assert_called_once_with(
            QueueUrl=queue.url, MessageBody="msg", DelaySeconds=10
        )


class TestSqsQueueReceive:
    def test_receive_returns_messages(
        self, queue: SqsQueue, mock_client: MagicMock
    ) -> None:
        messages: list[dict[str, Any]] = [{"MessageId": "m1", "Body": "hi"}]
        mock_client.receive_message.return_value = {"Messages": messages}

        result = queue.receive(max_messages=5, wait_seconds=2)

        assert result == messages
        mock_client.receive_message.assert_called_once_with(
            QueueUrl=queue.url,
            MaxNumberOfMessages=5,
            WaitTimeSeconds=2,
        )

    def test_receive_empty_queue_returns_empty_list(
        self, queue: SqsQueue, mock_client: MagicMock
    ) -> None:
        mock_client.receive_message.return_value = {}

        result = queue.receive()

        assert result == []


class TestSqsQueuePurge:
    def test_purge_calls_client(self, queue: SqsQueue, mock_client: MagicMock) -> None:
        queue.purge()
        mock_client.purge_queue.assert_called_once_with(QueueUrl=queue.url)


class TestSqsQueueProperties:
    def test_url_property(self, queue: SqsQueue) -> None:
        assert (
            queue.url == "https://sqs.us-east-1.amazonaws.com/000000000000/test-queue"
        )

    def test_client_property(self, queue: SqsQueue, mock_client: MagicMock) -> None:
        assert queue.client is mock_client

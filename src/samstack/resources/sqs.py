from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient
    from mypy_boto3_sqs.type_defs import MessageTypeDef


class SqsQueue:
    """Thin wrapper around an SQS queue for use in pytest fixtures."""

    def __init__(self, url: str, client: SQSClient) -> None:
        self._url = url
        self._client = client

    @property
    def url(self) -> str:
        return self._url

    @property
    def client(self) -> SQSClient:
        return self._client

    def send(self, body: str | dict[str, Any], **kwargs: Any) -> str:
        """
        Send a message. Dicts are JSON-serialized. Returns the message ID.
        Extra kwargs (e.g. ``DelaySeconds``) are forwarded to boto3.
        """
        message_body = json.dumps(body) if isinstance(body, dict) else body
        resp = self._client.send_message(
            QueueUrl=self._url, MessageBody=message_body, **kwargs
        )
        return resp["MessageId"]

    def receive(
        self, max_messages: int = 1, wait_seconds: int = 0
    ) -> list[MessageTypeDef]:
        """
        Receive messages from the queue.

        Returns a list of message dicts (``MessageId``, ``Body``,
        ``ReceiptHandle``, etc). Returns an empty list when the queue is empty.
        """
        resp = self._client.receive_message(
            QueueUrl=self._url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
        )
        return resp.get("Messages", [])

    def purge(self) -> None:
        """Delete all messages from the queue."""
        self._client.purge_queue(QueueUrl=self._url)

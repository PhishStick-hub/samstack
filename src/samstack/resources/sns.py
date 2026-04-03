from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mypy_boto3_sns import SNSClient


class SnsTopic:
    """Thin wrapper around an SNS topic for use in pytest fixtures."""

    def __init__(self, arn: str, client: SNSClient) -> None:
        self._arn = arn
        self._client = client

    @property
    def arn(self) -> str:
        return self._arn

    @property
    def client(self) -> SNSClient:
        return self._client

    def publish(
        self,
        message: str | dict[str, Any],
        subject: str | None = None,
    ) -> str:
        """
        Publish a message to the topic. Dicts are JSON-serialized.
        Returns the message ID.
        """
        body = json.dumps(message) if isinstance(message, dict) else message
        kwargs: dict[str, Any] = {"TopicArn": self._arn, "Message": body}
        if subject is not None:
            kwargs["Subject"] = subject
        resp = self._client.publish(**kwargs)
        return resp["MessageId"]

    def subscribe_sqs(self, queue_arn: str) -> str:
        """
        Subscribe an SQS queue to this topic.

        Args:
            queue_arn: The ARN of the SQS queue to receive messages.

        Returns:
            The subscription ARN.
        """
        resp = self._client.subscribe(
            TopicArn=self._arn,
            Protocol="sqs",
            Endpoint=queue_arn,
        )
        return resp["SubscriptionArn"]

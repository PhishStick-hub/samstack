from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, create_autospec

import pytest
from mypy_boto3_sns import SNSClient

from samstack.resources.sns import SnsTopic


@pytest.fixture
def mock_client() -> (
    MagicMock
):  # autospec of SNSClient; typed as MagicMock for ty compatibility
    return create_autospec(SNSClient, instance=True)


@pytest.fixture
def topic(mock_client: MagicMock) -> SnsTopic:
    return SnsTopic(
        arn="arn:aws:sns:us-east-1:000000000000:test-topic", client=mock_client
    )


class TestSnsTopicPublish:
    def test_publish_str_message(self, topic: SnsTopic, mock_client: MagicMock) -> None:
        mock_client.publish.return_value = {"MessageId": "msg-1"}

        result = topic.publish("hello")

        assert result == "msg-1"
        mock_client.publish.assert_called_once_with(TopicArn=topic.arn, Message="hello")

    def test_publish_dict_serializes_to_json(
        self, topic: SnsTopic, mock_client: MagicMock
    ) -> None:
        mock_client.publish.return_value = {"MessageId": "msg-2"}
        payload: dict[str, Any] = {"event": "user.created", "id": 7}

        result = topic.publish(payload)

        assert result == "msg-2"
        mock_client.publish.assert_called_once_with(
            TopicArn=topic.arn, Message=json.dumps(payload)
        )

    def test_publish_with_subject(
        self, topic: SnsTopic, mock_client: MagicMock
    ) -> None:
        mock_client.publish.return_value = {"MessageId": "msg-3"}

        topic.publish("alert", subject="Urgent")

        mock_client.publish.assert_called_once_with(
            TopicArn=topic.arn, Message="alert", Subject="Urgent"
        )

    def test_publish_without_subject_omits_kwarg(
        self, topic: SnsTopic, mock_client: MagicMock
    ) -> None:
        mock_client.publish.return_value = {"MessageId": "msg-4"}

        topic.publish("msg")

        call_kwargs = mock_client.publish.call_args.kwargs
        assert "Subject" not in call_kwargs


class TestSnsTopicSubscribeSqs:
    def test_subscribe_sqs_returns_arn(
        self, topic: SnsTopic, mock_client: MagicMock
    ) -> None:
        sub_arn = "arn:aws:sns:us-east-1:000000000000:test-topic:sub-1"
        mock_client.subscribe.return_value = {"SubscriptionArn": sub_arn}

        result = topic.subscribe_sqs("arn:aws:sqs:us-east-1:000000000000:my-queue")

        assert result == sub_arn
        mock_client.subscribe.assert_called_once_with(
            TopicArn=topic.arn,
            Protocol="sqs",
            Endpoint="arn:aws:sqs:us-east-1:000000000000:my-queue",
        )


class TestSnsTopicProperties:
    def test_arn_property(self, topic: SnsTopic) -> None:
        assert topic.arn == "arn:aws:sns:us-east-1:000000000000:test-topic"

    def test_client_property(self, topic: SnsTopic, mock_client: MagicMock) -> None:
        assert topic.client is mock_client

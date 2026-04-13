"""Integration tests for SNS resource fixtures against real LocalStack."""

from __future__ import annotations

import json
from collections.abc import Callable


from samstack.resources.sns import SnsTopic
from samstack.resources.sqs import SqsQueue


class TestMakeSnsTopic:
    def test_creates_real_topic(
        self, make_sns_topic: Callable[[str], SnsTopic]
    ) -> None:
        topic = make_sns_topic("notifications")
        msg_id = topic.publish("hello")
        assert isinstance(msg_id, str)
        assert len(msg_id) > 0

    def test_uuid_isolation(self, make_sns_topic: Callable[[str], SnsTopic]) -> None:
        t1 = make_sns_topic("alerts")
        t2 = make_sns_topic("alerts")
        assert t1.arn != t2.arn

    def test_publish_dict(self, make_sns_topic: Callable[[str], SnsTopic]) -> None:
        topic = make_sns_topic("dict-events")
        payload = {"event": "user.created", "id": 42}
        msg_id = topic.publish(payload)
        assert isinstance(msg_id, str)

    def test_publish_with_subject(
        self, make_sns_topic: Callable[[str], SnsTopic]
    ) -> None:
        topic = make_sns_topic("subjects")
        msg_id = topic.publish("critical alert", subject="Urgent")
        assert isinstance(msg_id, str)

    def test_subscribe_sqs_and_receive(
        self,
        make_sns_topic: Callable[[str], SnsTopic],
        make_sqs_queue: Callable[[str], SqsQueue],
    ) -> None:
        topic = make_sns_topic("fanout")
        queue = make_sqs_queue("fanout-inbox")

        queue_attrs = queue.client.get_queue_attributes(
            QueueUrl=queue.url, AttributeNames=["QueueArn"]
        )
        queue_arn = queue_attrs["Attributes"]["QueueArn"]

        sub_arn = topic.subscribe_sqs(queue_arn)
        assert sub_arn.startswith("arn:aws:sns:")

        topic.publish("from-sns")
        messages = queue.receive(max_messages=1, wait_seconds=5)
        assert len(messages) == 1
        body = json.loads(messages[0]["Body"])
        assert body["Message"] == "from-sns"


class TestSnsTopicFunctionScoped:
    def test_publish_returns_message_id(self, sns_topic: SnsTopic) -> None:
        msg_id = sns_topic.publish("test")
        assert isinstance(msg_id, str)

    def test_client_escape_hatch(self, sns_topic: SnsTopic) -> None:
        response = sns_topic.client.list_topics()
        arns = [t["TopicArn"] for t in response["Topics"]]
        assert sns_topic.arn in arns

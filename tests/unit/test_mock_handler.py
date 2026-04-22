from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from samstack.mock import handler as mh


@pytest.fixture(autouse=True)
def _reset_module_client() -> None:
    mh._s3 = None


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_SPY_BUCKET", "test-bucket")
    monkeypatch.setenv("MOCK_FUNCTION_NAME", "mock-b")


@pytest.fixture
def s3_stub(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    stub = MagicMock(spec=S3Client)
    stub.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject"
    )

    def _fake_boto3_client(*_args: Any, **_kwargs: Any) -> MagicMock:
        return stub

    monkeypatch.setattr(mh.boto3, "client", _fake_boto3_client)
    return stub


class TestNormalize:
    def test_http_event_extracts_fields(self) -> None:
        event: dict[str, Any] = {
            "httpMethod": "POST",
            "path": "/orders/42",
            "headers": {"content-type": "application/json"},
            "queryStringParameters": {"foo": "bar"},
            "body": '{"qty": 3}',
        }
        call = mh._normalize(event)
        assert call["method"] == "POST"
        assert call["path"] == "/orders/42"
        assert call["query"] == {"foo": "bar"}
        assert call["body"] == {"qty": 3}

    def test_invoke_event(self) -> None:
        call = mh._normalize({"action": "run", "id": 5})
        assert call["method"] == "INVOKE"
        assert call["path"] is None
        assert call["body"] == {"action": "run", "id": 5}

    def test_http_event_non_json_body(self) -> None:
        call = mh._normalize(
            {
                "httpMethod": "POST",
                "path": "/x",
                "headers": {"content-type": "text/plain"},
                "body": "raw text",
            }
        )
        assert call["body"] == "raw text"

    def test_http_event_missing_body(self) -> None:
        call = mh._normalize({"httpMethod": "GET", "path": "/x"})
        assert call["body"] is None


class TestSpyHandler:
    def test_captures_call_and_returns_default_http(
        self, env: None, s3_stub: MagicMock
    ) -> None:
        result = mh.spy_handler(
            {"httpMethod": "GET", "path": "/x", "headers": {}}, None
        )
        s3_stub.put_object.assert_called_once()
        assert result["statusCode"] == 200

    def test_returns_default_invoke_response(
        self, env: None, s3_stub: MagicMock
    ) -> None:
        result = mh.spy_handler({"direct": True}, None)
        assert result == {}

    def test_pops_queued_response(
        self,
        env: None,
        s3_stub: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        queue_body = MagicMock()
        queue_body.read.return_value = json.dumps(
            [{"statusCode": 201, "body": "{}"}, {"statusCode": 202, "body": "{}"}]
        ).encode()
        s3_stub.get_object.side_effect = None
        s3_stub.get_object.return_value = {"Body": queue_body}

        result = mh.spy_handler({"httpMethod": "POST", "path": "/x"}, None)
        assert result["statusCode"] == 201

        # Remaining queue written back.
        put_calls = s3_stub.put_object.call_args_list
        assert any("queue.json" in str(c.kwargs.get("Key", "")) for c in put_calls)

    def test_pops_last_response_deletes_queue(
        self, env: None, s3_stub: MagicMock
    ) -> None:
        queue_body = MagicMock()
        queue_body.read.return_value = json.dumps(
            [{"statusCode": 418, "body": "{}"}]
        ).encode()
        s3_stub.get_object.side_effect = None
        s3_stub.get_object.return_value = {"Body": queue_body}

        result = mh.spy_handler({"httpMethod": "POST", "path": "/x"}, None)
        assert result["statusCode"] == 418
        s3_stub.delete_object.assert_called()

    def test_missing_env_raises(self, s3_stub: MagicMock) -> None:
        with pytest.raises(RuntimeError):
            mh.spy_handler({}, None)

    def test_default_response_is_fresh_copy(
        self, env: None, s3_stub: MagicMock
    ) -> None:
        """Regression: default HTTP response must not be the module-level dict.

        Warm Lambda reuses the process; mutating the returned dict must not
        pollute the next invocation.
        """
        first = mh.spy_handler({"httpMethod": "GET", "path": "/x"}, None)
        first["statusCode"] = 500
        first["_extra"] = "tampered"
        second = mh.spy_handler({"httpMethod": "GET", "path": "/x"}, None)
        assert second["statusCode"] == 200
        assert "_extra" not in second
        assert first is not second

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import boto3 as boto3_mod
import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from samstack.mock import handler as mh

_INLINE_PATH = (
    Path(__file__).parent.parent.parent
    / "tests"
    / "fixtures"
    / "multi_lambda"
    / "tests"
    / "mocks"
    / "mock_b"
    / "handler.py"
)


def _load_inline_handler() -> Any:
    spec = importlib.util.spec_from_file_location(
        "_inline_spy_handler", str(_INLINE_PATH)
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load inline handler from {_INLINE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_inline_spy_handler"] = mod
    spec.loader.exec_module(mod)
    return mod


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


class TestInlineParity:
    """Ensure mock_b's inlined spy_handler matches the real implementation."""

    @pytest.fixture(autouse=True)
    def _shared_setup(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        mh._s3 = None
        monkeypatch.setenv("MOCK_SPY_BUCKET", "test-bucket")
        monkeypatch.setenv("MOCK_FUNCTION_NAME", "mock-b")

        stub = MagicMock(spec=S3Client)
        stub.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject"
        )

        def _fake_client(*_args: Any, **_kwargs: Any) -> MagicMock:
            return stub

        monkeypatch.setattr(boto3_mod, "client", _fake_client)
        self.stub = stub
        self.inline = _load_inline_handler()
        self.inline._s3 = None
        return stub

    def test_http_default_response_matches(self) -> None:
        event: dict[str, Any] = {"httpMethod": "GET", "path": "/x", "headers": {}}
        result_real = mh.spy_handler(dict(event), None)
        self.stub.reset_mock()
        mh._s3 = None
        result_inline = self.inline.handler(dict(event), None)
        assert result_real == result_inline

    def test_invoke_default_response_matches(self) -> None:
        event: dict[str, Any] = {"action": "run", "id": 5}
        result_real = mh.spy_handler(dict(event), None)
        self.stub.reset_mock()
        mh._s3 = None
        result_inline = self.inline.handler(dict(event), None)
        assert result_real == result_inline

    def test_both_capture_to_s3(self) -> None:
        event: dict[str, Any] = {"httpMethod": "POST", "path": "/o", "body": "x"}
        mh.spy_handler(dict(event), None)
        real_calls = [
            c.kwargs.get("Key", "") for c in self.stub.put_object.call_args_list
        ]
        self.stub.reset_mock()
        self.inline._s3 = None
        self.inline.handler(dict(event), None)
        inline_calls = [
            c.kwargs.get("Key", "") for c in self.stub.put_object.call_args_list
        ]
        real_has_spy = any("spy/" in k for k in real_calls)
        inline_has_spy = any("spy/" in k for k in inline_calls)
        assert real_has_spy and inline_has_spy

    def test_both_return_fresh_copy(self) -> None:
        event: dict[str, Any] = {"httpMethod": "GET", "path": "/x", "headers": {}}
        first = mh.spy_handler(dict(event), None)
        first["statusCode"] = 500
        first["_tampered"] = True
        second = mh.spy_handler(dict(event), None)
        assert second["statusCode"] == 200
        assert "_tampered" not in second

        self.inline._s3 = None
        first_i = self.inline.handler(dict(event), None)
        first_i["statusCode"] = 500
        first_i["_tampered"] = True
        second_i = self.inline.handler(dict(event), None)
        assert second_i["statusCode"] == 200
        assert "_tampered" not in second_i

    def test_both_raise_on_missing_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MOCK_SPY_BUCKET", raising=False)
        monkeypatch.delenv("MOCK_FUNCTION_NAME", raising=False)
        with pytest.raises(RuntimeError):
            mh.spy_handler({}, None)
        with pytest.raises(RuntimeError):
            self.inline.handler({}, None)

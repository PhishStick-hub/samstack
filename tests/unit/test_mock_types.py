from __future__ import annotations

from typing import Any

import pytest

from samstack.mock.types import Call, CallList


def _call(
    method: str = "POST",
    path: str | None = "/orders",
    body: Any = None,
    headers: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
) -> Call:
    return Call(
        method=method,
        path=path,
        headers=dict(headers or {}),
        query=dict(query or {}),
        body=body,
        raw_event={},
    )


class TestCallFromDict:
    def test_round_trip_defaults(self) -> None:
        call = Call.from_dict({"method": "GET", "path": "/x"})
        assert call.method == "GET"
        assert call.path == "/x"
        assert call.headers == {}
        assert call.query == {}
        assert call.body is None
        assert call.raw_event == {}

    def test_full_payload(self) -> None:
        call = Call.from_dict(
            {
                "method": "POST",
                "path": "/orders",
                "headers": {"content-type": "application/json"},
                "query": {"q": "1"},
                "body": {"total": 10},
                "raw_event": {"httpMethod": "POST"},
            }
        )
        assert call.headers == {"content-type": "application/json"}
        assert call.query == {"q": "1"}
        assert call.body == {"total": 10}
        assert call.raw_event == {"httpMethod": "POST"}

    def test_none_collections_coerced_to_empty(self) -> None:
        call = Call.from_dict({"method": "X", "path": None, "headers": None})
        assert call.headers == {}


class TestCallList:
    def test_len_and_index(self) -> None:
        calls = CallList([_call(path="/a"), _call(path="/b")])
        assert len(calls) == 2
        assert calls[0].path == "/a"
        assert calls[1].path == "/b"

    def test_one_asserts_single(self) -> None:
        one = CallList([_call(path="/only")]).one
        assert one.path == "/only"

    def test_one_raises_when_zero(self) -> None:
        with pytest.raises(AssertionError):
            _ = CallList([]).one

    def test_one_raises_when_many(self) -> None:
        with pytest.raises(AssertionError):
            _ = CallList([_call(), _call()]).one

    def test_last_returns_final(self) -> None:
        last = CallList([_call(path="/a"), _call(path="/b")]).last
        assert last.path == "/b"

    def test_last_raises_when_empty(self) -> None:
        with pytest.raises(AssertionError):
            _ = CallList([]).last

    def test_matching_filters_by_equality(self) -> None:
        calls = CallList(
            [
                _call(method="POST", path="/orders"),
                _call(method="GET", path="/health"),
                _call(method="POST", path="/orders"),
            ]
        )
        posts = calls.matching(path="/orders", method="POST")
        assert len(posts) == 2

    def test_matching_returns_empty_when_no_match(self) -> None:
        calls = CallList([_call(method="GET")])
        assert len(calls.matching(method="PUT")) == 0

    def test_iteration(self) -> None:
        seq = [_call(path="/a"), _call(path="/b")]
        assert [c.path for c in CallList(seq)] == ["/a", "/b"]

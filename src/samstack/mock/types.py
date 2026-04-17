"""Public types for mock Lambda call capture."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Call:
    """One captured invocation of a mock Lambda.

    Attributes:
        method: HTTP verb (``"GET"``, ``"POST"``, ...) for API Gateway events,
            or ``"INVOKE"`` for direct boto3 Lambda invokes.
        path: Request path (e.g. ``"/orders/42"``) for HTTP events, or
            ``None`` for direct invokes.
        headers: HTTP request headers (empty for invokes).
        query: Parsed query-string parameters (empty for invokes).
        body: Parsed JSON body for HTTP events with ``content-type: application/json``;
            raw string when body is non-JSON; parsed JSON payload for direct invokes.
        raw_event: The full, unmodified Lambda event dictionary as received.
    """

    method: str
    path: str | None
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    body: Any = None
    raw_event: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Call:
        """Reconstruct a Call from its serialized JSON form."""
        return cls(
            method=data.get("method", ""),
            path=data.get("path"),
            headers=dict(data.get("headers") or {}),
            query=dict(data.get("query") or {}),
            body=data.get("body"),
            raw_event=dict(data.get("raw_event") or {}),
        )


class CallList(Sequence[Call]):
    """An ordered, immutable collection of captured Calls with assertion helpers.

    Returned by :pyattr:`LambdaMock.calls`. Behaves like a regular sequence
    (supports ``len()``, indexing, iteration, slicing). The helper properties
    make common assertions more readable than ``calls[0]`` / ``calls[-1]``.

    Usage::

        assert mock_b.calls.one.path == "/orders"
        assert mock_b.calls.last.method == "POST"
        posts = mock_b.calls.matching(method="POST")
        assert posts.one.body["total"] == 100
    """

    def __init__(self, calls: Sequence[Call]) -> None:
        self._calls: tuple[Call, ...] = tuple(calls)

    def __len__(self) -> int:
        return len(self._calls)

    def __iter__(self) -> Iterator[Call]:
        return iter(self._calls)

    def __getitem__(self, index: int | slice) -> Any:
        return self._calls[index]

    def __repr__(self) -> str:
        return f"CallList({list(self._calls)!r})"

    @property
    def one(self) -> Call:
        """Assert exactly one call was captured and return it.

        Raises:
            AssertionError: If the number of captured calls is not exactly 1.
        """
        if len(self._calls) != 1:
            raise AssertionError(
                f"Expected exactly 1 call, got {len(self._calls)}: {list(self._calls)!r}"
            )
        return self._calls[0]

    @property
    def last(self) -> Call:
        """Return the most recent call.

        Raises:
            AssertionError: If no calls were captured.
        """
        if not self._calls:
            raise AssertionError("Expected at least 1 call, got 0")
        return self._calls[-1]

    def matching(self, **filters: Any) -> CallList:
        """Return a new CallList containing only calls whose attributes equal the filters.

        Example::

            calls.matching(method="POST", path="/orders")
        """
        filtered = [
            call
            for call in self._calls
            if all(getattr(call, key, None) == value for key, value in filters.items())
        ]
        return CallList(filtered)

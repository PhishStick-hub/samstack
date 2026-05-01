"""LambdaMock wrapper and ``make_lambda_mock`` factory fixture."""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

import pytest

from samstack._xdist import (
    get_worker_id,
    is_controller,
    wait_for_state_key,
    write_state_file,
)
from samstack.mock.types import Call, CallList
from samstack.resources.s3 import S3Bucket

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class LambdaMock:
    """Handle on a mock Lambda: inspect received calls and queue canned responses.

    Instances are produced by the :func:`make_lambda_mock` fixture. Each mock
    gets its own S3 prefix (``spy/<alias>/`` for calls, ``mock-responses/<alias>/``
    for responses) so multiple mocks can share one spy bucket safely.
    """

    SPY_PREFIX = "spy"
    RESPONSE_PREFIX = "mock-responses"

    def __init__(self, name: str, bucket: S3Bucket) -> None:
        self._name = name
        self._bucket = bucket

    @property
    def name(self) -> str:
        """Short alias of the mock (used in S3 key prefixes and env vars)."""
        return self._name

    @property
    def bucket(self) -> S3Bucket:
        """Underlying spy S3 bucket wrapper."""
        return self._bucket

    @property
    def calls(self) -> CallList:
        """Return all captured calls in chronological order."""
        keys = sorted(self._bucket.list_keys(prefix=f"{self.SPY_PREFIX}/{self._name}/"))
        calls: list[Call] = []
        for key in keys:
            try:
                data = self._bucket.get_json(key)
            except Exception as exc:  # pragma: no cover - defensive
                warnings.warn(
                    f"samstack: failed to read spy object '{key}': {exc}",
                    stacklevel=2,
                )
                continue
            if isinstance(data, dict):
                calls.append(Call.from_dict(data))
        return CallList(calls)

    def clear(self) -> None:
        """Remove all previously captured calls and any queued responses."""
        for key in self._bucket.list_keys(prefix=f"{self.SPY_PREFIX}/{self._name}/"):
            self._bucket.delete(key)
        for key in self._bucket.list_keys(
            prefix=f"{self.RESPONSE_PREFIX}/{self._name}/"
        ):
            self._bucket.delete(key)

    def next_response(self, response: dict[str, Any]) -> None:
        """Queue a single response — returned by the next invocation only."""
        self.response_queue([response])

    def response_queue(self, responses: list[dict[str, Any]]) -> None:
        """Queue multiple responses, consumed head-first across successive calls."""
        key = f"{self.RESPONSE_PREFIX}/{self._name}/queue.json"
        self._bucket.put(key, json.dumps(responses).encode())


@pytest.fixture(scope="session")
def make_lambda_mock(
    make_s3_bucket: Callable[[str], S3Bucket],
    s3_client: "S3Client",
    sam_env_vars: dict[str, dict[str, str]],
) -> Iterator[Callable[..., LambdaMock]]:
    """Session-scoped factory that wires up a mock Lambda.

    For each mock, creates a dedicated spy bucket (or reuses a shared one) and
    injects ``MOCK_SPY_BUCKET`` / ``MOCK_FUNCTION_NAME`` / ``AWS_ENDPOINT_URL_S3``
    env vars into the target function's ``sam_env_vars`` entry. Must be invoked
    **before** ``sam_build`` runs (which happens when ``sam_api`` /
    ``sam_lambda_endpoint`` are first resolved).

    Args:
        function_name: The logical Resources key from the SAM template (e.g.
            ``"MockBFunction"``).
        alias: Short identifier used for S3 prefixes. Must be unique per-session
            when sharing a bucket.
        bucket: Optional pre-existing ``S3Bucket`` to reuse across mocks. When
            omitted, a fresh bucket named ``mock-<alias>-<uuid>`` is created.

    Usage::

        @pytest.fixture(scope="session")
        def _mock_b_session(make_lambda_mock):
            return make_lambda_mock("MockBFunction", alias="mock-b")

        @pytest.fixture
        def mock_b(_mock_b_session):
            _mock_b_session.clear()
            yield _mock_b_session
    """
    created: list[LambdaMock] = []

    def _make(
        function_name: str,
        *,
        alias: str,
        bucket: S3Bucket | None = None,
    ) -> LambdaMock:
        # D-06: If user provides a pre-existing bucket, skip all xdist logic
        if bucket is not None:
            spy_bucket = bucket
        else:
            worker_id = get_worker_id()
            if not is_controller(worker_id):
                # gw1+ path (D-01, D-03): wait for gw0 to create shared spy bucket
                shared_bucket_name = wait_for_state_key(
                    f"mock_spy_bucket_{alias}", timeout=120
                )
                spy_bucket = S3Bucket(name=shared_bucket_name, client=s3_client)
            else:
                # gw0 / master path (D-01): create spy bucket + write name to state
                try:
                    spy_bucket = make_s3_bucket(f"mock-{alias}")
                except Exception as exc:
                    if worker_id == "gw0":
                        write_state_file(
                            "error",
                            f"mock spy bucket 'mock-{alias}' creation failed: {exc}",
                        )
                    raise
                if worker_id == "gw0":
                    write_state_file(f"mock_spy_bucket_{alias}", spy_bucket.name)

        # D-05: Mutate sam_env_vars on ALL workers for in-memory consistency
        sam_env_vars[function_name] = {
            "MOCK_SPY_BUCKET": spy_bucket.name,
            "MOCK_FUNCTION_NAME": alias,
            "AWS_ENDPOINT_URL_S3": "http://localstack:4566",
        }
        mock = LambdaMock(name=alias, bucket=spy_bucket)
        created.append(mock)
        return mock

    yield _make

    # No explicit teardown — bucket cleanup is handled by ``make_s3_bucket``
    # at end of session.

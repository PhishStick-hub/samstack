"""Tests for ``xdist_shared_session`` — the single coordinator helper.

This file owns the controller/worker/master branching contract that every
shared fixture now delegates to. Per-fixture tests verify wiring; this file
verifies coordination semantics once.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from samstack._xdist import Role, StateKeys, xdist_shared_session


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Pin every test to a fresh state directory."""
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    monkeypatch.setattr("samstack._xdist._STATE_FILE_LOCK", None, raising=False)


@contextmanager
def _resource(value: str = "the-resource") -> Generator[tuple[str, str], None, None]:
    yield value, value


@contextmanager
def _resource_split(user: str, state: str) -> Generator[tuple[str, str], None, None]:
    """Yield distinct user-resource and state-value (e.g., container vs URL)."""
    yield user, state


# ---------------------------------------------------------------------------
# Master path
# ---------------------------------------------------------------------------


class TestMasterPath:
    def test_runs_controller_yields_resource(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samstack._xdist.worker_role", lambda: Role.MASTER)

        write = MagicMock()
        monkeypatch.setattr("samstack._xdist.write_state_file", write)

        with xdist_shared_session("k", on_controller=lambda: _resource("v")) as r:
            assert r == "v"

        # Master never publishes to shared state — there is no audience.
        write.assert_not_called()

    def test_does_not_record_error_on_master(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samstack._xdist.worker_role", lambda: Role.MASTER)

        @contextmanager
        def _boom() -> Generator[tuple[str, str], None, None]:
            raise RuntimeError("kaboom")
            yield

        write_err = MagicMock()
        monkeypatch.setattr("samstack._xdist.write_error_for", write_err)

        with pytest.raises(RuntimeError, match="kaboom"):
            with xdist_shared_session("k", on_controller=_boom):
                pass

        write_err.assert_not_called()


# ---------------------------------------------------------------------------
# Controller path
# ---------------------------------------------------------------------------


class TestControllerPath:
    def test_writes_state_value_after_controller_setup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samstack._xdist.worker_role", lambda: Role.CONTROLLER)
        write = MagicMock()
        monkeypatch.setattr("samstack._xdist.write_state_file", write)

        with xdist_shared_session(
            "lambda_endpoint",
            on_controller=lambda: _resource_split("container-handle", "http://url"),
        ) as r:
            assert r == "container-handle"

        write.assert_called_once_with("lambda_endpoint", "http://url")

    def test_writes_per_key_error_on_controller_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samstack._xdist.worker_role", lambda: Role.CONTROLLER)

        @contextmanager
        def _boom() -> Generator[tuple[str, str], None, None]:
            raise RuntimeError("kaboom")
            yield

        write_err = MagicMock()
        monkeypatch.setattr("samstack._xdist.write_error_for", write_err)

        with pytest.raises(RuntimeError, match="kaboom"):
            with xdist_shared_session("k", on_controller=_boom):
                pass

        write_err.assert_called_once()
        args, _ = write_err.call_args
        assert args[0] == "k"  # per-key error slot, not the legacy 'error'
        assert "kaboom" in args[1]


# ---------------------------------------------------------------------------
# Worker path
# ---------------------------------------------------------------------------


class TestWorkerPath:
    def test_yields_state_value_directly_when_on_worker_omitted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samstack._xdist.worker_role", lambda: Role.WORKER)
        monkeypatch.setattr(
            "samstack._xdist.wait_for_state_key",
            lambda key, timeout=120: "http://shared",
        )
        controller_spy = MagicMock()
        monkeypatch.setattr("samstack._xdist.write_state_file", MagicMock())

        with xdist_shared_session("k", on_controller=controller_spy) as r:
            assert r == "http://shared"

        controller_spy.assert_not_called()  # worker must not run controller

    def test_on_worker_maps_state_value_to_user_resource(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samstack._xdist.worker_role", lambda: Role.WORKER)
        monkeypatch.setattr(
            "samstack._xdist.wait_for_state_key", lambda key, timeout=120: "BUCKET-X"
        )
        monkeypatch.setattr("samstack._xdist.write_state_file", MagicMock())

        seen = []

        def _wrap(state_value: str) -> str:
            seen.append(state_value)
            return f"proxy({state_value})"

        with xdist_shared_session(
            "k", on_controller=lambda: _resource(), on_worker=_wrap
        ) as r:
            assert r == "proxy(BUCKET-X)"

        assert seen == ["BUCKET-X"]

    def test_signals_worker_done_on_teardown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("samstack._xdist.worker_role", lambda: Role.WORKER)
        monkeypatch.setattr(
            "samstack._xdist.wait_for_state_key", lambda key, timeout=120: "v"
        )
        monkeypatch.setattr("samstack._xdist.get_worker_id", lambda: "gw3")

        write = MagicMock()
        monkeypatch.setattr("samstack._xdist.write_state_file", write)

        with xdist_shared_session("k", on_controller=lambda: _resource()):
            pass

        write.assert_called_once_with(StateKeys.worker_done("gw3"), True)

"""Wiring tests for sam_lambda_endpoint.

The xdist controller/worker branching, state writes, and error handling
are owned by ``samstack._xdist.xdist_shared_session`` and tested in
``test_xdist_shared_session.py``. These tests verify only the
fixture-specific concerns: which subprocess is started and how the
warm-mode is selected.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

import samstack.fixtures.sam_lambda as sl
from samstack._errors import SamStartupError
from samstack._xdist import Role

_sam_lambda_gen = getattr(sl.sam_lambda_endpoint, "__wrapped__")


def _settings() -> MagicMock:
    s = MagicMock()
    s.lambda_port = 3001
    s.start_lambda_args = []
    s.region = "us-east-1"
    return s


@contextmanager
def _service(url: str = "http://127.0.0.1:3001") -> Generator[str, None, None]:
    yield url


def _service_factory(url: str = "http://127.0.0.1:3001"):
    def _f(**_: Any) -> Any:
        return _service(url)

    return _f


def _patch_role(monkeypatch: pytest.MonkeyPatch, role: Role) -> None:
    """Patch role detection at the helper's import site."""
    monkeypatch.setattr("samstack._xdist.worker_role", lambda: role)
    # Helper writes only when role is CONTROLLER; stub state writes so the
    # tests don't touch the real state file.
    monkeypatch.setattr("samstack._xdist.write_state_file", MagicMock())
    monkeypatch.setattr("samstack._xdist.write_error_for", MagicMock())


class TestPreWarmAndContainer:
    """Master path covers the controller code; we exercise it via Role.MASTER."""

    def test_runs_container_and_pre_warms(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_role(monkeypatch, Role.MASTER)
        monkeypatch.setattr(sl, "_run_sam_service", _service_factory())

        pre_warm = MagicMock()
        monkeypatch.setattr(sl, "_pre_warm_functions", pre_warm)

        gen = _sam_lambda_gen(_settings(), None, "net", [], ["FuncA"])
        result = next(gen)

        assert result == "http://127.0.0.1:3001"
        pre_warm.assert_called_once_with(
            "http://127.0.0.1:3001", ["FuncA"], "us-east-1"
        )

    def test_uses_eager_when_no_warm_functions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_role(monkeypatch, Role.MASTER)
        run_spy = MagicMock(side_effect=lambda **_: _service())
        monkeypatch.setattr(sl, "_run_sam_service", run_spy)
        monkeypatch.setattr(sl, "_pre_warm_functions", MagicMock())

        gen = _sam_lambda_gen(_settings(), None, "net", [], [])
        next(gen)

        _, kwargs = run_spy.call_args
        assert kwargs["warm_containers"] == "EAGER"

    def test_pre_warm_failure_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_role(monkeypatch, Role.MASTER)
        monkeypatch.setattr(sl, "_run_sam_service", _service_factory())
        monkeypatch.setattr(
            sl,
            "_pre_warm_functions",
            MagicMock(side_effect=SamStartupError(port=0, log_tail="boom")),
        )

        gen = _sam_lambda_gen(_settings(), None, "net", [], ["FuncA"])
        with pytest.raises(SamStartupError):
            next(gen)


class TestWorkerPath:
    def test_yields_endpoint_from_state_without_docker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_role(monkeypatch, Role.WORKER)
        monkeypatch.setattr(
            "samstack._xdist.wait_for_state_key",
            lambda key, timeout=120: "http://127.0.0.1:3001",
        )
        run_spy = MagicMock()
        monkeypatch.setattr(sl, "_run_sam_service", run_spy)

        gen = _sam_lambda_gen(_settings(), None, "net", [], [])
        result = next(gen)

        assert result == "http://127.0.0.1:3001"
        run_spy.assert_not_called()

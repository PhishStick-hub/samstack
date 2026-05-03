"""Wiring tests for sam_api.

The xdist controller/worker branching, state writes, and error handling
are owned by ``samstack._xdist.xdist_shared_session`` and tested in
``test_xdist_shared_session.py``. These tests verify only the
fixture-specific concerns: container subcommand, route filtering, and
HTTP pre-warming.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

import samstack.fixtures.sam_api as sa
from samstack._errors import SamStartupError
from samstack._xdist import Role

_sam_api_gen = getattr(sa.sam_api, "__wrapped__")


def _settings() -> MagicMock:
    s = MagicMock()
    s.api_port = 3000
    s.start_api_args = []
    s.project_root = MagicMock()
    s.log_dir = "logs"
    return s


@contextmanager
def _service_ok(url: str = "http://127.0.0.1:3000") -> Generator[str, None, None]:
    yield url


@contextmanager
def _service_fail() -> Generator[str, None, None]:
    raise SamStartupError(port=3000, log_tail="container exited")
    yield  # unreachable


def _patch_role(monkeypatch: pytest.MonkeyPatch, role: Role) -> None:
    monkeypatch.setattr("samstack._xdist.worker_role", lambda: role)
    monkeypatch.setattr("samstack._xdist.write_state_file", MagicMock())
    monkeypatch.setattr("samstack._xdist.write_error_for", MagicMock())


class TestControllerPath:
    def test_runs_start_api_and_pre_warms(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_role(monkeypatch, Role.MASTER)
        monkeypatch.setattr(sa, "_run_sam_service", lambda *a, **kw: _service_ok())

        pre_warm = MagicMock()
        monkeypatch.setattr(sa, "_pre_warm_api_routes", pre_warm)

        gen = _sam_api_gen(
            _settings(), None, "net", "http://127.0.0.1:3001", [], [], {}
        )
        result = next(gen)
        assert result == "http://127.0.0.1:3000"
        pre_warm.assert_called_once()

    def test_pre_warm_failure_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_role(monkeypatch, Role.MASTER)
        monkeypatch.setattr(sa, "_run_sam_service", lambda *a, **kw: _service_ok())
        monkeypatch.setattr(
            sa,
            "_pre_warm_api_routes",
            MagicMock(side_effect=SamStartupError(port=0, log_tail="pre-warm boom")),
        )

        gen = _sam_api_gen(
            _settings(), None, "net", "http://127.0.0.1:3001", [], [], {}
        )
        with pytest.raises(SamStartupError):
            next(gen)

    def test_container_failure_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_role(monkeypatch, Role.MASTER)
        monkeypatch.setattr(sa, "_run_sam_service", lambda *a, **kw: _service_fail())

        gen = _sam_api_gen(
            _settings(), None, "net", "http://127.0.0.1:3001", [], [], {}
        )
        with pytest.raises(SamStartupError):
            next(gen)


class TestWorkerPath:
    def test_yields_endpoint_from_state_without_docker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_role(monkeypatch, Role.WORKER)
        monkeypatch.setattr(
            "samstack._xdist.wait_for_state_key",
            lambda key, timeout=120: "http://127.0.0.1:3000",
        )
        run_spy = MagicMock()
        monkeypatch.setattr(sa, "_run_sam_service", run_spy)

        gen = _sam_api_gen(
            _settings(), None, "net", "http://127.0.0.1:3001", [], [], {}
        )
        result = next(gen)
        assert result == "http://127.0.0.1:3000"
        run_spy.assert_not_called()

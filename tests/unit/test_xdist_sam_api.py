from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

import samstack.fixtures.sam_api as sa
from samstack._errors import SamStartupError
from samstack._xdist import Role, StateKeys

# Access raw fixture function (bypass pytest decorator)
_sam_api_gen = getattr(sa.sam_api, "__wrapped__")


def _make_mock_settings() -> MagicMock:
    """Return a MagicMock SamStackSettings with required fields for sam_api."""
    mock = MagicMock()
    mock.api_port = 3000
    mock.start_api_args = []
    mock.project_root = MagicMock()
    mock.log_dir = "logs"
    mock.sam_image = "public.ecr.aws/sam/build-python3.13"
    mock.template = "template.yaml"
    mock.docker_platform = "linux/amd64"
    mock.region = "us-east-1"
    return mock


# ---------------------------------------------------------------------------
# Helper context managers for mocking _run_sam_service
# ---------------------------------------------------------------------------


@contextmanager
def _mock_run_sam_service_success(
    url: str = "http://127.0.0.1:3000",
) -> Generator[str, None, None]:
    """Mock _run_sam_service that successfully yields a URL."""
    yield url


@contextmanager
def _mock_run_sam_service_error() -> Generator[str, None, None]:
    """Mock _run_sam_service that raises SamStartupError during setup."""
    raise SamStartupError(port=3000, log_tail="container exited")
    yield  # unreachable


# ---------------------------------------------------------------------------
# TestSamApiMaster
# ---------------------------------------------------------------------------


class TestSamApiMaster:
    def test_runs_container_and_pre_warms_on_master(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Master path: _run_sam_service invoked, _pre_warm_api_routes called,
        write_state_file NOT called, endpoint yielded."""
        monkeypatch.setattr(sa, "worker_role", lambda: Role.MASTER)
        monkeypatch.setattr(
            sa,
            "_run_sam_service",
            lambda *a, **kw: _mock_run_sam_service_success("http://127.0.0.1:3000"),
        )

        pre_warm_spy = MagicMock()
        monkeypatch.setattr(sa, "_pre_warm_api_routes", pre_warm_spy)

        write_spy = MagicMock()
        monkeypatch.setattr(sa, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_api_gen(
            mock_settings, None, "docker_net", "http://127.0.0.1:3001", [], [], {}
        )
        result = next(gen)

        assert result == "http://127.0.0.1:3000"
        pre_warm_spy.assert_called_once()
        write_spy.assert_not_called()

        gen.close()

    def test_does_not_write_state_file_on_master_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Master path on error: raises SamStartupError, write_state_file NOT called."""
        monkeypatch.setattr(sa, "worker_role", lambda: Role.MASTER)
        monkeypatch.setattr(
            sa,
            "_run_sam_service",
            lambda *a, **kw: _mock_run_sam_service_error(),
        )

        write_spy = MagicMock()
        monkeypatch.setattr(sa, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_api_gen(
            mock_settings, None, "docker_net", "http://127.0.0.1:3001", [], [], {}
        )

        with pytest.raises(SamStartupError):
            next(gen)

        write_spy.assert_not_called()


# ---------------------------------------------------------------------------
# TestSamApiGw0
# ---------------------------------------------------------------------------


class TestSamApiGw0:
    def test_runs_container_pre_warms_and_writes_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 path: runs container, pre-warms, writes sam_api_endpoint to state."""
        monkeypatch.setattr(sa, "worker_role", lambda: Role.CONTROLLER)
        monkeypatch.setattr(
            sa,
            "_run_sam_service",
            lambda *a, **kw: _mock_run_sam_service_success("http://127.0.0.1:3000"),
        )

        pre_warm_spy = MagicMock()
        monkeypatch.setattr(sa, "_pre_warm_api_routes", pre_warm_spy)

        write_spy = MagicMock()
        monkeypatch.setattr(sa, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_api_gen(
            mock_settings, None, "docker_net", "http://127.0.0.1:3001", [], [], {}
        )
        result = next(gen)

        assert result == "http://127.0.0.1:3000"
        pre_warm_spy.assert_called_once()
        write_spy.assert_called_once_with(
            StateKeys.SAM_API_ENDPOINT, "http://127.0.0.1:3000"
        )
        # Test isolation: also stub write_error_for so a teardown exception
        # doesn't accidentally hit the real implementation.
        monkeypatch.setattr(sa, "write_error_for", MagicMock())
        gen.close()

    def test_writes_error_on_pre_warm_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 pre-warm error: writes 'error' key to state, re-raises SamStartupError."""
        monkeypatch.setattr(sa, "worker_role", lambda: Role.CONTROLLER)
        monkeypatch.setattr(
            sa,
            "_run_sam_service",
            lambda *a, **kw: _mock_run_sam_service_success("http://127.0.0.1:3000"),
        )

        monkeypatch.setattr(
            sa,
            "_pre_warm_api_routes",
            MagicMock(
                side_effect=SamStartupError(
                    port=0,
                    log_tail="Pre-warm HTTP request failed for function 'TestFunc' (/hello): test error",
                )
            ),
        )

        error_spy = MagicMock()
        monkeypatch.setattr(sa, "write_error_for", error_spy)
        monkeypatch.setattr(sa, "write_state_file", MagicMock())

        mock_settings = _make_mock_settings()
        gen = _sam_api_gen(
            mock_settings, None, "docker_net", "http://127.0.0.1:3001", [], [], {}
        )

        with pytest.raises(SamStartupError):
            next(gen)

        error_spy.assert_called_once()
        args, _ = error_spy.call_args
        assert args[0] == StateKeys.SAM_API_ENDPOINT
        assert "sam_api container failed to start" in str(args[1])

    def test_writes_error_on_container_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 container error: _run_sam_service raises, writes 'error' key,
        re-raises SamStartupError."""
        monkeypatch.setattr(sa, "worker_role", lambda: Role.CONTROLLER)
        monkeypatch.setattr(
            sa,
            "_run_sam_service",
            lambda *a, **kw: _mock_run_sam_service_error(),
        )

        error_spy = MagicMock()
        monkeypatch.setattr(sa, "write_error_for", error_spy)
        monkeypatch.setattr(sa, "write_state_file", MagicMock())

        mock_settings = _make_mock_settings()
        gen = _sam_api_gen(
            mock_settings, None, "docker_net", "http://127.0.0.1:3001", [], [], {}
        )

        with pytest.raises(SamStartupError):
            next(gen)

        error_spy.assert_called_once()
        args, _ = error_spy.call_args
        assert args[0] == StateKeys.SAM_API_ENDPOINT
        assert "sam_api container failed to start" in str(args[1])


# ---------------------------------------------------------------------------
# TestSamApiGw1Plus
# ---------------------------------------------------------------------------


class TestSamApiGw1Plus:
    def test_waits_and_yields_endpoint_on_gw1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw1+ path: waits for state key, yields endpoint, no Docker calls."""
        monkeypatch.setattr(sa, "worker_role", lambda: Role.WORKER)

        wait_spy = MagicMock(return_value="http://127.0.0.1:3000")
        monkeypatch.setattr(sa, "wait_for_state_key", wait_spy)

        run_sam_spy = MagicMock()
        monkeypatch.setattr(sa, "_run_sam_service", run_sam_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_api_gen(
            mock_settings, None, "docker_net", "http://127.0.0.1:3001", [], [], {}
        )
        result = next(gen)

        assert result == "http://127.0.0.1:3000"
        wait_spy.assert_called_once_with(StateKeys.SAM_API_ENDPOINT, timeout=120)
        run_sam_spy.assert_not_called()

        gen.close()

    def test_returns_after_yield_on_gw1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ path: yields endpoint then returns immediately (StopIteration)."""
        monkeypatch.setattr(sa, "worker_role", lambda: Role.WORKER)

        monkeypatch.setattr(
            sa,
            "wait_for_state_key",
            MagicMock(return_value="http://127.0.0.1:3000"),
        )

        mock_settings = _make_mock_settings()
        gen = _sam_api_gen(
            mock_settings, None, "docker_net", "http://127.0.0.1:3001", [], [], {}
        )

        result = next(gen)
        assert result == "http://127.0.0.1:3000"

        # Second advance should raise StopIteration (gw1+ returns after yield)
        with pytest.raises(StopIteration):
            next(gen)

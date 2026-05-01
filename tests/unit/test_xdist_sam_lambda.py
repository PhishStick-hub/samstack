from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest

import samstack.fixtures.sam_lambda as sl
from samstack._errors import SamStartupError

# Access raw fixture function (bypass pytest decorator)
_sam_lambda_gen = getattr(sl.sam_lambda_endpoint, "__wrapped__")


def _make_mock_settings() -> MagicMock:
    """Return a MagicMock SamStackSettings with required fields."""
    mock = MagicMock()
    mock.lambda_port = 3001
    mock.start_lambda_args = []
    mock.log_dir = "logs"
    mock.sam_image = "public.ecr.aws/sam/build-python3.13"
    mock.template = "template.yaml"
    mock.docker_platform = "linux/amd64"
    mock.region = "us-east-1"
    return mock


@contextmanager
def _make_mock_service(endpoint: str) -> Generator[str, None, None]:
    """Context manager that mimics _run_sam_service — yields endpoint URL."""
    yield endpoint


def _service_wrapper(endpoint: str = "http://127.0.0.1:3001"):
    """Callable that accepts _run_sam_service kwargs and returns a context manager."""

    def _inner(**kwargs: Any) -> Any:
        return _make_mock_service(endpoint)

    return _inner


# ---------------------------------------------------------------------------
# TestSamLambdaEndpointMaster
# ---------------------------------------------------------------------------


class TestSamLambdaEndpointMaster:
    def test_runs_container_and_pre_warms_with_functions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Master path: runs container, pre-warms functions, does NOT write to state."""
        monkeypatch.setattr(sl, "get_worker_id", lambda: "master")

        monkeypatch.setattr(
            sl,
            "_run_sam_service",
            _service_wrapper("http://127.0.0.1:3001"),
        )

        pre_warm_spy = MagicMock()
        monkeypatch.setattr(sl, "_pre_warm_functions", pre_warm_spy)

        write_spy = MagicMock()
        monkeypatch.setattr(sl, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_lambda_gen(mock_settings, None, "docker_net", [], ["FuncA"])
        result = next(gen)

        pre_warm_spy.assert_called_once_with(
            "http://127.0.0.1:3001", ["FuncA"], "us-east-1"
        )
        write_spy.assert_not_called()
        assert result == "http://127.0.0.1:3001"

    def test_uses_eager_when_no_warm_functions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Master path: uses EAGER warm mode when warm_functions is empty."""
        monkeypatch.setattr(sl, "get_worker_id", lambda: "master")

        # Capture _run_sam_service call args to verify warm_containers
        run_spy = MagicMock()
        run_spy.side_effect = lambda **kwargs: _make_mock_service(
            "http://127.0.0.1:3001"
        )
        monkeypatch.setattr(sl, "_run_sam_service", run_spy)

        monkeypatch.setattr(sl, "_pre_warm_functions", MagicMock())
        monkeypatch.setattr(sl, "write_state_file", MagicMock())

        mock_settings = _make_mock_settings()
        gen = _sam_lambda_gen(
            mock_settings,
            None,
            "docker_net",
            [],
            [],  # empty warm_functions
        )
        next(gen)

        # Verify _run_sam_service was called with warm_containers="EAGER"
        _, kwargs = run_spy.call_args
        assert kwargs["warm_containers"] == "EAGER"

    def test_does_not_write_state_on_master_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Master path: re-raises SamStartupError without writing to state file."""
        monkeypatch.setattr(sl, "get_worker_id", lambda: "master")

        monkeypatch.setattr(
            sl,
            "_run_sam_service",
            _service_wrapper("http://127.0.0.1:3001"),
        )
        monkeypatch.setattr(
            sl,
            "_pre_warm_functions",
            MagicMock(
                side_effect=SamStartupError(port=0, log_tail="Pre-warm invoke failed")
            ),
        )

        write_spy = MagicMock()
        monkeypatch.setattr(sl, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_lambda_gen(mock_settings, None, "docker_net", [], ["FuncA"])

        with pytest.raises(SamStartupError):
            next(gen)

        write_spy.assert_not_called()


# ---------------------------------------------------------------------------
# TestSamLambdaEndpointGw0
# ---------------------------------------------------------------------------


class TestSamLambdaEndpointGw0:
    def test_writes_endpoint_after_pre_warm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 path: writes sam_lambda_endpoint to shared state after pre-warm."""
        monkeypatch.setattr(sl, "get_worker_id", lambda: "gw0")

        monkeypatch.setattr(
            sl,
            "_run_sam_service",
            _service_wrapper("http://127.0.0.1:3001"),
        )
        monkeypatch.setattr(sl, "_pre_warm_functions", MagicMock())

        write_spy = MagicMock()
        monkeypatch.setattr(sl, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_lambda_gen(mock_settings, None, "docker_net", [], ["FuncA"])
        result = next(gen)

        assert result == "http://127.0.0.1:3001"
        write_spy.assert_called_once_with(
            "sam_lambda_endpoint", "http://127.0.0.1:3001"
        )

    def test_writes_error_on_pre_warm_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 path: writes error key when _pre_warm_functions fails, re-raises."""
        monkeypatch.setattr(sl, "get_worker_id", lambda: "gw0")

        monkeypatch.setattr(
            sl,
            "_run_sam_service",
            _service_wrapper("http://127.0.0.1:3001"),
        )
        monkeypatch.setattr(
            sl,
            "_pre_warm_functions",
            MagicMock(
                side_effect=SamStartupError(
                    port=0, log_tail="Pre-warm invoke failed for function 'FuncA'"
                )
            ),
        )

        write_spy = MagicMock()
        monkeypatch.setattr(sl, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_lambda_gen(mock_settings, None, "docker_net", [], ["FuncA"])

        with pytest.raises(SamStartupError):
            next(gen)

        write_spy.assert_called_once()
        args, _ = write_spy.call_args
        assert args[0] == "error"
        assert "sam_lambda_endpoint container failed to start" in str(args[1])

    def test_writes_error_on_container_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 path: writes error key when _run_sam_service fails, re-raises."""
        monkeypatch.setattr(sl, "get_worker_id", lambda: "gw0")

        monkeypatch.setattr(
            sl,
            "_run_sam_service",
            MagicMock(
                side_effect=SamStartupError(
                    port=3001, log_tail="Container exited prematurely"
                )
            ),
        )

        monkeypatch.setattr(sl, "_pre_warm_functions", MagicMock())

        write_spy = MagicMock()
        monkeypatch.setattr(sl, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_lambda_gen(mock_settings, None, "docker_net", [], ["FuncA"])

        with pytest.raises(SamStartupError):
            next(gen)

        write_spy.assert_called_once()
        args, _ = write_spy.call_args
        assert args[0] == "error"
        assert "sam_lambda_endpoint container failed to start" in str(args[1])


# ---------------------------------------------------------------------------
# TestSamLambdaEndpointGw1Plus
# ---------------------------------------------------------------------------


class TestSamLambdaEndpointGw1Plus:
    def test_waits_and_yields_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ path: calls wait_for_state_key, yields endpoint, no Docker calls."""
        monkeypatch.setattr(sl, "get_worker_id", lambda: "gw1")

        wait_spy = MagicMock(return_value="http://127.0.0.1:3001")
        monkeypatch.setattr(sl, "wait_for_state_key", wait_spy)

        run_spy = MagicMock()
        monkeypatch.setattr(sl, "_run_sam_service", run_spy)

        mock_settings = _make_mock_settings()
        gen = _sam_lambda_gen(mock_settings, None, "docker_net", [], ["FuncA"])
        result = next(gen)

        assert result == "http://127.0.0.1:3001"
        wait_spy.assert_called_once_with("sam_lambda_endpoint", timeout=120)
        run_spy.assert_not_called()

    def test_returns_after_yield(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ path: generator raises StopIteration after yielding (returns, no teardown)."""
        monkeypatch.setattr(sl, "get_worker_id", lambda: "gw2")

        monkeypatch.setattr(
            sl,
            "wait_for_state_key",
            MagicMock(return_value="http://127.0.0.1:3001"),
        )

        mock_settings = _make_mock_settings()
        gen = _sam_lambda_gen(mock_settings, None, "docker_net", [], [])
        result = next(gen)
        assert result == "http://127.0.0.1:3001"

        # gw1+ path returns after yield — second next() should raise StopIteration
        with pytest.raises(StopIteration):
            next(gen)

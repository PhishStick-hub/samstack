from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import samstack.fixtures.sam_build as sb
from samstack._errors import SamBuildError
from samstack._xdist import Role, StateKeys

# Access raw fixture function (bypass pytest decorator)
_sam_build_raw = getattr(sb.sam_build, "__wrapped__")


def _make_mock_settings() -> MagicMock:
    mock_settings = MagicMock()
    mock_settings.sam_image = "public.ecr.aws/sam/build-python3.13"
    mock_settings.project_root = Path("/tmp/test")
    mock_settings.log_dir = "logs"
    mock_settings.template = "template.yaml"
    mock_settings.build_args = []
    mock_settings.docker_platform = "linux/amd64"
    mock_settings.add_gitignore = False
    return mock_settings


_mock_env_vars: dict[str, dict[str, str]] = {"Parameters": {"TEST_VAR": "value"}}

_ERROR_KEY = StateKeys.error_for(StateKeys.BUILD_COMPLETE)


# ---------------------------------------------------------------------------
# TestSamBuildMaster
# ---------------------------------------------------------------------------


class TestSamBuildMaster:
    def test_runs_build_on_master(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Master runs run_one_shot_container; never writes state or waits."""
        monkeypatch.setattr(sb, "worker_role", lambda: Role.MASTER)
        monkeypatch.setattr(sb, "_is_ci", lambda: False)

        run_spy = MagicMock(return_value=("build logs", 0))
        monkeypatch.setattr(sb, "run_one_shot_container", run_spy)

        write_spy = MagicMock()
        monkeypatch.setattr(sb, "write_state_file", write_spy)
        monkeypatch.setattr(sb, "write_error_for", MagicMock())

        wait_spy = MagicMock()
        monkeypatch.setattr(sb, "wait_for_state_key", wait_spy)

        mock_settings = _make_mock_settings()
        _sam_build_raw(mock_settings, _mock_env_vars)

        run_spy.assert_called_once()
        write_spy.assert_not_called()
        wait_spy.assert_not_called()

    def test_raises_on_build_failure_master(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Master raises SamBuildError on non-zero exit; never writes state."""
        monkeypatch.setattr(sb, "worker_role", lambda: Role.MASTER)
        monkeypatch.setattr(sb, "_is_ci", lambda: False)

        monkeypatch.setattr(
            sb,
            "run_one_shot_container",
            MagicMock(return_value=("error logs", 1)),
        )

        write_spy = MagicMock()
        monkeypatch.setattr(sb, "write_state_file", write_spy)
        error_spy = MagicMock()
        monkeypatch.setattr(sb, "write_error_for", error_spy)

        mock_settings = _make_mock_settings()
        with pytest.raises(SamBuildError):
            _sam_build_raw(mock_settings, _mock_env_vars)

        write_spy.assert_not_called()
        error_spy.assert_not_called()


# ---------------------------------------------------------------------------
# TestSamBuildController (gw0)
# ---------------------------------------------------------------------------


class TestSamBuildController:
    def test_runs_build_and_writes_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Controller runs build and writes build_complete=True after success."""
        monkeypatch.setattr(sb, "worker_role", lambda: Role.CONTROLLER)
        monkeypatch.setattr(sb, "_is_ci", lambda: False)

        run_spy = MagicMock(return_value=("build logs", 0))
        monkeypatch.setattr(sb, "run_one_shot_container", run_spy)

        write_spy = MagicMock()
        monkeypatch.setattr(sb, "write_state_file", write_spy)
        monkeypatch.setattr(sb, "write_error_for", MagicMock())

        mock_settings = _make_mock_settings()
        _sam_build_raw(mock_settings, _mock_env_vars)

        run_spy.assert_called_once()
        write_spy.assert_called_once_with(StateKeys.BUILD_COMPLETE, True)

    def test_writes_error_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Controller writes per-key error on build failure and re-raises."""
        monkeypatch.setattr(sb, "worker_role", lambda: Role.CONTROLLER)
        monkeypatch.setattr(sb, "_is_ci", lambda: False)

        monkeypatch.setattr(
            sb,
            "run_one_shot_container",
            MagicMock(return_value=("build failed", 1)),
        )

        write_spy = MagicMock()
        monkeypatch.setattr(sb, "write_state_file", write_spy)
        error_spy = MagicMock()
        monkeypatch.setattr(sb, "write_error_for", error_spy)

        mock_settings = _make_mock_settings()
        with pytest.raises(SamBuildError):
            _sam_build_raw(mock_settings, _mock_env_vars)

        # Per-key error slot, not the legacy "error" slot
        error_spy.assert_called_once()
        args, _ = error_spy.call_args
        assert args[0] == StateKeys.BUILD_COMPLETE
        write_spy.assert_not_called()


# ---------------------------------------------------------------------------
# TestSamBuildWorker (gw1+)
# ---------------------------------------------------------------------------


class TestSamBuildWorker:
    def test_waits_for_build_complete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Worker waits for build_complete and never runs Docker."""
        monkeypatch.setattr(sb, "worker_role", lambda: Role.WORKER)

        run_spy = MagicMock()
        monkeypatch.setattr(sb, "run_one_shot_container", run_spy)

        wait_spy = MagicMock(return_value=True)
        monkeypatch.setattr(sb, "wait_for_state_key", wait_spy)

        mock_settings = _make_mock_settings()
        _sam_build_raw(mock_settings, _mock_env_vars)

        wait_spy.assert_called_once_with(StateKeys.BUILD_COMPLETE, timeout=300)
        run_spy.assert_not_called()

    def test_fails_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Worker re-raises pytest.fail when error recorded in state."""
        monkeypatch.setattr(sb, "worker_role", lambda: Role.WORKER)

        monkeypatch.setattr(
            sb,
            "wait_for_state_key",
            MagicMock(side_effect=pytest.fail.Exception("controller startup failed")),
        )

        mock_settings = _make_mock_settings()
        with pytest.raises(pytest.fail.Exception):
            _sam_build_raw(mock_settings, _mock_env_vars)


# Suppress unused-name warning when tests don't reference _ERROR_KEY directly.
_ = _ERROR_KEY

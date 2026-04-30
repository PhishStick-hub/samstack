from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import samstack.fixtures.sam_build as sb
from samstack._errors import SamBuildError

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


# ---------------------------------------------------------------------------
# TestSamBuildMaster
# ---------------------------------------------------------------------------


class TestSamBuildMaster:
    def test_runs_build_on_master(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Master path runs run_one_shot_container; does NOT call write_state_file or wait_for_state_key."""
        monkeypatch.setattr(sb, "get_worker_id", lambda: "master")
        monkeypatch.setattr(sb, "_is_ci", lambda: False)

        run_spy = MagicMock(return_value=("build logs", 0))
        monkeypatch.setattr(sb, "run_one_shot_container", run_spy)

        write_spy = MagicMock()
        monkeypatch.setattr(sb, "write_state_file", write_spy)

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
        """Master path raises SamBuildError on non-zero exit; does NOT write state file."""
        monkeypatch.setattr(sb, "get_worker_id", lambda: "master")
        monkeypatch.setattr(sb, "_is_ci", lambda: False)

        monkeypatch.setattr(
            sb,
            "run_one_shot_container",
            MagicMock(return_value=("error logs", 1)),
        )

        write_spy = MagicMock()
        monkeypatch.setattr(sb, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        with pytest.raises(SamBuildError):
            _sam_build_raw(mock_settings, _mock_env_vars)

        write_spy.assert_not_called()


# ---------------------------------------------------------------------------
# TestSamBuildGw0
# ---------------------------------------------------------------------------


class TestSamBuildGw0:
    def test_runs_build_and_writes_flag_on_gw0(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 runs run_one_shot_container and writes build_complete=True after success."""
        monkeypatch.setattr(sb, "get_worker_id", lambda: "gw0")
        monkeypatch.setattr(sb, "_is_ci", lambda: False)

        run_spy = MagicMock(return_value=("build logs", 0))
        monkeypatch.setattr(sb, "run_one_shot_container", run_spy)

        write_spy = MagicMock()
        monkeypatch.setattr(sb, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        _sam_build_raw(mock_settings, _mock_env_vars)

        run_spy.assert_called_once()
        write_spy.assert_called_once_with("build_complete", True)

    def test_writes_error_on_failure_gw0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw0 writes error key on build failure and re-raises SamBuildError."""
        monkeypatch.setattr(sb, "get_worker_id", lambda: "gw0")
        monkeypatch.setattr(sb, "_is_ci", lambda: False)

        monkeypatch.setattr(
            sb,
            "run_one_shot_container",
            MagicMock(return_value=("build failed", 1)),
        )

        write_spy = MagicMock()
        monkeypatch.setattr(sb, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        with pytest.raises(SamBuildError):
            _sam_build_raw(mock_settings, _mock_env_vars)

        # Must write error key (not build_complete)
        write_spy.assert_called_once()
        args, _ = write_spy.call_args
        assert args[0] == "error"


# ---------------------------------------------------------------------------
# TestSamBuildGw1
# ---------------------------------------------------------------------------


class TestSamBuildGw1:
    def test_waits_for_build_complete_on_gw1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw1+ calls wait_for_state_key("build_complete", timeout=300) and returns without running Docker."""
        monkeypatch.setattr(sb, "get_worker_id", lambda: "gw1")

        run_spy = MagicMock()
        monkeypatch.setattr(sb, "run_one_shot_container", run_spy)

        wait_spy = MagicMock(return_value=True)
        monkeypatch.setattr(sb, "wait_for_state_key", wait_spy)

        mock_settings = _make_mock_settings()
        _sam_build_raw(mock_settings, _mock_env_vars)

        wait_spy.assert_called_once_with("build_complete", timeout=300)
        run_spy.assert_not_called()

    def test_fails_on_error_gw1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ raises pytest.fail.Exception when error key detected in state."""
        monkeypatch.setattr(sb, "get_worker_id", lambda: "gw1")

        monkeypatch.setattr(
            sb,
            "wait_for_state_key",
            MagicMock(
                side_effect=pytest.fail.Exception("gw0 infrastructure startup failed")
            ),
        )

        mock_settings = _make_mock_settings()
        with pytest.raises(pytest.fail.Exception):
            _sam_build_raw(mock_settings, _mock_env_vars)

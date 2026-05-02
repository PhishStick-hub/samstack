from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import samstack.fixtures.localstack as loc
from samstack._xdist import Role, StateKeys

# Access raw fixture functions (bypass pytest decorator)
_localstack_endpoint_raw: Callable[[object], str] = getattr(
    loc.localstack_endpoint, "__wrapped__"
)
_localstack_container_gen: Callable[[object, str], Generator[object, None, None]] = (
    getattr(loc.localstack_container, "__wrapped__")
)


# ---------------------------------------------------------------------------
# TestLocalStackEndpointMaster
# ---------------------------------------------------------------------------


class TestLocalStackEndpointMaster:
    def test_returns_container_url_on_master(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """master path: localstack_endpoint delegates to container.get_url()."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.MASTER)

        write_spy = MagicMock()
        monkeypatch.setattr(loc, "write_state_file", write_spy)

        proxy = loc._LocalStackContainerProxy("http://127.0.0.1:4566")
        result = _localstack_endpoint_raw(proxy)

        assert result == "http://127.0.0.1:4566"
        write_spy.assert_not_called()


# ---------------------------------------------------------------------------
# TestLocalStackEndpointGw0
# ---------------------------------------------------------------------------


class TestLocalStackEndpointGw0:
    def test_returns_container_url_on_gw0(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 path: localstack_endpoint returns container.get_url()."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)

        mock_container = MagicMock()
        mock_container.get_url.return_value = "http://127.0.0.1:4566"

        result = _localstack_endpoint_raw(mock_container)

        assert result == "http://127.0.0.1:4566"

    def test_does_not_write_state_directly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 path: localstack_endpoint itself does NOT write state (container does).

        The write_state_file("localstack_endpoint") call is made in localstack_container,
        not in localstack_endpoint. localstack_endpoint simply calls get_url().
        """
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)

        write_spy = MagicMock()
        monkeypatch.setattr(loc, "write_state_file", write_spy)

        mock_container = MagicMock()
        mock_container.get_url.return_value = "http://127.0.0.1:4566"

        result = _localstack_endpoint_raw(mock_container)

        assert result == "http://127.0.0.1:4566"
        write_spy.assert_not_called()


# ---------------------------------------------------------------------------
# TestLocalStackEndpointGw1
# ---------------------------------------------------------------------------


class TestLocalStackEndpointGw1:
    def test_returns_endpoint_from_proxy_on_gw1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw1+ path: localstack_endpoint returns proxy.get_url()."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.WORKER)

        proxy = loc._LocalStackContainerProxy("http://127.0.0.1:4566")
        result = _localstack_endpoint_raw(proxy)

        assert result == "http://127.0.0.1:4566"

    def test_proxy_get_wrapped_container_returns_none(self) -> None:
        """_LocalStackContainerProxy.get_wrapped_container() always returns None."""
        proxy = loc._LocalStackContainerProxy("http://x:4566")
        assert proxy.get_wrapped_container() is None

    def test_proxy_stop_is_noop(self) -> None:
        """_LocalStackContainerProxy.stop() does not raise."""
        proxy = loc._LocalStackContainerProxy("http://x:4566")
        proxy.stop()  # Must not raise


# ---------------------------------------------------------------------------
# TestLocalStackContainerMaster
# ---------------------------------------------------------------------------


def _make_mock_settings() -> MagicMock:
    mock_settings = MagicMock()
    mock_settings.localstack_image = "localstack/localstack:latest"
    mock_settings.project_root = Path("/tmp/test")
    mock_settings.log_dir = "logs"
    return mock_settings


def _setup_docker_mocks(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    """Set up mocked LocalStackContainer and Docker SDK client."""
    mock_inner = MagicMock()
    mock_container = MagicMock()
    mock_container.get_url.return_value = "http://127.0.0.1:4566"
    mock_container.get_wrapped_container.return_value = mock_inner
    monkeypatch.setattr(
        loc, "LocalStackContainer", MagicMock(return_value=mock_container)
    )

    mock_client = MagicMock()
    monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: mock_client)

    monkeypatch.setattr(loc, "_connect_container_with_alias", MagicMock())
    monkeypatch.setattr(loc, "_disconnect_container_from_network", MagicMock())
    monkeypatch.setattr(loc, "stream_logs_to_file", MagicMock())

    return mock_container, mock_client


class TestLocalStackContainerMaster:
    def test_creates_and_starts_on_master(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """master path: creates LocalStack container, starts it, does NOT write state."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.MASTER)

        mock_container, _ = _setup_docker_mocks(monkeypatch)

        write_spy = MagicMock()
        monkeypatch.setattr(loc, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _localstack_container_gen(mock_settings, "samstack-net")
        next(gen)

        mock_container.start.assert_called_once()
        write_spy.assert_not_called()

    def test_stops_on_teardown_master(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """master path: container.stop() is called on teardown."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.MASTER)

        mock_container, _ = _setup_docker_mocks(monkeypatch)

        mock_settings = _make_mock_settings()
        gen = _localstack_container_gen(mock_settings, "samstack-net")
        next(gen)

        gen.close()

        mock_container.stop.assert_called()


# ---------------------------------------------------------------------------
# TestLocalStackContainerGw0
# ---------------------------------------------------------------------------


class TestLocalStackContainerGw0:
    def test_creates_starts_writes_endpoint_on_gw0(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 path: creates container, writes localstack_endpoint to state."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)

        mock_container, _ = _setup_docker_mocks(monkeypatch)

        write_spy = MagicMock()
        monkeypatch.setattr(loc, "write_state_file", write_spy)

        mock_settings = _make_mock_settings()
        gen = _localstack_container_gen(mock_settings, "samstack-net")
        next(gen)

        mock_container.start.assert_called_once()
        write_spy.assert_called_with(
            StateKeys.LOCALSTACK_ENDPOINT, "http://127.0.0.1:4566"
        )

    def test_writes_error_on_failure_gw0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw0 path: writes error key to state on Docker failure, re-raises."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)

        mock_inner = MagicMock()
        mock_container = MagicMock()
        mock_container.get_wrapped_container.return_value = mock_inner
        mock_container.start.side_effect = Exception("docker fail")
        monkeypatch.setattr(
            loc, "LocalStackContainer", MagicMock(return_value=mock_container)
        )
        monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: MagicMock())
        monkeypatch.setattr(loc, "_connect_container_with_alias", MagicMock())
        monkeypatch.setattr(loc, "stream_logs_to_file", MagicMock())

        error_spy = MagicMock()
        monkeypatch.setattr(loc, "write_error_for", error_spy)
        monkeypatch.setattr(loc, "write_state_file", MagicMock())

        mock_settings = _make_mock_settings()
        gen = _localstack_container_gen(mock_settings, "samstack-net")
        with pytest.raises(Exception, match="docker fail"):
            next(gen)

        error_spy.assert_called_with(
            StateKeys.LOCALSTACK_ENDPOINT, "LocalStack container failed to start"
        )

    def test_stops_and_disconnects_on_teardown_gw0(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 path: container.stop() and disconnect called on teardown."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)

        mock_container, _ = _setup_docker_mocks(monkeypatch)
        disconnect_spy = MagicMock()
        monkeypatch.setattr(loc, "_disconnect_container_from_network", disconnect_spy)
        monkeypatch.setattr(loc, "write_state_file", MagicMock())
        monkeypatch.setattr(loc, "wait_for_workers_done", MagicMock())

        mock_settings = _make_mock_settings()
        gen = _localstack_container_gen(mock_settings, "samstack-net")
        next(gen)

        gen.close()

        mock_container.stop.assert_called()
        disconnect_spy.assert_called()

    def test_waits_for_workers_before_stopping(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Controller blocks on wait_for_workers_done BEFORE container.stop()."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)

        mock_container, _ = _setup_docker_mocks(monkeypatch)
        monkeypatch.setattr(loc, "write_state_file", MagicMock())

        call_order: list[str] = []
        monkeypatch.setattr(
            loc,
            "wait_for_workers_done",
            lambda: call_order.append("wait"),
        )
        mock_container.stop.side_effect = lambda: call_order.append("stop")

        mock_settings = _make_mock_settings()
        gen = _localstack_container_gen(mock_settings, "samstack-net")
        next(gen)
        gen.close()

        assert call_order == ["wait", "stop"], (
            f"wait_for_workers_done must run before container.stop; got {call_order}"
        )


# ---------------------------------------------------------------------------
# TestLocalStackContainerGw1
# ---------------------------------------------------------------------------


class TestLocalStackContainerGw1:
    def test_yields_proxy_without_docker_calls_gw1(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw1+ path: yields _LocalStackContainerProxy, no Docker API calls."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.WORKER)
        monkeypatch.setattr(
            loc,
            "wait_for_state_key",
            lambda key, timeout=120: "http://127.0.0.1:4566",
        )

        mock_client = MagicMock()
        from_env_spy = MagicMock(return_value=mock_client)
        monkeypatch.setattr(loc.docker_sdk, "from_env", from_env_spy)

        mock_settings = _make_mock_settings()
        gen = _localstack_container_gen(mock_settings, "samstack-net")
        result = next(gen)

        assert isinstance(result, loc._LocalStackContainerProxy)
        assert result.get_url() == "http://127.0.0.1:4566"
        from_env_spy.assert_not_called()

    def test_no_teardown_on_gw1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ path: no container.stop() or disconnect on teardown."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.WORKER)
        monkeypatch.setattr(
            loc,
            "wait_for_state_key",
            lambda key, timeout=120: "http://127.0.0.1:4566",
        )

        disconnect_spy = MagicMock()
        monkeypatch.setattr(loc, "_disconnect_container_from_network", disconnect_spy)

        mock_container = MagicMock()
        monkeypatch.setattr(
            loc, "LocalStackContainer", MagicMock(return_value=mock_container)
        )
        monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: MagicMock())

        mock_settings = _make_mock_settings()
        gen = _localstack_container_gen(mock_settings, "samstack-net")
        next(gen)

        gen.close()

        mock_container.stop.assert_not_called()
        disconnect_spy.assert_not_called()

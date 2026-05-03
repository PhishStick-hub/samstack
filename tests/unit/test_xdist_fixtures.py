from __future__ import annotations

import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from testcontainers.core.labels import LABEL_SESSION_ID, SESSION_ID

import samstack.fixtures.localstack as loc
from samstack._xdist import Role, StateKeys

# Access raw fixture functions (bypass pytest decorator)
_docker_network_name: Callable[[pytest.FixtureRequest], str] = getattr(
    loc.docker_network_name, "__wrapped__"
)
_docker_network_gen: Callable[[str], Generator[str, None, None]] = getattr(
    loc.docker_network, "__wrapped__"
)


def _fake_lock_always_acquired():
    @contextmanager
    def _cm():
        yield

    return _cm


def _make_infra_lock_cm(acquire_spy=None, release_spy=None):
    @contextmanager
    def _cm():
        if acquire_spy:
            acquire_spy()
        try:
            yield
        finally:
            if release_spy:
                release_spy()

    return _cm


def _make_infra_lock_cm(acquire_spy=None, release_spy=None):
    @contextmanager
    def _cm():
        if acquire_spy:
            acquire_spy()
        try:
            yield True
        finally:
            if release_spy:
                release_spy()

    return _cm


# ---------------------------------------------------------------------------
# TestDockerNetworkNameMaster
# ---------------------------------------------------------------------------


class TestDockerNetworkNameMaster:
    def test_generates_uuid_on_master(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw0/master generates a samstack-{uuid8} name from uuid4()."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.MASTER)

        mock_request = MagicMock()
        result = _docker_network_name(mock_request)
        assert re.match(r"^samstack-[a-f0-9]{8}$", result)


# ---------------------------------------------------------------------------
# TestDockerNetworkNameGw0
# ---------------------------------------------------------------------------


class TestDockerNetworkNameGw0:
    def test_generates_uuid_on_gw0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw0 generates its own samstack-{uuid8} name (identical to master path)."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)

        mock_request = MagicMock()
        result = _docker_network_name(mock_request)
        assert re.match(r"^samstack-[a-f0-9]{8}$", result)


# ---------------------------------------------------------------------------
# TestDockerNetworkNameGw1
# ---------------------------------------------------------------------------


class TestDockerNetworkNameGw1:
    def test_returns_empty_string_on_gw1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ returns '' — coordination moves into docker_network via wait_for_state_key."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.WORKER)

        mock_request = MagicMock()
        result = _docker_network_name(mock_request)
        assert result == ""


# ---------------------------------------------------------------------------
# Shared mock for Reaper (used by master/gw0 create paths)
# ---------------------------------------------------------------------------


def _mock_reaper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent Reaper.get_instance() from doing real Docker work."""
    monkeypatch.setattr(loc.Reaper, "get_instance", MagicMock())


# ---------------------------------------------------------------------------
# TestDockerNetworkMaster
# ---------------------------------------------------------------------------


class TestDockerNetworkMaster:
    def test_creates_network_on_master(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Master path creates Docker network, does NOT write state file."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.MASTER)
        _mock_reaper(monkeypatch)
        monkeypatch.setattr(loc.testcontainers_config, "ryuk_disabled", True)

        mock_client = MagicMock()
        mock_network = MagicMock()
        mock_network.name = "samstack-test"
        mock_client.networks.create.return_value = mock_network
        monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: mock_client)

        write_spy = MagicMock()
        monkeypatch.setattr(loc, "write_state_file", write_spy)

        gen = _docker_network_gen("samstack-abc12345")
        next(gen)

        mock_client.networks.create.assert_called_once_with(
            "samstack-abc12345",
            driver="bridge",
            labels={LABEL_SESSION_ID: SESSION_ID},
        )
        write_spy.assert_not_called()

    def test_teardown_cleans_up_on_master(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Master teardown calls _teardown_network."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.MASTER)
        _mock_reaper(monkeypatch)
        monkeypatch.setattr(loc.testcontainers_config, "ryuk_disabled", True)

        mock_client = MagicMock()
        mock_network = MagicMock()
        mock_network.name = "samstack-test"
        mock_client.networks.create.return_value = mock_network
        monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: mock_client)

        teardown_spy = MagicMock()
        monkeypatch.setattr(loc, "_teardown_network", teardown_spy)

        gen = _docker_network_gen("samstack-master")
        result = next(gen)
        assert result == "samstack-master"

        # Trigger teardown (close generator)
        gen.close()

        teardown_spy.assert_called_once()
        args, _ = teardown_spy.call_args
        assert args[1] == "samstack-master"


# ---------------------------------------------------------------------------
# TestDockerNetworkGw0
# ---------------------------------------------------------------------------


class TestDockerNetworkGw0:
    def test_creates_network_and_writes_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gw0 creates network, acquires lock, writes state file."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)
        _mock_reaper(monkeypatch)
        monkeypatch.setattr(loc.testcontainers_config, "ryuk_disabled", True)

        mock_client = MagicMock()
        mock_network = MagicMock()
        mock_network.name = "samstack-test"
        mock_client.networks.create.return_value = mock_network
        monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: mock_client)

        monkeypatch.setattr(loc, "infra_lock", _fake_lock_always_acquired())
        write_spy = MagicMock()
        monkeypatch.setattr(loc, "write_state_file", write_spy)

        gen = _docker_network_gen("samstack-gw0")
        next(gen)

        mock_client.networks.create.assert_called_once_with(
            "samstack-gw0",
            driver="bridge",
            labels={LABEL_SESSION_ID: SESSION_ID},
        )
        write_spy.assert_called_with(StateKeys.DOCKER_NETWORK, "samstack-gw0")

    def test_acquires_and_releases_lock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw0 acquires infra lock before creation, releases in teardown."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)
        _mock_reaper(monkeypatch)
        monkeypatch.setattr(loc.testcontainers_config, "ryuk_disabled", True)

        mock_client = MagicMock()
        mock_network = MagicMock()
        mock_network.name = "samstack-test"
        mock_client.networks.create.return_value = mock_network
        monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: mock_client)

        lock_acquire_spy = MagicMock()
        lock_release_spy = MagicMock()
        monkeypatch.setattr(
            loc, "infra_lock", _make_infra_lock_cm(lock_acquire_spy, lock_release_spy)
        )
        monkeypatch.setattr(loc, "write_state_file", MagicMock())
        monkeypatch.setattr(loc, "_teardown_network", MagicMock())
        # Controller path waits for workers before teardown; stub it out so
        # the test doesn't poll for PYTEST_XDIST_WORKER_COUNT or sleep.
        monkeypatch.setattr(loc, "wait_for_workers_done", MagicMock())

        gen = _docker_network_gen("samstack-gw0")
        next(gen)

        lock_acquire_spy.assert_called_once()
        lock_release_spy.assert_not_called()

        # Trigger teardown
        gen.close()

        lock_release_spy.assert_called_once()

    def test_writes_error_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw0 writes error key to state on network creation failure, re-raises."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.CONTROLLER)
        monkeypatch.setattr(loc, "infra_lock", _fake_lock_always_acquired())

        error_spy = MagicMock()
        monkeypatch.setattr(loc, "write_error_for", error_spy)
        monkeypatch.setattr(loc, "write_state_file", MagicMock())

        # Make _create_and_register_network fail
        monkeypatch.setattr(
            loc,
            "_create_and_register_network",
            MagicMock(side_effect=Exception("Docker error")),
        )

        gen = _docker_network_gen("samstack-hardfail")
        with pytest.raises(Exception, match="Docker error"):
            next(gen)

        error_spy.assert_called_with(
            StateKeys.DOCKER_NETWORK,
            "Docker network creation failed: samstack-hardfail",
        )


# ---------------------------------------------------------------------------
# TestDockerNetworkGw1
# ---------------------------------------------------------------------------


class TestDockerNetworkGw1:
    def test_yields_without_docker_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ polls shared state for the network name, yields it without Docker calls."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.WORKER)
        monkeypatch.setattr(
            loc,
            "wait_for_state_key",
            lambda key, timeout=120: "samstack-from-state",
        )

        # Mock Docker SDK to detect if it's called
        mock_client = MagicMock()
        monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: mock_client)

        # docker_network_name is "" for gw1+ — docker_network polls state itself
        gen = _docker_network_gen("")
        result = next(gen)
        assert result == "samstack-from-state"

        # Docker SDK must NOT be used
        mock_client.networks.create.assert_not_called()

    def test_no_teardown_on_gw1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ teardown does no Docker work; only writes worker_done marker."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.WORKER)
        monkeypatch.setattr(loc, "get_worker_id", lambda: "gw1")
        monkeypatch.setattr(
            loc,
            "wait_for_state_key",
            lambda key, timeout=120: "samstack-from-state",
        )

        mock_client = MagicMock()
        monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: mock_client)

        teardown_spy = MagicMock()
        monkeypatch.setattr(loc, "_teardown_network", teardown_spy)
        write_spy = MagicMock()
        monkeypatch.setattr(loc, "write_state_file", write_spy)

        gen = _docker_network_gen("")
        result = next(gen)
        assert result == "samstack-from-state"

        # Trigger teardown
        gen.close()

        teardown_spy.assert_not_called()
        # Worker now signals completion so the controller can safely tear
        # down shared infra (LocalStack, sam_api, sam_lambda_endpoint).
        write_spy.assert_called_once_with(StateKeys.worker_done("gw1"), True)

    def test_fails_on_error_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ raises pytest.fail.Exception when gw0 wrote an error to state."""
        monkeypatch.setattr(loc, "worker_role", lambda: Role.WORKER)
        monkeypatch.setattr(
            loc,
            "wait_for_state_key",
            lambda key, timeout=120: pytest.fail(
                "gw0 infrastructure startup failed: boom"
            ),
        )

        gen = _docker_network_gen("")
        with pytest.raises(pytest.fail.Exception, match="boom"):
            next(gen)

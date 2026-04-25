from __future__ import annotations

from collections.abc import Callable, Iterator
from unittest.mock import MagicMock, patch

import pytest

import samstack.fixtures.localstack as loc
from testcontainers.core.labels import LABEL_SESSION_ID, SESSION_ID

# pytest fixtures are typed as FixtureFunctionDefinition by ty, but
# __wrapped__ (the raw generator function) is accessible at runtime.
# Use getattr to avoid ty's static type check on the attribute.
_docker_network: Callable[[str], Iterator[str]] = getattr(
    loc.docker_network, "__wrapped__"
)


@pytest.fixture
def mock_docker_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch docker.from_env() to return a MagicMock client."""
    client = MagicMock()
    network = MagicMock()
    network.name = "samstack-test"
    client.networks.create.return_value = network
    monkeypatch.setattr(loc.docker_sdk, "from_env", lambda: client)
    return client


class TestDockerNetworkRyukEnabled:
    """Ryuk is enabled (ryuk_disabled=False)."""

    def test_network_created_with_session_id_label(
        self,
        mock_docker_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """TEST-01: network carries org.testcontainers.session-id label."""
        monkeypatch.setattr(loc.testcontainers_config, "ryuk_disabled", False)
        mock_socket = MagicMock()

        with (
            patch.object(loc.Reaper, "get_instance"),
            patch.object(loc.Reaper, "_socket", mock_socket, create=True),
        ):
            gen = _docker_network("samstack-test")
            next(gen)

        mock_docker_client.networks.create.assert_called_once_with(
            "samstack-test",
            driver="bridge",
            labels={LABEL_SESSION_ID: SESSION_ID},
        )

    def test_reaper_get_instance_called(
        self,
        mock_docker_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reaper.get_instance() is called to ensure Ryuk exists."""
        monkeypatch.setattr(loc.testcontainers_config, "ryuk_disabled", False)

        with patch.object(loc.Reaper, "get_instance") as mock_get_instance:
            gen = _docker_network("samstack-test")
            next(gen)

        mock_get_instance.assert_called_once()


class TestDockerNetworkRyukDisabled:
    """Ryuk is disabled (ryuk_disabled=True)."""

    def test_reaper_not_called_when_ryuk_disabled(
        self,
        mock_docker_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """TEST-02: when ryuk_disabled=True, Reaper.get_instance is never called."""
        monkeypatch.setattr(loc.testcontainers_config, "ryuk_disabled", True)

        with patch.object(loc.Reaper, "get_instance") as mock_get_instance:
            gen = _docker_network("samstack-test")
            next(gen)

        mock_get_instance.assert_not_called()

    def test_network_still_created_with_label_when_ryuk_disabled(
        self,
        mock_docker_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Label is always injected regardless of ryuk_disabled."""
        monkeypatch.setattr(loc.testcontainers_config, "ryuk_disabled", True)

        gen = _docker_network("samstack-test")
        next(gen)

        mock_docker_client.networks.create.assert_called_once_with(
            "samstack-test",
            driver="bridge",
            labels={LABEL_SESSION_ID: SESSION_ID},
        )

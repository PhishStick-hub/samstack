from __future__ import annotations

import contextlib
import warnings
from collections.abc import Iterator
from typing import TYPE_CHECKING
from uuid import uuid4

import docker as docker_sdk
import pytest
from testcontainers.localstack import LocalStackContainer

from samstack._errors import DockerNetworkError, LocalStackStartupError
from samstack._process import stream_logs_to_file
from samstack.fixtures._sam_container import (
    DOCKER_SOCKET,
    _connect_container_with_alias,
    _disconnect_container_from_network,
)
from samstack.settings import SamStackSettings

if TYPE_CHECKING:
    import docker.models.containers
    import docker.models.networks


# — Docker network ----------------------------------------------------------------


def _stop_network_container(
    network: docker_sdk.models.networks.Network,
    container: docker_sdk.models.containers.Container,
) -> None:
    try:
        container.stop(timeout=5)
        container.remove(force=True)
    except Exception as exc:
        warnings.warn(
            f"samstack: failed to stop container during network teardown: {exc}",
            stacklevel=2,
        )
        with contextlib.suppress(Exception):
            network.disconnect(container, force=True)


def _teardown_network(network: docker_sdk.models.networks.Network, name: str) -> None:
    try:
        network.reload()
        for container in network.containers:
            _stop_network_container(network, container)
        network.remove()
    except Exception as exc:
        warnings.warn(
            f"samstack: failed to clean up Docker network '{name}': {exc}",
            stacklevel=2,
        )


@pytest.fixture(scope="session")
def docker_network_name() -> str:
    """Return the name for the shared Docker bridge network.

    Override this fixture to use a fixed or externally-managed network name.
    """
    return f"samstack-{uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def docker_network(docker_network_name: str) -> Iterator[str]:
    """Create a Docker bridge network shared by LocalStack and SAM containers."""
    client = docker_sdk.from_env()
    try:
        network = client.networks.create(docker_network_name, driver="bridge")
    except Exception as exc:
        raise DockerNetworkError(name=docker_network_name, reason=str(exc)) from exc
    try:
        yield docker_network_name
    finally:
        _teardown_network(network, docker_network_name)


# — LocalStack container -------------------------------------------------------


@pytest.fixture(scope="session")
def localstack_container(
    samstack_settings: SamStackSettings,
    docker_network: str,
) -> Iterator[LocalStackContainer]:
    """Start LocalStack and connect it to the shared Docker network."""
    container = LocalStackContainer(image=samstack_settings.localstack_image)
    container.with_volume_mapping(DOCKER_SOCKET, DOCKER_SOCKET, "rw")
    container.start()

    log_dir = samstack_settings.project_root / samstack_settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    inner = container.get_wrapped_container()
    if inner is None:
        container.stop()
        raise LocalStackStartupError(log_tail="container exited before start")
    stream_logs_to_file(inner, log_dir / "localstack.log")

    client = docker_sdk.from_env()
    try:
        _connect_container_with_alias(client, docker_network, container, "localstack")
    except Exception as exc:
        container.stop()
        raise DockerNetworkError(name=docker_network, reason=str(exc)) from exc

    try:
        yield container
    finally:
        try:
            _disconnect_container_from_network(client, docker_network, container)
        except Exception as exc:
            warnings.warn(
                f"samstack: failed to disconnect LocalStack from network '{docker_network}': {exc}",
                stacklevel=2,
            )
        container.stop()


@pytest.fixture(scope="session")
def localstack_endpoint(localstack_container: LocalStackContainer) -> str:
    """Return the host-accessible LocalStack URL for use in boto3 clients."""
    return localstack_container.get_url()

from __future__ import annotations

import warnings
from collections.abc import Iterator
from uuid import uuid4

import docker as docker_sdk
import pytest
from testcontainers.localstack import LocalStackContainer

from samstack._errors import DockerNetworkError
from samstack.fixtures._sam_container import DOCKER_SOCKET
from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def docker_network_name() -> str:
    """Return the name for the shared Docker bridge network.

    Override this fixture to use a fixed or externally-managed network name.
    """
    return f"samstack-{uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def docker_network(docker_network_name: str) -> Iterator[str]:
    """Create a Docker bridge network shared by LocalStack and SAM containers."""
    name = docker_network_name
    client = docker_sdk.from_env()
    try:
        network = client.networks.create(name, driver="bridge")
    except Exception as exc:
        raise DockerNetworkError(name=name, reason=str(exc)) from exc
    try:
        yield name
    finally:
        try:
            network.reload()
            for container in network.containers:
                try:
                    container.stop(timeout=5)
                    container.remove(force=True)
                except Exception:
                    network.disconnect(container, force=True)
            network.remove()
        except Exception as exc:
            warnings.warn(
                f"samstack: failed to clean up Docker network '{name}': {exc}",
                stacklevel=1,
            )


@pytest.fixture(scope="session")
def localstack_container(
    samstack_settings: SamStackSettings,
    docker_network: str,
) -> Iterator[LocalStackContainer]:
    """Start LocalStack and connect it to the shared Docker network."""
    container = LocalStackContainer(image=samstack_settings.localstack_image)
    container.with_volume_mapping(DOCKER_SOCKET, DOCKER_SOCKET, "rw")
    container.start()

    client = docker_sdk.from_env()
    try:
        network = client.networks.get(docker_network)
        inner = container.get_wrapped_container()
        assert inner is not None, "LocalStack container failed to start"
        network.connect(inner.id, aliases=["localstack"])
    except Exception as exc:
        container.stop()
        raise DockerNetworkError(name=docker_network, reason=str(exc)) from exc

    try:
        yield container
    finally:
        try:
            network = client.networks.get(docker_network)
            inner = container.get_wrapped_container()
            if inner is not None:
                network.disconnect(inner.id, force=True)
        except Exception as exc:
            warnings.warn(
                f"samstack: failed to disconnect LocalStack from network '{docker_network}': {exc}",
                stacklevel=1,
            )
        container.stop()


@pytest.fixture(scope="session")
def localstack_endpoint(localstack_container: LocalStackContainer) -> str:
    """Return the host-accessible LocalStack URL for use in boto3 clients."""
    return localstack_container.get_url()

from __future__ import annotations

import contextlib
import warnings
from collections.abc import Iterator
from typing import TYPE_CHECKING
from uuid import uuid4

import docker as docker_sdk
import pytest
from testcontainers.core.config import testcontainers_config
from testcontainers.core.container import Reaper
from testcontainers.core.labels import LABEL_SESSION_ID, SESSION_ID
from testcontainers.localstack import LocalStackContainer

from samstack._errors import DockerNetworkError, LocalStackStartupError
from samstack._process import stream_logs_to_file
from samstack._xdist import (
    Role,
    StateKeys,
    acquire_infra_lock,
    get_worker_id,
    release_infra_lock,
    wait_for_state_key,
    wait_for_workers_done,
    worker_role,
    write_error_for,
    write_state_file,
)
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


def _create_and_register_network(name: str) -> docker_sdk.models.networks.Network:
    """Create a Docker bridge network and register with Ryuk if enabled."""
    client = docker_sdk.from_env()
    try:
        network = client.networks.create(
            name,
            driver="bridge",
            labels={LABEL_SESSION_ID: SESSION_ID},
        )
    except Exception as exc:
        raise DockerNetworkError(name=name, reason=str(exc)) from exc
    if not testcontainers_config.ryuk_disabled:
        Reaper.get_instance()
    return network


@pytest.fixture(scope="session")
def docker_network_name(request: pytest.FixtureRequest) -> str:
    """Return the name for the shared Docker bridge network.

    Override this fixture to use a fixed or externally-managed network name.
    Under xdist: gw0/master generates a UUID name; gw1+ returns an empty
    string — the real name is resolved inside ``docker_network`` by polling
    shared state, making the coordination dependency explicit there.
    """
    if worker_role() is not Role.WORKER:
        return f"samstack-{uuid4().hex[:8]}"
    # Workers (gw1+) do not generate a name; docker_network polls shared state.
    return ""


@pytest.fixture(scope="session")
def docker_network(docker_network_name: str) -> Iterator[str]:
    """Create a Docker bridge network shared by LocalStack and SAM containers.

    Under xdist: the controller (gw0) creates the network and writes its name
    to shared state; workers (gw1+) read the name and proxy.

    Teardown coordination is owned by each controller-owned shared resource
    (``localstack_container``, ``sam_api``, ``sam_lambda_endpoint``) — those
    fixtures call :func:`wait_for_workers_done` BEFORE stopping their
    containers. This fixture deliberately does not wait, because pytest
    finalises in LIFO order: ``docker_network`` runs *after* its dependents,
    by which time those containers are already gone.
    """
    role = worker_role()

    # === Worker path: wait for controller to create the network, then proxy ===
    if role is Role.WORKER:
        resolved_name = wait_for_state_key(StateKeys.DOCKER_NETWORK, timeout=120)
        try:
            yield resolved_name
        finally:
            # Signal completion so controllers waiting in their own teardowns
            # (localstack_container, sam_api, sam_lambda_endpoint) can proceed.
            with contextlib.suppress(Exception):
                write_state_file(StateKeys.worker_done(get_worker_id()), True)
        return

    # === Master / controller path: create Docker infrastructure ===
    if role is Role.CONTROLLER:
        if not acquire_infra_lock():
            pytest.fail(
                "gw0 failed to acquire infrastructure lock — "
                "another process may already hold it. "
                "This should not happen under normal xdist operation."
            )
        try:
            network = _create_and_register_network(docker_network_name)
            write_state_file(StateKeys.DOCKER_NETWORK, docker_network_name)
        except Exception:
            write_error_for(
                StateKeys.DOCKER_NETWORK,
                f"Docker network creation failed: {docker_network_name}",
            )
            release_infra_lock()
            raise
    else:
        # MASTER (no xdist) — existing behavior, no state file needed
        network = _create_and_register_network(docker_network_name)

    try:
        yield docker_network_name
    finally:
        try:
            _teardown_network(network, docker_network_name)
        finally:
            if role is Role.CONTROLLER:
                release_infra_lock()


# — LocalStack container -------------------------------------------------------


class _LocalStackContainerProxy:
    """Lightweight proxy that mimics LocalStackContainer.get_url() on gw1+ workers.

    gw1+ workers do not start their own LocalStack container. Instead, they
    wait for gw0 to write the shared endpoint to the state file. This proxy
    satisfies the `localstack_container` fixture dependency on gw1+ so that
    downstream fixtures (localstack_endpoint, boto3 clients) work unchanged.
    """

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint

    def get_url(self) -> str:
        return self._endpoint

    def get_wrapped_container(self) -> None:
        """gw1+ has no Docker container — always returns None."""
        return None

    def stop(self) -> None:
        """No-op — workers don't own the container, controller stops it."""
        return None


@pytest.fixture(scope="session")
def localstack_container(
    samstack_settings: SamStackSettings,
    docker_network: str,
) -> Iterator[LocalStackContainer | _LocalStackContainerProxy]:
    """Start LocalStack and connect it to the shared Docker network.

    Under xdist: the controller starts LocalStack and writes its endpoint
    to shared state; workers wait for the endpoint and yield a lightweight
    proxy without any Docker API calls.

    Teardown ordering: pytest finalises session-scoped fixtures in LIFO
    order, so this fixture tears down BEFORE its dependency
    ``docker_network``. To prevent stopping LocalStack while workers are
    still mid-test (their resource fixtures' per-test teardowns hit S3/
    DynamoDB/SQS through this LocalStack), the CONTROLLER blocks on
    :func:`wait_for_workers_done` inside its own teardown before stopping
    the container. ``sam_api`` and ``sam_lambda_endpoint`` apply the same
    pattern via ``xdist_shared_session(wait_for_workers_on_teardown=True)``.
    """
    role = worker_role()

    # === Worker path: wait for controller, yield proxy, no Docker ===
    if role is Role.WORKER:
        endpoint = wait_for_state_key(StateKeys.LOCALSTACK_ENDPOINT, timeout=120)
        yield _LocalStackContainerProxy(endpoint)
        return

    # === Master / controller path: create and start LocalStack ===
    container = LocalStackContainer(image=samstack_settings.localstack_image)
    container.with_volume_mapping(DOCKER_SOCKET, DOCKER_SOCKET, "rw")

    try:
        container.start()
    except Exception:
        if role is Role.CONTROLLER:
            write_error_for(
                StateKeys.LOCALSTACK_ENDPOINT,
                "LocalStack container failed to start",
            )
        raise

    log_dir = samstack_settings.project_root / samstack_settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    inner = container.get_wrapped_container()
    if inner is None:
        container.stop()
        if role is Role.CONTROLLER:
            write_error_for(
                StateKeys.LOCALSTACK_ENDPOINT,
                "LocalStack container exited before start",
            )
        raise LocalStackStartupError(log_tail="container exited before start")
    stream_logs_to_file(inner, log_dir / "localstack.log")

    client = docker_sdk.from_env()
    try:
        _connect_container_with_alias(client, docker_network, container, "localstack")
    except Exception as exc:
        container.stop()
        if role is Role.CONTROLLER:
            write_error_for(
                StateKeys.LOCALSTACK_ENDPOINT,
                f"LocalStack network connection failed: {exc}",
            )
        raise DockerNetworkError(name=docker_network, reason=str(exc)) from exc

    if role is Role.CONTROLLER:
        write_state_file(StateKeys.LOCALSTACK_ENDPOINT, container.get_url())

    try:
        yield container
    finally:
        # Block teardown until every worker has signalled completion. Workers
        # use boto3 clients pointed at this LocalStack instance during their
        # own per-test teardown of resource fixtures (s3_bucket, dynamodb_table,
        # ...); stopping the container before they finish would surface as
        # ConnectionRefusedError during their session teardown.
        if role is Role.CONTROLLER:
            wait_for_workers_done()
        try:
            _disconnect_container_from_network(client, docker_network, container)
        except Exception as exc:
            warnings.warn(
                f"samstack: failed to disconnect LocalStack from network '{docker_network}': {exc}",
                stacklevel=2,
            )
        try:
            container.stop()
        except Exception as exc:
            warnings.warn(
                f"samstack: failed to stop LocalStack container: {exc}",
                stacklevel=2,
            )


@pytest.fixture(scope="session")
def localstack_endpoint(
    localstack_container: LocalStackContainer | _LocalStackContainerProxy,
) -> str:
    """Return the host-accessible LocalStack URL for use in boto3 clients."""
    return localstack_container.get_url()

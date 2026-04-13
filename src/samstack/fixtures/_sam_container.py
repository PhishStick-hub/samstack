from __future__ import annotations

import os
import platform
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from testcontainers.core.container import DockerContainer

from samstack._process import stream_logs_to_file, wait_for_http, wait_for_port
from samstack.settings import SamStackSettings

DOCKER_SOCKET = "/var/run/docker.sock"


def _is_ci() -> bool:
    """Return True when running inside a CI environment (GitHub Actions, GitLab CI, etc.)."""
    return bool(os.environ.get("CI"))


def _extra_hosts() -> dict[str, str]:
    """On Linux (no Docker Desktop), map host.docker.internal to the host gateway."""
    if platform.system() == "Darwin":
        return {}
    return {"host.docker.internal": "host-gateway"}


def build_sam_args(
    port: int,
    env_vars_host_path: str,
    docker_network: str,
    warm_containers: Literal["LAZY", "EAGER"],
    settings_extra_args: list[str],
    fixture_extra_args: list[str],
) -> list[str]:
    """Return the CLI arg list shared by start-api and start-lambda."""
    skip_pull: list[str] = [] if _is_ci() else ["--skip-pull-image"]
    return [
        *skip_pull,
        "--warm-containers",
        warm_containers,
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--env-vars",
        env_vars_host_path,
        "--docker-network",
        docker_network,
        "--container-host",
        "host.docker.internal",
        "--container-host-interface",
        "0.0.0.0",
        *settings_extra_args,
        *fixture_extra_args,
    ]


@contextmanager
def _run_sam_service(
    settings: SamStackSettings,
    docker_network: str,
    subcommand: Literal["start-api", "start-lambda"],
    port: int,
    warm_containers: Literal["LAZY", "EAGER"],
    settings_extra_args: list[str],
    fixture_extra_args: list[str],
    log_filename: str,
    wait_mode: Literal["http", "port"],
) -> Iterator[str]:
    """Start a `sam local <subcommand>` container and yield its endpoint URL."""
    log_dir = settings.project_root / settings.log_dir
    log_path = log_dir / log_filename
    host_path = str(settings.project_root)
    env_vars_host_path = str(log_dir / "env_vars.json")

    args = build_sam_args(
        port=port,
        env_vars_host_path=env_vars_host_path,
        docker_network=docker_network,
        warm_containers=warm_containers,
        settings_extra_args=settings_extra_args,
        fixture_extra_args=fixture_extra_args,
    )
    command = ["sam", "local", subcommand, "--template", settings.template, *args]

    container = create_sam_container(
        settings=settings,
        docker_network=docker_network,
        host_path=host_path,
        port=port,
        command=command,
    )
    container.start()
    inner = container.get_wrapped_container()
    assert inner is not None, "SAM container failed to start"
    stream_logs_to_file(inner, log_path)

    host_port = int(container.get_exposed_port(port))
    if wait_mode == "http":
        wait_for_http("127.0.0.1", host_port, log_path=log_path, timeout=120.0)
    else:
        wait_for_port("127.0.0.1", host_port, log_path=log_path, timeout=120.0)

    try:
        yield f"http://127.0.0.1:{host_port}"
    finally:
        container.stop()


def create_sam_container(
    settings: SamStackSettings,
    docker_network: str,
    host_path: str,
    port: int,
    command: list[str],
) -> DockerContainer:
    """Build a DockerContainer for `sam local start-*` with all standard mounts and env."""
    return (
        DockerContainer(settings.sam_image)
        .with_kwargs(
            network=docker_network,
            extra_hosts=_extra_hosts(),
            working_dir=host_path,
        )
        .with_volume_mapping(host_path, host_path, "rw")
        .with_volume_mapping(DOCKER_SOCKET, DOCKER_SOCKET, "rw")
        .with_exposed_ports(port)
        .with_env("SAM_CLI_CONTAINER_CONNECTION_TIMEOUT", "60")
        .with_env("DOCKER_DEFAULT_PLATFORM", settings.docker_platform)
        .with_command(command)
    )

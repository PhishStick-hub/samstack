from __future__ import annotations

from typing import Any

import docker as docker_sdk


def run_one_shot_container(
    image: str,
    command: str | list[str],
    volumes: dict[str, dict[str, str]],
    working_dir: str = "/var/task",
    network: str | None = None,
    environment: dict[str, str] | None = None,
) -> tuple[str, int]:
    """Run a container to completion. Returns (logs, exit_code)."""
    client = docker_sdk.from_env()
    kwargs: dict[str, Any] = {"network": network} if network else {}
    if environment:
        kwargs["environment"] = environment
    container = client.containers.run(
        image=image,
        command=command,
        volumes=volumes,
        working_dir=working_dir,
        detach=True,
        **kwargs,
    )
    try:
        result = container.wait()
        logs = container.logs().decode(errors="replace")
        return logs, result["StatusCode"]
    finally:
        container.remove(force=True)

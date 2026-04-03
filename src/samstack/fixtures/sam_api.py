from __future__ import annotations

from collections.abc import Iterator

import pytest

from samstack.fixtures._sam_container import _run_sam_service
from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def sam_api_extra_args() -> list[str]:
    """
    Extra CLI args appended to `sam local start-api` after the defaults.

    Override in your conftest.py:

        @pytest.fixture(scope="session")
        def sam_api_extra_args() -> list[str]:
            return ["--debug"]
    """
    return []


@pytest.fixture(scope="session")
def sam_api(
    samstack_settings: SamStackSettings,
    sam_build: None,
    docker_network: str,
    sam_api_extra_args: list[str],
) -> Iterator[str]:
    """
    Start `sam local start-api` in Docker. Yields base URL http://127.0.0.1:{api_port}.
    Logs written to {log_dir}/start-api.log.
    """
    with _run_sam_service(
        settings=samstack_settings,
        docker_network=docker_network,
        subcommand="start-api",
        port=samstack_settings.api_port,
        warm_containers="LAZY",
        settings_extra_args=samstack_settings.start_api_args,
        fixture_extra_args=sam_api_extra_args,
        log_filename="start-api.log",
        wait_mode="http",
    ) as endpoint:
        yield endpoint

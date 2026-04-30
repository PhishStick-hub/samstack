from __future__ import annotations

import contextlib
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator

import pytest

from samstack._errors import SamStartupError
from samstack._xdist import (
    get_worker_id,
    is_controller,
    wait_for_state_key,
    write_state_file,
)
from samstack.fixtures._sam_container import _run_sam_service
from samstack.settings import SamStackSettings

_logger = logging.getLogger("samstack")


def _filter_warm_routes(
    warm_api_routes: dict[str, str],
    warm_functions: list[str],
) -> dict[str, str]:
    return {k: v for k, v in warm_api_routes.items() if k in warm_functions}


def _pre_warm_api_routes(
    endpoint: str,
    routes: dict[str, str],
) -> None:
    """Send a synthetic GET to each API route to ensure warm containers are ready.

    Prints a summary to stderr, then sends GET requests sequentially.
    Any HTTP response (2xx, 4xx, 5xx) counts as success — only connection-level
    errors (timeout, refused, DNS) raise ``SamStartupError``.
    """
    if not routes:
        return

    _logger.info("pre-warming %d API route(s)", len(routes))
    for func_name, path in routes.items():
        url = f"{endpoint}{path}"
        try:
            with contextlib.closing(urllib.request.urlopen(url, timeout=10.0)):  # noqa: S310
                pass
        except urllib.error.HTTPError:
            pass
        except (urllib.error.URLError, OSError) as exc:
            raise SamStartupError(
                port=0,
                log_tail=f"Pre-warm HTTP request failed for function "
                f"'{func_name}' ({url}): {exc}",
            ) from exc


@pytest.fixture(scope="session")
def warm_api_routes() -> dict[str, str]:
    """
    Mapping of Lambda function names to API route paths for HTTP pre-warming.

    Only functions present in BOTH ``warm_functions`` AND ``warm_api_routes``
    receive synthetic HTTP GET requests before the first test runs. A function
    in ``warm_api_routes`` but not ``warm_functions`` is ignored.

    Override in your conftest.py:

        @pytest.fixture(scope="session")
        def warm_api_routes() -> dict[str, str]:
            return {"HelloWorldFunction": "/hello"}

    Values are route paths only (e.g., ``"/hello"``), not full URLs. The
    ``sam_api`` endpoint URL is prepended at request time.
    """
    return {}


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
    warm_functions: list[str],
    warm_api_routes: dict[str, str],
) -> Iterator[str]:
    """Start `sam local start-api` in Docker. Yields base URL http://127.0.0.1:{api_port}.

    Under xdist: gw0 starts the container and writes the endpoint to shared state;
    gw1+ workers poll for the endpoint and yield it without any Docker calls.
    Logs written to {log_dir}/start-api.log.
    """
    worker_id = get_worker_id()

    # === gw1+ path: wait for gw0, yield URL, no Docker ===
    if not is_controller(worker_id):
        endpoint = wait_for_state_key("sam_api_endpoint", timeout=120)
        yield endpoint
        return

    # === gw0 / master path: start container + pre-warm ===
    try:
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
            network_alias="sam-api",
        ) as endpoint:
            _pre_warm_api_routes(
                endpoint,
                _filter_warm_routes(warm_api_routes, warm_functions),
            )
            if worker_id == "gw0":
                write_state_file("sam_api_endpoint", endpoint)
            yield endpoint
    except Exception as exc:
        if worker_id == "gw0":
            write_state_file(
                "error",
                f"sam_api container failed to start: {exc}",
            )
        raise

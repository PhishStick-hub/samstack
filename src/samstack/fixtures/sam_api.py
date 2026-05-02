from __future__ import annotations

import contextlib
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from samstack._errors import SamStartupError
from samstack._xdist import StateKeys, xdist_shared_session
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
    sam_lambda_endpoint: str,
    sam_api_extra_args: list[str],
    warm_functions: list[str],
    warm_api_routes: dict[str, str],
) -> Iterator[str]:
    """Start `sam local start-lambda` and `start-api` in Docker.

    Yields base URL http://127.0.0.1:{api_port}.

    Depends on ``sam_lambda_endpoint`` so the Lambda runtime is always started
    alongside the API gateway. This ensures gw0 writes both endpoints to shared
    state even when its test allocation only covers API tests — gw1+ workers
    that need ``lambda_client`` can still resolve it.

    Under xdist: gw0 starts the containers and writes endpoints to shared state;
    gw1+ workers poll for the endpoints and yield them without any Docker calls.
    Logs written to {log_dir}/start-api.log and {log_dir}/start-lambda.log.
    """

    @contextmanager
    def _on_controller() -> Iterator[tuple[str, str]]:
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
            yield endpoint, endpoint

    with xdist_shared_session(
        StateKeys.SAM_API_ENDPOINT,
        on_controller=_on_controller,
        error_prefix="sam_api container failed to start",
        wait_for_workers_on_teardown=True,
    ) as endpoint:
        yield endpoint

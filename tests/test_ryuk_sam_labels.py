"""Integration test: verifies SAM API and SAM Lambda containers carry the Ryuk session label.

Tests that both SAM container fixtures receive the org.testcontainers.session-id label
automatically via DockerContainer.start(), making them eligible for Ryuk cleanup.
Uses Docker SDK label query (key-only, not value) to locate containers without
requiring direct container handles — works under xdist where each worker has a
different SESSION_ID than the controller that created the containers.

Must run in the tests/ top-level session where sam_api and sam_lambda_endpoint fixtures
are active. The tests/integration/ session does not start SAM containers.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
import docker
from testcontainers.core.config import testcontainers_config
from testcontainers.core.labels import LABEL_SESSION_ID

if TYPE_CHECKING:
    import docker.models.containers

UUID_PATTERN = re.compile(r"^[0-9a-f-]{36}$", re.I)

pytestmark = pytest.mark.skipif(
    testcontainers_config.ryuk_disabled,
    reason="Ryuk label verification requires Ryuk active",
)


def _find_sam_containers_by_subcommand(
    docker_client: docker.DockerClient, subcommand: str
) -> list[docker.models.containers.Container]:
    """Return session-labeled containers whose command includes the given SAM subcommand.

    Filters by label key existence only (not value) so the lookup works under
    xdist: SAM containers are labeled with the controller's SESSION_ID, which
    differs from each worker's local SESSION_ID.
    """
    labeled = docker_client.containers.list(filters={"label": LABEL_SESSION_ID})
    return [
        c for c in labeled if subcommand in (c.attrs.get("Config", {}).get("Cmd") or [])
    ]


class TestSamApiRyukLabel:
    def test_sam_api_container_has_session_label(self, sam_api: str) -> None:
        """SAM API container carries org.testcontainers.session-id after start-api is running."""
        if testcontainers_config.ryuk_disabled:
            pytest.skip("Ryuk disabled — label check not meaningful")

        # sam_api fixture ensures start-api container is running before this test executes.
        docker_client = docker.from_env()
        matching = _find_sam_containers_by_subcommand(docker_client, "start-api")

        assert matching, (
            "No session-labeled container with 'start-api' in command found. "
            "Ensure sam_api fixture is active and the container started successfully."
        )
        # Spot-check: every found container must carry the correct label value.
        for container in matching:
            label_value = container.labels.get(LABEL_SESSION_ID, "")
            assert UUID_PATTERN.match(label_value), (
                f"Container '{container.name}' label '{LABEL_SESSION_ID}'={label_value!r} "
                "is not a valid UUID"
            )


class TestSamLambdaRyukLabel:
    def test_sam_lambda_container_has_session_label(
        self, sam_lambda_endpoint: str
    ) -> None:
        """SAM Lambda container carries org.testcontainers.session-id after start-lambda is running."""
        if testcontainers_config.ryuk_disabled:
            pytest.skip("Ryuk disabled — label check not meaningful")

        # sam_lambda_endpoint fixture ensures start-lambda container is running.
        docker_client = docker.from_env()
        matching = _find_sam_containers_by_subcommand(docker_client, "start-lambda")

        assert matching, (
            "No session-labeled container with 'start-lambda' in command found. "
            "Ensure sam_lambda_endpoint fixture is active and the container started successfully."
        )
        for container in matching:
            label_value = container.labels.get(LABEL_SESSION_ID, "")
            assert UUID_PATTERN.match(label_value), (
                f"Container '{container.name}' label '{LABEL_SESSION_ID}'={label_value!r} "
                "is not a valid UUID"
            )

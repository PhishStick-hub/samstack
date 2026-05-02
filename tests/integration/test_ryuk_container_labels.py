"""Integration test: verifies LocalStack container carries the Ryuk session label.

Tests that LocalStack container fixture receives the org.testcontainers.session-id
label automatically via DockerContainer.start(), making it eligible for Ryuk cleanup.
Label inspection only — no crash or cleanup cycle (see test_ryuk_crash.py for that).
"""

from __future__ import annotations

import re

import docker as docker_sdk
import pytest
from testcontainers.core.config import testcontainers_config
from testcontainers.core.labels import LABEL_SESSION_ID
from testcontainers.localstack import LocalStackContainer

UUID_PATTERN = re.compile(r"^[0-9a-f-]{36}$", re.I)

# Skip the entire module when Ryuk is disabled (CI environments where
# TESTCONTAINERS_RYUK_DISABLED=true). Label checks only need Ryuk active
# to be meaningful — the label itself is always written, but verifying it
# without Ryuk active confirms nothing about cleanup eligibility.
pytestmark = pytest.mark.skipif(
    testcontainers_config.ryuk_disabled,
    reason="Ryuk label verification requires Ryuk active",
)


class TestLocalStackRyukLabel:
    def test_localstack_container_has_session_label(
        self, localstack_container: LocalStackContainer
    ) -> None:
        """LocalStack container carries org.testcontainers.session-id after .start()."""
        if testcontainers_config.ryuk_disabled:
            pytest.skip("Ryuk disabled — label check not meaningful")

        inner = localstack_container.get_wrapped_container()
        if inner is None:
            # Under xdist workers the fixture is a proxy without a Docker handle.
            # Fall back to the Docker SDK: find the running LocalStack container.
            client = docker_sdk.from_env()
            candidates = [
                c
                for c in client.containers.list()
                if "localstack" in (c.attrs.get("Config", {}).get("Image") or "")
            ]
            assert candidates, (
                "No running LocalStack container found via Docker SDK. "
                "Ensure localstack_container fixture is active."
            )
            inner = candidates[0]

        inner.reload()
        labels = inner.labels

        assert LABEL_SESSION_ID in labels, (
            f"LocalStack container is missing label '{LABEL_SESSION_ID}'. "
            f"Present labels: {list(labels.keys())}"
        )
        label = labels[LABEL_SESSION_ID]
        assert UUID_PATTERN.match(label), (
            f"Label '{LABEL_SESSION_ID}' value {label!r} is not a valid UUID"
        )

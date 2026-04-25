"""Integration test: verifies LocalStack container carries the Ryuk session label.

Tests that LocalStack container fixture receives the org.testcontainers.session-id
label automatically via DockerContainer.start(), making it eligible for Ryuk cleanup.
Label inspection only — no crash or cleanup cycle (see test_ryuk_crash.py for that).
"""

from __future__ import annotations

import pytest
from testcontainers.core.config import testcontainers_config
from testcontainers.core.labels import LABEL_SESSION_ID, SESSION_ID
from testcontainers.localstack import LocalStackContainer


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
        assert inner is not None, (
            "localstack_container.get_wrapped_container() returned None — "
            "container did not start correctly"
        )
        inner.reload()
        labels = inner.labels

        assert LABEL_SESSION_ID in labels, (
            f"LocalStack container is missing label '{LABEL_SESSION_ID}'. "
            f"Present labels: {list(labels.keys())}"
        )
        assert labels[LABEL_SESSION_ID] == SESSION_ID, (
            f"Label value mismatch. Expected '{SESSION_ID}', got '{labels[LABEL_SESSION_ID]}'"
        )

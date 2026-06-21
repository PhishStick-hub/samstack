"""Integration test: verifies Floci container carries the Ryuk session label.

Tests that Floci container fixture receives the org.testcontainers.session-id
label automatically via DockerContainer.start(), making it eligible for Ryuk cleanup.
Label inspection only — no crash or cleanup cycle (see test_ryuk_crash.py for that).
"""

from __future__ import annotations

import pytest
from floci import FlociContainer
from testcontainers.core.config import testcontainers_config
from testcontainers.core.labels import LABEL_SESSION_ID, SESSION_ID


# Skip the entire module when Ryuk is disabled (CI environments where
# TESTCONTAINERS_RYUK_DISABLED=true). Label checks only need Ryuk active
# to be meaningful — the label itself is always written, but verifying it
# without Ryuk active confirms nothing about cleanup eligibility.
pytestmark = pytest.mark.skipif(
    testcontainers_config.ryuk_disabled,
    reason="Ryuk label verification requires Ryuk active",
)


class TestFlociRyukLabel:
    def test_floci_container_has_session_label(
        self, floci_container: FlociContainer
    ) -> None:
        """Floci container carries org.testcontainers.session-id after .start()."""
        if testcontainers_config.ryuk_disabled:
            pytest.skip("Ryuk disabled — label check not meaningful")

        inner = floci_container.get_wrapped_container()
        assert inner is not None, (
            "floci_container.get_wrapped_container() returned None — "
            "container did not start correctly"
        )
        inner.reload()
        labels = inner.labels

        assert LABEL_SESSION_ID in labels, (
            f"Floci container is missing label '{LABEL_SESSION_ID}'. "
            f"Present labels: {list(labels.keys())}"
        )
        assert labels[LABEL_SESSION_ID] == SESSION_ID, (
            f"Label value mismatch. Expected '{SESSION_ID}', got '{labels[LABEL_SESSION_ID]}'"
        )

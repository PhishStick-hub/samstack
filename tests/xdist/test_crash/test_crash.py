"""Crash recovery integration test (TEST-02).

Verifies that when gw0's Docker infrastructure fails to start,
gw1+ workers exit cleanly with pytest.fail() instead of hanging
or producing Docker API error spew.

Pattern: launch pytest -n 2 subprocess pointing at the crash
conftest, capture output, assert clean exit within timeout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from testcontainers.core.config import testcontainers_config

# Skip on macOS — Docker Desktop's TCP proxy interferes with crash detection
pytestmark = pytest.mark.skipif(
    testcontainers_config.ryuk_disabled or sys.platform == "darwin",
    reason="Crash recovery verification requires Ryuk on Linux",
)

CRASH_SUITE_DIR = Path(__file__).parent


class TestXdistCrashRecovery:
    """Launch -n 2 with crash conftest, verify gw0 failure → gw1+ clean exit."""

    def test_gw1_exits_cleanly_after_gw0_failure(self) -> None:
        """Launch crash suite with -n 2, assert non-zero exit with fail message."""
        timeout = 120

        # Use -k to avoid recursing into this test file itself
        proc = subprocess.Popen(
            [
                "uv",
                "run",
                "pytest",
                str(CRASH_SUITE_DIR),
                "-n",
                "2",
                "--timeout",
                str(timeout),
                "-v",
                "-k",
                "test_trigger_docker_infra",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            stdout, _ = proc.communicate(timeout=timeout + 30)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, _ = proc.communicate()
            pytest.fail(
                f"Crash subprocess timed out after {timeout + 30}s — "
                f"gw1+ may have hung waiting for gw0. Output:\n{stdout[-2000:]}"
            )

        # Crash suite SHOULD fail (gw0 can't start)
        assert proc.returncode != 0, (
            f"Expected non-zero exit from crash subprocess, got {proc.returncode}. "
            f"Output:\n{stdout[-2000:]}"
        )

        # Must contain a failure indicator (fail/skip/error message)
        output_lower = stdout.lower()
        assert (
            "infrastructure startup failed" in output_lower
            or "gw0 infrastructure" in output_lower
            or "failed" in output_lower
        ), f"Expected fail message in crash output, got:\n{stdout[-2000:]}"

        # Must NOT contain Docker API errors (sign of unclean exit)
        assert "docker.errors" not in stdout, (
            f"Docker API errors found in crash output (unclean exit):\n{stdout[-2000:]}"
        )
        assert "connection refused" not in output_lower, (
            f"Connection errors in crash output (unclean exit):\n{stdout[-2000:]}"
        )

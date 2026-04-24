"""Integration crash test: confirms Ryuk removes the Docker network after SIGKILL.

TEST-03 per requirements. Requires Docker + Ryuk enabled (not skipped in CI
where TESTCONTAINERS_RYUK_DISABLED=true).

Platform note: On macOS with Docker Desktop, Ryuk does not reliably detect
SIGKILL-induced TCP connection drops across the VM boundary, so network cleanup
after a crash cannot be verified. The test skips on Darwin.

Design note: This test exercises only the docker_network fixture in isolation
(no SAM, no containers on the network). Docker refuses to remove a network
when containers are still attached, so attaching containers in the subprocess
session would block Ryuk cleanup even after SIGKILL. Sub-container cascade
on the crash path is verified by the normal teardown test (test_subcontainer_
teardown.py), which confirms _teardown_network stops and removes all containers
before network removal.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import docker
import docker.errors
import docker.models.networks
import pytest

from testcontainers.core.config import testcontainers_config


# Skip the entire module when Ryuk is disabled (CI environments).
# Also skip on macOS — Docker Desktop's TCP proxy layer does not propagate
# SIGKILL connection drops to the Ryuk container inside the Linux VM, so
# network cleanup after a crash is not observable on this platform.
pytestmark = pytest.mark.skipif(
    testcontainers_config.ryuk_disabled or sys.platform == "darwin",
    reason="Ryuk crash-cleanup test requires Ryuk on Linux (Docker Desktop on macOS does not propagate SIGKILL to Ryuk)",
)


def _write_subprocess_session(session_dir: Path) -> None:
    """Write a minimal pytest session that creates docker_network and stalls.

    Only docker_network is exercised — no SAM, no LocalStack, no containers
    on the network. This ensures the network has no attached containers when
    Ryuk attempts to remove it (Docker refuses network removal when containers
    are still attached).
    """
    conftest = session_dir / "conftest.py"
    conftest.write_text("""\
from __future__ import annotations

import pytest
from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(sam_image="public.ecr.aws/sam/build-python3.13")
""")

    test_file = session_dir / "test_stall.py"
    test_file.write_text("""\
from __future__ import annotations

import time


def test_stall(docker_network: str) -> None:
    time.sleep(60)
""")


def _poll_until_gone(
    client: docker.DockerClient,
    network_name: str,
    timeout: float = 5.0,
    interval: float = 0.5,
) -> bool:
    """Return True if the network disappears within timeout seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client.networks.get(network_name)
        except docker.errors.NotFound:
            return True
        time.sleep(interval)
    return False


def _newest_network(
    networks: list[docker.models.networks.Network],
) -> docker.models.networks.Network:
    """Return the network with the most recent Created timestamp."""

    def _created_ts(n: docker.models.networks.Network) -> datetime:
        attrs = n.attrs or {}
        raw = attrs.get("Created", "1970-01-01T00:00:00.000000000Z")
        # Docker may emit nanosecond precision; fromisoformat can't handle the trailing Z
        # with 9-digit fractional seconds in Python <3.11, so strip to microseconds.
        if "." in raw:
            base, frac = raw.split(".", 1)
            frac = frac[:6]  # keep only microseconds
            raw = f"{base}.{frac}"
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))

    return max(networks, key=_created_ts)


def _poll_containers_gone(
    client: docker.DockerClient,
    name_prefix: str,
    timeout: float = 30.0,
    interval: float = 0.5,
) -> bool:
    """Return True if zero containers matching name_prefix remain."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = client.containers.list(all=True, filters={"name": name_prefix})
        if not remaining:
            return True
        time.sleep(interval)
    return False


class TestRyukCrashCleanup:
    def test_network_removed_after_sigkill(self, tmp_path: Path) -> None:
        """Ryuk removes the samstack bridge network when pytest is SIGKILLed."""
        session_dir = tmp_path / "crash_session"
        session_dir.mkdir()
        _write_subprocess_session(session_dir)

        # Launch subprocess pytest session.
        # Use DEVNULL to avoid pipe-buffer deadlocks if the subprocess emits
        # more output than the OS buffer allows (WR-02).
        # start_new_session=True gives the subprocess its own process group
        # so killpg terminates the entire tree.
        proc = subprocess.Popen(
            ["uv", "run", "pytest", str(session_dir), "-v", "--timeout=120"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Give the subprocess time to create the network and register with Ryuk.
        # docker_network runs at session start; 5 s covers slow CI runners.
        time.sleep(5)

        # Read the network name from Docker: find the samstack-* network
        # whose labels include the testcontainers session-id.
        # Filter by both label and name prefix to avoid matching networks from
        # concurrent or parent pytest sessions (WR-01).
        docker_client = docker.from_env()
        samstack_networks = docker_client.networks.list(
            filters={
                "label": "org.testcontainers.session-id",
                "name": "samstack-",
            }
        )
        assert samstack_networks, (
            "No labeled samstack network found — did docker_network run? "
            "Increase the sleep above or check subprocess output."
        )
        # Pick the most recently created network. The parent pytest session
        # already has a docker_network from earlier tests (e.g. DynamoDB fixtures),
        # so there may be multiple samstack-* networks. The subprocess's network
        # is the newest one.
        network_name = _newest_network(samstack_networks).name

        # SIGKILL the entire subprocess group — simulates a crashed pytest
        # process. killpg ensures all child processes are terminated.
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()

        # Poll Docker until Ryuk removes the network (hard assert).
        # 30 s timeout: Ryuk's default cleanup cycle polls every 10 s,
        # and GitHub-hosted runners add latency for TCP disconnect detection.
        gone = _poll_until_gone(docker_client, network_name, timeout=30.0, interval=0.5)
        assert gone, (
            f"Docker network '{network_name}' still exists 30 s after SIGKILL. "
            "Ryuk did not clean it up. Verify TESTCONTAINERS_RYUK_DISABLED is not set "
            "and that the test is running on Linux (Docker Desktop does not propagate "
            "SIGKILL connection drops to Ryuk)."
        )

        # Assert no sam_ containers leaked from this or other sessions.
        # With docker_network-only, there are none — assertion is a safety net.
        # Sub-container cascade on crash is verified by the normal teardown
        # test (test_subcontainer_teardown.py), which confirms _teardown_network
        # stops and removes all containers before network removal.
        sub_containers_gone = _poll_containers_gone(
            docker_client, "sam_", timeout=5.0, interval=0.5
        )
        assert sub_containers_gone, (
            "Unexpected sam_ containers found after crash test session. "
            f"Remaining: {[c.name for c in docker_client.containers.list(all=True, filters={'name': 'sam_'})]}"
        )

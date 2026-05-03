"""Integration crash test: confirms warm Lambda runtime sub-containers are
cleaned up via Ryuk network cascade after SIGKILL.

Requires Docker + Ryuk enabled. Skips on macOS — Docker Desktop's TCP proxy
does not propagate SIGKILL connection drops to Ryuk inside the Linux VM.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import docker
import docker.errors
import pytest
from testcontainers.core.config import testcontainers_config

pytestmark = pytest.mark.skipif(
    testcontainers_config.ryuk_disabled or sys.platform == "darwin",
    reason="Ryuk crash-cleanup test requires Ryuk on Linux (Docker Desktop on macOS does not propagate SIGKILL to Ryuk)",
)


def _write_warm_crash_session(session_dir: Path, *, fixture_dir: Path) -> Path:
    """Write a pytest session that starts SAM API with warm containers and stalls.

    Injects a session-scoped autouse fixture that writes ``ready.flag`` once
    ``sam_api`` is fully resolved.  The file contains the Docker network name
    on line 1 and a comma-separated list of short container IDs (all containers
    connected to that network at that moment) on line 2.

    The outer test waits for the file, snapshots the container IDs, then
    SIGKILLs and verifies every snapshotted container has been removed.
    """
    ready_file = session_dir / "ready.flag"

    conftest = session_dir / "conftest.py"
    conftest.write_text(f"""\
from __future__ import annotations
from pathlib import Path
import docker as docker_sdk
import pytest
from samstack.settings import SamStackSettings

FIXTURE_DIR = Path(r"{fixture_dir}")
READY_FILE = Path(r"{ready_file}")


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        project_root=FIXTURE_DIR,
        log_dir="logs/sam",
        add_gitignore=False,
    )


@pytest.fixture(scope="session")
def warm_functions() -> list[str]:
    return ["WarmCheckFunction"]


@pytest.fixture(scope="session")
def warm_api_routes() -> dict[str, str]:
    return {{"WarmCheckFunction": "/warm"}}


@pytest.fixture(scope="session", autouse=True)
def _signal_ready(sam_api: str, docker_network: str) -> None:
    # sam_api depends on sam_lambda_endpoint which already pre-warmed
    # WarmCheckFunction — warm Lambda containers exist on the network now.
    _docker = docker_sdk.from_env()
    network = _docker.networks.get(docker_network)
    network.reload()
    cids = [c.id for c in network.containers]
    READY_FILE.write_text(f"{{docker_network}}\\n{{','.join(cids)}}")
""")

    test_file = session_dir / "test_warm_and_stall.py"
    test_file.write_text("""\
from __future__ import annotations

import time

import requests


def test_warm_and_stall(sam_api: str) -> None:
    resp = requests.get(f"{sam_api}/warm", timeout=30)
    assert resp.status_code == 200
    time.sleep(60)
""")

    return ready_file


def _wait_for_ready(
    ready_file: Path,
    proc: subprocess.Popen,
    *,
    interval: float = 0.5,
) -> bool:
    """Block until ready_file appears or the subprocess exits.

    Returns True when the file is found, False if the subprocess exits first
    (indicating a startup failure).  No hardcoded timeout — the outer pytest
    ``--timeout`` is the safety net if the subprocess hangs indefinitely.
    """
    while True:
        if ready_file.exists():
            return True
        if proc.poll() is not None:
            return False
        time.sleep(interval)


def _poll_containers_gone(
    client: docker.DockerClient,
    container_ids: list[str],
    timeout: float = 30.0,
    interval: float = 0.5,
) -> list[str]:
    """Poll until all container IDs are unreachable, or timeout.

    Returns the list of IDs still present after timeout (empty means all gone).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = []
        for cid in container_ids:
            try:
                client.containers.get(cid)
                remaining.append(cid)
            except docker.errors.NotFound:
                pass
        if not remaining:
            return []
        time.sleep(interval)
    return remaining


class TestWarmCrashCleanup:
    def test_warm_subcontainers_removed_after_sigkill(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "warm_crash_session"
        session_dir.mkdir()

        fixture_dir = Path(__file__).parent.parent / "fixtures" / "warm_check"
        ready_file = _write_warm_crash_session(session_dir, fixture_dir=fixture_dir)

        proc = subprocess.Popen(
            ["uv", "run", "pytest", str(session_dir), "-v", "--timeout=180"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        docker_client = docker.from_env()

        ready = _wait_for_ready(ready_file, proc)
        assert ready, (
            "Session subprocess exited before signaling ready — SAM startup failed. "
            f"Exit code: {proc.returncode}. "
            f"Check SAM logs under {session_dir}."
        )

        lines = ready_file.read_text().strip().splitlines()
        network_name = lines[0]
        container_ids = lines[1].split(",") if len(lines) > 1 and lines[1] else []

        assert container_ids, (
            f"No containers on network '{network_name}' at ready time — "
            "warm Lambda container was not created."
        )

        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()

        remaining = _poll_containers_gone(docker_client, container_ids, timeout=30.0)
        assert not remaining, (
            "Containers still present 30s after SIGKILL — Ryuk did not clean them up. "
            "Verify TESTCONTAINERS_RYUK_DISABLED is not set and test is on Linux. "
            f"Network: '{network_name}'. Still running: {remaining}"
        )

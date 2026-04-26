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

POLL_STARTUP_TIMEOUT = 60.0
POLL_STARTUP_INTERVAL = 2.0


def _poll_containers_exist(
    client: docker.DockerClient,
    name_prefix: str,
    timeout: float = POLL_STARTUP_TIMEOUT,
    interval: float = POLL_STARTUP_INTERVAL,
) -> list[object]:
    """Poll until at least one container matching name_prefix exists, or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = client.containers.list(all=True, filters={"name": name_prefix})
        if found:
            return found
        time.sleep(interval)
    return []


def _write_warm_crash_session(session_dir: Path, *, fixture_dir: Path) -> None:
    conftest = session_dir / "conftest.py"
    conftest.write_text(f"""\
from __future__ import annotations
from pathlib import Path
import pytest
from samstack.settings import SamStackSettings

FIXTURE_DIR = Path(r"{fixture_dir}")


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


class TestWarmCrashCleanup:
    def test_warm_subcontainers_removed_after_sigkill(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "warm_crash_session"
        session_dir.mkdir()

        fixture_dir = Path(__file__).parent.parent / "fixtures" / "warm_check"
        _write_warm_crash_session(session_dir, fixture_dir=fixture_dir)

        proc = subprocess.Popen(
            ["uv", "run", "pytest", str(session_dir), "-v", "--timeout=180"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        docker_client = docker.from_env()
        pre_kill = _poll_containers_exist(docker_client, "sam_")
        assert pre_kill, (
            "No sam_ containers found before SIGKILL — subprocess may have failed to start. "
            f"Remaining containers: {[c.name for c in docker_client.containers.list(all=True)]}"
        )

        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()

        gone = _poll_containers_gone(docker_client, "sam_", timeout=30.0, interval=0.5)
        assert gone, (
            "Warm Lambda runtime sub-containers still present 30s after SIGKILL. "
            "Ryuk did not clean them up. Verify TESTCONTAINERS_RYUK_DISABLED is not set "
            f"and test is on Linux. Remaining: {[c.name for c in docker_client.containers.list(all=True, filters={'name': 'sam_'})]}"
        )

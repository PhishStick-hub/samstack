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

    Injects a session-scoped autouse fixture that writes ``ready.flag`` the
    moment ``sam_api`` is resolved (i.e. after pre-warming completes and warm
    Lambda containers exist).  Returns the path to that flag file so the outer
    test can watch for it instead of polling Docker with a guessed timeout.
    """
    ready_file = session_dir / "ready.flag"

    conftest = session_dir / "conftest.py"
    conftest.write_text(f"""\
from __future__ import annotations
from pathlib import Path
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
def _signal_ready(sam_api: str) -> None:
    # sam_api depends on sam_lambda_endpoint which pre-warmed WarmCheckFunction
    # via direct invoke — warm Lambda containers exist on disk at this point.
    READY_FILE.write_text("ready")
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

        containers = docker_client.containers.list(all=True, filters={"name": "sam_"})
        assert containers, (
            "No sam_ containers found after ready signal. "
            f"All containers: {[c.name for c in docker_client.containers.list(all=True)]}"
        )

        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()

        gone = _poll_containers_gone(docker_client, "sam_", timeout=30.0, interval=0.5)
        assert gone, (
            "Warm Lambda runtime sub-containers still present 30s after SIGKILL. "
            "Ryuk did not clean them up. Verify TESTCONTAINERS_RYUK_DISABLED is not set "
            f"and test is on Linux. Remaining: "
            f"{[c.name for c in docker_client.containers.list(all=True, filters={'name': 'sam_'})]}"
        )

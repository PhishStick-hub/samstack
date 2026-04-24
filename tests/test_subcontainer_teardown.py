"""Verify SAM Lambda runtime sub-containers are cleaned up on normal teardown.

Per D-07: runs in a subprocess session that invokes Lambda then exits cleanly.
The parent process polls Docker after subprocess exit to assert no sam_ prefixed
containers remain — confirming _teardown_network properly stops and removes
SAM-spawned sub-containers during normal session teardown.

Only gates on ryuk_disabled (runs on macOS too — this is the normal teardown
path, not the crash path, so Docker Desktop's TCP proxy is not relevant).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import docker
import pytest
from testcontainers.core.config import testcontainers_config

pytestmark = pytest.mark.skipif(
    testcontainers_config.ryuk_disabled,
    reason="docker_network fixture requires Ryuk-enabled environment for registration",
)


def _write_teardown_session(session_dir: Path, *, fixture_dir: Path) -> None:
    """Write a pytest session that starts SAM, invokes Lambda, then exits.

    The session runs a full SAM stack (build + start-api) and triggers a
    Lambda invocation via HTTP GET /hello to create a Lambda runtime
    sub-container. The test then exits normally — session teardown should
    clean up the sub-container via _teardown_network.
    """
    conftest = session_dir / "conftest.py"
    conftest.write_text(f"""\
from __future__ import annotations
from pathlib import Path
import pytest
from samstack.settings import SamStackSettings

# Absolute path to the hello_world test fixture, embedded at generation time.
FIXTURE_DIR = Path(r"{fixture_dir}")

@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        project_root=FIXTURE_DIR,
        log_dir="logs/sam",
        add_gitignore=False,
    )
""")

    test_file = session_dir / "test_invoke_and_exit.py"
    test_file.write_text("""\
from __future__ import annotations
import time
import requests


def test_invoke_lambda_then_exit(sam_api: str) -> None:
    resp = requests.get(f"{sam_api}/hello", timeout=30)
    assert resp.status_code == 200
    time.sleep(3)
""")


def _poll_for_containers(
    client: docker.DockerClient,
    name_prefix: str,
    expect_gone: bool,
    timeout: float = 15.0,
    interval: float = 0.5,
) -> None:
    """Poll Docker until containers are gone (expect_gone=True) or found."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = client.containers.list(all=True, filters={"name": name_prefix})
        if expect_gone and not remaining:
            return
        if not expect_gone and remaining:
            return
        time.sleep(interval)
    state = client.containers.list(all=True, filters={"name": name_prefix})
    names = [c.name for c in state]
    if expect_gone:
        raise AssertionError(
            f"Expected zero containers matching '{name_prefix}' after "
            f"teardown, but {len(state)} remain after {timeout}s: {names}"
        )
    raise AssertionError(
        f"Expected containers matching '{name_prefix}' but none found after {timeout}s"
    )


class TestSubcontainerNormalTeardown:
    def test_subcontainers_cleaned_after_normal_teardown(self, tmp_path: Path) -> None:
        """Sub-containers are removed after normal pytest session teardown.

        Launches a subprocess pytest session that starts SAM API, invokes
        Lambda via HTTP GET /hello (creating a Lambda runtime sub-container),
        and exits normally. After the subprocess completes, polls Docker to
        assert zero containers with name prefix "sam_" remain — confirming
        _teardown_network properly cleaned up SAM-spawned sub-containers
        during normal session teardown.
        """
        session_dir = tmp_path / "teardown_session"
        session_dir.mkdir()

        fixture_dir = Path.cwd() / "tests" / "fixtures" / "hello_world"
        _write_teardown_session(session_dir, fixture_dir=fixture_dir)

        proc = subprocess.Popen(
            ["uv", "run", "pytest", str(session_dir), "-v", "--timeout=180"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        exit_code = proc.wait(timeout=300)

        assert exit_code == 0, (
            f"Subprocess pytest session failed with exit code {exit_code}. "
            "The SAM session did not complete normally — check that LocalStack "
            "is accessible and the hello_world fixture builds correctly."
        )

        docker_client = docker.from_env()
        _poll_for_containers(
            docker_client,
            name_prefix="sam_",
            expect_gone=True,
            timeout=15.0,
            interval=0.5,
        )

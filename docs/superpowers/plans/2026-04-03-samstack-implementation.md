# samstack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `samstack`, a pytest plugin library that provides session-scoped fixtures for running AWS SAM Lambdas locally in Docker against LocalStack, with zero host tooling required beyond Docker.

**Architecture:** `samstack` is a pytest plugin (entry point `pytest11`) that reads `[tool.samstack]` from the child project's `pyproject.toml`, starts LocalStack and SAM CLI containers on a shared Docker bridge network, and exposes fixtures for `sam local start-api` and `sam local start-lambda`. SAM Lambda containers reach LocalStack via the internal hostname `localstack` on that network. All container lifecycle is managed by the library.

**Tech Stack:** Python 3.13, uv, ruff, ty, testcontainers[localstack], docker SDK, pytest, boto3, boto3-stubs[lambda]

---

## File Map

```
samstack/
├── pyproject.toml                         # project metadata, entry points, deps
├── src/samstack/
│   ├── __init__.py                        # re-exports SamStackSettings + public errors
│   ├── _errors.py                         # SamStackError hierarchy
│   ├── settings.py                        # SamStackSettings dataclass + load_settings()
│   ├── _process.py                        # wait_for_port, tail_log_file, run_one_shot_container, stream_logs_to_file
│   ├── plugin.py                          # pytest plugin: reads pyproject.toml, registers all fixtures
│   └── fixtures/
│       ├── __init__.py                    # empty
│       ├── localstack.py                  # docker_network, localstack_container, localstack_endpoint
│       ├── sam_build.py                   # sam_env_vars, sam_build
│       ├── sam_api.py                     # sam_api_extra_args, sam_api
│       └── sam_lambda.py                  # sam_lambda_extra_args, sam_lambda_endpoint, lambda_client
└── tests/
    ├── fixtures/
    │   └── hello_world/
    │       ├── template.yaml              # minimal SAM template (HelloWorldFunction + API Gateway)
    │       └── src/
    │           └── handler.py             # GET /hello → 200, POST /hello → writes to S3 → 201
    ├── conftest.py                        # points samstack at hello_world fixture dir
    ├── test_settings.py                   # unit tests (no Docker)
    ├── test_sam_build.py                  # build succeeds, .aws-sam/ created
    ├── test_sam_api.py                    # GET /hello → 200 via requests
    ├── test_sam_lambda.py                 # invoke HelloWorldFunction via lambda_client → 200
    └── test_localstack_integration.py     # POST /hello → Lambda writes to S3 → assert object exists
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/samstack/__init__.py`
- Create: `src/samstack/fixtures/__init__.py`

- [ ] **Step 1: Initialise the project with uv**

```bash
cd /Users/ivan_shcherbenko/Repo/samstack
uv init --lib --python 3.13
```

- [ ] **Step 2: Replace generated `pyproject.toml` with the correct content**

```toml
[build-system]
requires = ["hatchling>=1.26"]
build-backend = "hatchling.build"

[project]
name = "samstack"
version = "0.1.0"
description = "Pytest fixtures for testing AWS SAM Lambdas locally with LocalStack"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "testcontainers[localstack]>=4.10.0",
    "docker>=7.0.0",
    "boto3>=1.35.0",
]

[project.entry-points."pytest11"]
samstack = "samstack.plugin"

[tool.hatch.build.targets.wheel]
packages = ["src/samstack"]

[tool.pytest.ini_options]
filterwarnings = [
    "ignore::DeprecationWarning:testcontainers.*",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "requests>=2.32.0",
    "boto3-stubs[lambda,s3]>=1.35.0",
    "ruff>=0.15.2",
    "ty>=0.0.18",
]
```

- [ ] **Step 3: Create `src/samstack/__init__.py`**

```python
from samstack._errors import (
    DockerNetworkError,
    LocalStackStartupError,
    SamBuildError,
    SamStackError,
    SamStartupError,
)
from samstack.settings import SamStackSettings, load_settings

__all__ = [
    "DockerNetworkError",
    "LocalStackStartupError",
    "SamBuildError",
    "SamStackError",
    "SamStartupError",
    "SamStackSettings",
    "load_settings",
]
```

- [ ] **Step 4: Create `src/samstack/fixtures/__init__.py`** (empty file)

- [ ] **Step 5: Sync dependencies**

```bash
uv sync
```

Expected: all packages installed, `uv.lock` created.

- [ ] **Step 6: Commit**

```bash
git init
git add pyproject.toml uv.lock src/
git commit -m "chore: scaffold samstack project"
```

---

## Task 2: Error Hierarchy

**Files:**
- Create: `src/samstack/_errors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_errors.py`:

```python
from samstack._errors import (
    DockerNetworkError,
    LocalStackStartupError,
    SamBuildError,
    SamStackError,
    SamStartupError,
)


def test_sam_build_error_is_sam_stack_error() -> None:
    err = SamBuildError(logs="build failed output")
    assert isinstance(err, SamStackError)
    assert "build failed output" in str(err)


def test_sam_startup_error_contains_port_and_log() -> None:
    err = SamStartupError(port=3000, log_tail="last 50 lines")
    assert isinstance(err, SamStackError)
    assert "3000" in str(err)
    assert "last 50 lines" in str(err)


def test_localstack_startup_error_is_sam_stack_error() -> None:
    err = LocalStackStartupError(log_tail="ls crashed")
    assert isinstance(err, SamStackError)
    assert "ls crashed" in str(err)


def test_docker_network_error_is_sam_stack_error() -> None:
    err = DockerNetworkError(name="samstack-abc", reason="permission denied")
    assert isinstance(err, SamStackError)
    assert "samstack-abc" in str(err)
    assert "permission denied" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_errors.py -v
```

Expected: `ImportError` — `_errors` module does not exist yet.

- [ ] **Step 3: Create `src/samstack/_errors.py`**

```python
class SamStackError(Exception):
    """Base exception for all samstack errors."""


class SamBuildError(SamStackError):
    """sam build container exited with non-zero status."""

    def __init__(self, logs: str) -> None:
        self.logs = logs
        super().__init__(f"sam build failed.\n\nLogs:\n{logs}")


class SamStartupError(SamStackError):
    """SAM process did not bind port within timeout."""

    def __init__(self, port: int, log_tail: str) -> None:
        self.port = port
        self.log_tail = log_tail
        super().__init__(
            f"SAM did not start on port {port} within timeout.\n\nLog tail:\n{log_tail}"
        )


class LocalStackStartupError(SamStackError):
    """LocalStack container did not become healthy."""

    def __init__(self, log_tail: str) -> None:
        self.log_tail = log_tail
        super().__init__(f"LocalStack did not become healthy.\n\nLog tail:\n{log_tail}")


class DockerNetworkError(SamStackError):
    """Failed to create or attach shared Docker network."""

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason
        super().__init__(f"Docker network '{name}' error: {reason}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_errors.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/samstack/_errors.py tests/test_errors.py
git commit -m "feat(errors): add SamStackError hierarchy"
```

---

## Task 3: Settings

**Files:**
- Create: `src/samstack/settings.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings.py`:

```python
from pathlib import Path

import pytest

from samstack.settings import SamStackSettings, load_settings


def test_defaults_applied(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.samstack]\nsam_image = "public.ecr.aws/sam/build-python3.13"\n'
    )
    settings = load_settings(tmp_path)
    assert settings.template == "template.yaml"
    assert settings.region == "us-east-1"
    assert settings.api_port == 3000
    assert settings.lambda_port == 3001
    assert settings.localstack_image == "localstack/localstack:4"
    assert settings.log_dir == "logs/sam"
    assert settings.build_args == []
    assert settings.add_gitignore is True
    assert settings.start_api_args == []
    assert settings.start_lambda_args == []
    assert settings.project_root == tmp_path


def test_overrides_applied(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("""
[tool.samstack]
sam_image = "public.ecr.aws/sam/build-python3.13"
region = "eu-west-1"
api_port = 8080
lambda_port = 8081
log_dir = "my-logs"
build_args = ["--use-container"]
add_gitignore = false
start_api_args = ["--debug"]
start_lambda_args = ["--debug"]
""")
    settings = load_settings(tmp_path)
    assert settings.region == "eu-west-1"
    assert settings.api_port == 8080
    assert settings.lambda_port == 8081
    assert settings.log_dir == "my-logs"
    assert settings.build_args == ["--use-container"]
    assert settings.add_gitignore is False
    assert settings.start_api_args == ["--debug"]
    assert settings.start_lambda_args == ["--debug"]


def test_missing_sam_image_raises(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.samstack]\n")
    with pytest.raises(ValueError, match="sam_image"):
        load_settings(tmp_path)


def test_missing_tool_samstack_section_raises(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
    with pytest.raises(ValueError, match="\\[tool\\.samstack\\]"):
        load_settings(tmp_path)


def test_settings_is_dataclass() -> None:
    s = SamStackSettings(sam_image="test-image")
    assert s.sam_image == "test-image"
    assert s.region == "us-east-1"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_settings.py -v
```

Expected: `ImportError` — `settings` module does not exist yet.

- [ ] **Step 3: Create `src/samstack/settings.py`**

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SamStackSettings:
    sam_image: str
    template: str = "template.yaml"
    region: str = "us-east-1"
    api_port: int = 3000
    lambda_port: int = 3001
    localstack_image: str = "localstack/localstack:4"
    log_dir: str = "logs/sam"
    build_args: list[str] = field(default_factory=list)
    add_gitignore: bool = True
    start_api_args: list[str] = field(default_factory=list)
    start_lambda_args: list[str] = field(default_factory=list)
    project_root: Path = field(default_factory=Path.cwd)


def load_settings(project_root: Path) -> SamStackSettings:
    """Parse [tool.samstack] from pyproject.toml in project_root."""
    pyproject = project_root / "pyproject.toml"
    with pyproject.open("rb") as f:
        data = tomllib.load(f)

    tool = data.get("tool", {})
    if "samstack" not in tool:
        raise ValueError(
            "[tool.samstack] section not found in pyproject.toml. "
            "Add it to configure samstack."
        )

    cfg: dict = tool["samstack"]

    if not cfg.get("sam_image"):
        raise ValueError(
            "sam_image is required in [tool.samstack]. "
            "Example: sam_image = \"public.ecr.aws/sam/build-python3.13\""
        )

    return SamStackSettings(
        sam_image=cfg["sam_image"],
        template=cfg.get("template", "template.yaml"),
        region=cfg.get("region", "us-east-1"),
        api_port=int(cfg.get("api_port", 3000)),
        lambda_port=int(cfg.get("lambda_port", 3001)),
        localstack_image=cfg.get("localstack_image", "localstack/localstack:4"),
        log_dir=cfg.get("log_dir", "logs/sam"),
        build_args=list(cfg.get("build_args", [])),
        add_gitignore=bool(cfg.get("add_gitignore", True)),
        start_api_args=list(cfg.get("start_api_args", [])),
        start_lambda_args=list(cfg.get("start_lambda_args", [])),
        project_root=project_root,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_settings.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/samstack/settings.py tests/test_settings.py
git commit -m "feat(settings): add SamStackSettings and load_settings"
```

---

## Task 4: Process Helpers

**Files:**
- Create: `src/samstack/_process.py`
- Create: `tests/test_process.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_process.py`:

```python
import socket
import threading
import time
from pathlib import Path

import pytest

from samstack._errors import SamStartupError
from samstack._process import tail_log_file, wait_for_port


def test_tail_log_file_returns_last_n_lines(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("\n".join(str(i) for i in range(100)))
    tail = tail_log_file(log, lines=10)
    lines = tail.strip().splitlines()
    assert len(lines) == 10
    assert lines[-1] == "99"


def test_tail_log_file_missing_returns_empty(tmp_path: Path) -> None:
    result = tail_log_file(tmp_path / "nonexistent.log")
    assert result == ""


def test_wait_for_port_succeeds_when_port_open(tmp_path: Path) -> None:
    # bind a free port, then wait for it
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.listen(1)
    log = tmp_path / "test.log"
    try:
        wait_for_port("127.0.0.1", port, log_path=log, timeout=5.0)
    finally:
        srv.close()


def test_wait_for_port_raises_on_timeout(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("some log line")
    with pytest.raises(SamStartupError) as exc_info:
        wait_for_port("127.0.0.1", 19999, log_path=log, timeout=1.0, interval=0.2)
    assert "19999" in str(exc_info.value)
    assert "some log line" in str(exc_info.value)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_process.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `src/samstack/_process.py`**

```python
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import docker as docker_sdk

from samstack._errors import SamBuildError, SamStartupError


def tail_log_file(path: Path, lines: int = 50) -> str:
    """Return the last *lines* lines of a log file, or '' if missing."""
    if not path.exists():
        return ""
    content = path.read_text(errors="replace")
    return "\n".join(content.splitlines()[-lines:])


def wait_for_port(
    host: str,
    port: int,
    log_path: Path,
    timeout: float = 120.0,
    interval: float = 0.5,
) -> None:
    """Block until *port* accepts TCP connections or raise SamStartupError."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            socket.create_connection((host, port), timeout=1.0).close()
            return
        except OSError:
            time.sleep(interval)
    raise SamStartupError(port=port, log_tail=tail_log_file(log_path))


def stream_logs_to_file(container_id: str, log_path: Path) -> threading.Thread:
    """Stream Docker container stdout/stderr to *log_path* in a daemon thread."""
    import docker as docker_sdk

    def _stream() -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        client = docker_sdk.from_env()
        try:
            ctr = client.containers.get(container_id)
            with log_path.open("a") as f:
                for chunk in ctr.logs(stream=True, follow=True):
                    f.write(chunk.decode(errors="replace"))
                    f.flush()
        except Exception:
            pass

    t = threading.Thread(target=_stream, daemon=True)
    t.start()
    return t


def run_one_shot_container(
    image: str,
    command: str,
    volumes: dict[str, dict[str, str]],
    working_dir: str = "/var/task",
    network: str | None = None,
) -> tuple[str, int]:
    """Run a container to completion. Returns (logs, exit_code)."""
    import docker as docker_sdk

    client = docker_sdk.from_env()
    kwargs: dict = {"network": network} if network else {}
    container = client.containers.run(
        image=image,
        command=command,
        volumes=volumes,
        working_dir=working_dir,
        detach=True,
        **kwargs,
    )
    result = container.wait()
    logs = container.logs().decode(errors="replace")
    container.remove(force=True)
    return logs, result["StatusCode"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_process.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/samstack/_process.py tests/test_process.py
git commit -m "feat(process): add wait_for_port, tail_log_file, stream_logs_to_file, run_one_shot_container"
```

---

## Task 5: LocalStack Fixtures

**Files:**
- Create: `src/samstack/fixtures/localstack.py`

- [ ] **Step 1: Create `src/samstack/fixtures/localstack.py`**

```python
from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import docker as docker_sdk
import pytest
from testcontainers.localstack import LocalStackContainer

from samstack._errors import DockerNetworkError, LocalStackStartupError
from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def docker_network(samstack_settings: SamStackSettings) -> Iterator[str]:
    """Create a Docker bridge network shared by LocalStack and SAM containers."""
    name = f"samstack-{uuid4().hex[:8]}"
    client = docker_sdk.from_env()
    try:
        network = client.networks.create(name, driver="bridge")
    except Exception as exc:
        raise DockerNetworkError(name=name, reason=str(exc)) from exc
    try:
        yield name
    finally:
        try:
            network.reload()
            for container in network.containers:
                network.disconnect(container, force=True)
            network.remove()
        except Exception:
            pass


@pytest.fixture(scope="session")
def localstack_container(
    samstack_settings: SamStackSettings,
    docker_network: str,
) -> Iterator[LocalStackContainer]:
    """Start LocalStack and connect it to the shared Docker network."""
    container = LocalStackContainer(image=samstack_settings.localstack_image)
    container.with_volume_mapping("/var/run/docker.sock", "/var/run/docker.sock", "rw")
    container.start()

    client = docker_sdk.from_env()
    try:
        network = client.networks.get(docker_network)
        network.connect(container._container.id, aliases=["localstack"])
    except Exception as exc:
        container.stop()
        raise DockerNetworkError(name=docker_network, reason=str(exc)) from exc

    try:
        yield container
    finally:
        try:
            network = client.networks.get(docker_network)
            network.disconnect(container._container.id, force=True)
        except Exception:
            pass
        container.stop()


@pytest.fixture(scope="session")
def localstack_endpoint(localstack_container: LocalStackContainer) -> str:
    """Return the host-accessible LocalStack URL for use in boto3 clients."""
    return localstack_container.get_url()
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
uv run python -c "from samstack.fixtures.localstack import docker_network, localstack_container, localstack_endpoint; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/samstack/fixtures/localstack.py
git commit -m "feat(fixtures): add docker_network, localstack_container, localstack_endpoint"
```

---

## Task 6: SAM Env Vars + Build Fixtures

**Files:**
- Create: `src/samstack/fixtures/sam_build.py`

- [ ] **Step 1: Create `src/samstack/fixtures/sam_build.py`**

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from samstack._errors import SamBuildError
from samstack._process import run_one_shot_container
from samstack.settings import SamStackSettings


def _add_gitignore_entry(project_root: Path, log_dir: str) -> None:
    gitignore = project_root / ".gitignore"
    entry = f"{log_dir}/"
    if gitignore.exists():
        if entry in gitignore.read_text().splitlines():
            return
        gitignore.write_text(gitignore.read_text() + f"\n{entry}\n")
    else:
        gitignore.write_text(f"{entry}\n")


@pytest.fixture(scope="session")
def sam_env_vars(samstack_settings: SamStackSettings) -> dict[str, dict[str, str]]:
    """
    Default environment variables injected into all Lambda functions at runtime.

    Override in your conftest.py to add function-specific vars:

        @pytest.fixture(scope="session")
        def sam_env_vars(sam_env_vars):
            sam_env_vars["MyFunction"] = {"MY_VAR": "value"}
            return sam_env_vars
    """
    return {
        "Parameters": {
            "AWS_ENDPOINT_URL": "http://localstack:4566",
            "AWS_DEFAULT_REGION": samstack_settings.region,
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
        }
    }


@pytest.fixture(scope="session")
def sam_build(
    samstack_settings: SamStackSettings,
    sam_env_vars: dict[str, dict[str, str]],
) -> None:
    """
    Run `sam build` in a one-shot Docker container. Runs once per test session.

    The build output lands in {project_root}/.aws-sam/ and is reused by
    sam_api and sam_lambda_endpoint fixtures.
    """
    log_dir = samstack_settings.project_root / samstack_settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # Write env vars JSON to a path accessible inside the SAM container
    env_vars_path = log_dir / "env_vars.json"
    env_vars_path.write_text(json.dumps(sam_env_vars, indent=2))

    build_cmd = "sam build --skip-pull-image " + " ".join(samstack_settings.build_args)
    volumes = {
        str(samstack_settings.project_root): {"bind": "/var/task", "mode": "rw"},
        "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"},
    }

    logs, exit_code = run_one_shot_container(
        image=samstack_settings.sam_image,
        command=build_cmd,
        volumes=volumes,
    )
    if exit_code != 0:
        raise SamBuildError(logs=logs)

    if samstack_settings.add_gitignore:
        _add_gitignore_entry(samstack_settings.project_root, samstack_settings.log_dir)
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
uv run python -c "from samstack.fixtures.sam_build import sam_env_vars, sam_build; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/samstack/fixtures/sam_build.py
git commit -m "feat(fixtures): add sam_env_vars and sam_build"
```

---

## Task 7: SAM API Fixture

**Files:**
- Create: `src/samstack/fixtures/sam_api.py`

- [ ] **Step 1: Create `src/samstack/fixtures/sam_api.py`**

```python
from __future__ import annotations

from collections.abc import Iterator

import pytest
from testcontainers.core.container import DockerContainer

from samstack._process import stream_logs_to_file, wait_for_port
from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def sam_api_extra_args() -> list[str]:
    """
    Extra CLI args appended to `sam local start-api` after the defaults.

    Override in your conftest.py for full control:

        @pytest.fixture(scope="session")
        def sam_api_extra_args() -> list[str]:
            return ["--skip-pull-image", "--warm-containers", "EAGER", "--debug"]
    """
    return []


@pytest.fixture(scope="session")
def sam_api(
    samstack_settings: SamStackSettings,
    sam_build: None,
    docker_network: str,
) -> Iterator[str]:
    """
    Start `sam local start-api` in Docker. Yields the base URL, e.g. http://127.0.0.1:3000.

    Depends on sam_build (runs once) and docker_network (shared with LocalStack).
    """
    log_dir = samstack_settings.project_root / samstack_settings.log_dir
    log_path = log_dir / "start-api.log"
    # env_vars.json written by sam_build fixture at this path
    env_vars_container_path = f"/var/task/{samstack_settings.log_dir}/env_vars.json"

    default_args = [
        "--skip-pull-image",
        "--warm-containers", "EAGER",
        "--port", str(samstack_settings.api_port),
        "--env-vars", env_vars_container_path,
    ] + samstack_settings.start_api_args

    from samstack.fixtures.sam_api import sam_api_extra_args as _default_extra  # noqa: PLC0415
    extra: list[str] = []  # resolved via fixture injection, not import
    # Note: sam_api_extra_args is injected as a parameter; declare it above in the fixture signature if needed.
    # The extra_args fixture is separate so child projects can override it independently.

    cmd = "sam local start-api " + " ".join(default_args)

    container = (
        DockerContainer(samstack_settings.sam_image)
        .with_kwargs(network=docker_network)
        .with_volume_mapping(str(samstack_settings.project_root), "/var/task", "rw")
        .with_volume_mapping("/var/run/docker.sock", "/var/run/docker.sock", "rw")
        .with_exposed_ports(samstack_settings.api_port)
        .with_command(cmd)
    )
    container.start()
    stream_logs_to_file(container._container.id, log_path)

    host_port = int(container.get_exposed_port(samstack_settings.api_port))
    wait_for_port("127.0.0.1", host_port, log_path=log_path, timeout=120.0)

    try:
        yield f"http://127.0.0.1:{host_port}"
    finally:
        container.stop()
```

> **Note:** The `sam_api_extra_args` fixture is injected via pytest fixture resolution, not direct import. The fixture must be added to the `sam_api` function signature. See correction in Step 2 below.

- [ ] **Step 2: Fix `sam_api` to properly receive `sam_api_extra_args` via fixture injection**

Replace the `sam_api` fixture body with the corrected version (extra_args via parameter):

```python
@pytest.fixture(scope="session")
def sam_api(
    samstack_settings: SamStackSettings,
    sam_build: None,
    docker_network: str,
    sam_api_extra_args: list[str],
) -> Iterator[str]:
    log_dir = samstack_settings.project_root / samstack_settings.log_dir
    log_path = log_dir / "start-api.log"
    env_vars_container_path = f"/var/task/{samstack_settings.log_dir}/env_vars.json"

    default_args = [
        "--skip-pull-image",
        "--warm-containers", "EAGER",
        "--port", str(samstack_settings.api_port),
        "--env-vars", env_vars_container_path,
    ] + samstack_settings.start_api_args + sam_api_extra_args

    cmd = "sam local start-api " + " ".join(default_args)

    container = (
        DockerContainer(samstack_settings.sam_image)
        .with_kwargs(network=docker_network)
        .with_volume_mapping(str(samstack_settings.project_root), "/var/task", "rw")
        .with_volume_mapping("/var/run/docker.sock", "/var/run/docker.sock", "rw")
        .with_exposed_ports(samstack_settings.api_port)
        .with_command(cmd)
    )
    container.start()
    stream_logs_to_file(container._container.id, log_path)

    host_port = int(container.get_exposed_port(samstack_settings.api_port))
    wait_for_port("127.0.0.1", host_port, log_path=log_path, timeout=120.0)

    try:
        yield f"http://127.0.0.1:{host_port}"
    finally:
        container.stop()
```

Write the final `src/samstack/fixtures/sam_api.py`:

```python
from __future__ import annotations

from collections.abc import Iterator

import pytest
from testcontainers.core.container import DockerContainer

from samstack._process import stream_logs_to_file, wait_for_port
from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def sam_api_extra_args() -> list[str]:
    """
    Extra CLI args appended to `sam local start-api` after the defaults.

    Override in your conftest.py:

        @pytest.fixture(scope="session")
        def sam_api_extra_args() -> list[str]:
            return ["--debug"]
    """
    return []


@pytest.fixture(scope="session")
def sam_api(
    samstack_settings: SamStackSettings,
    sam_build: None,
    docker_network: str,
    sam_api_extra_args: list[str],
) -> Iterator[str]:
    """
    Start `sam local start-api` in Docker. Yields base URL http://127.0.0.1:{api_port}.
    Logs written to {log_dir}/start-api.log.
    """
    log_dir = samstack_settings.project_root / samstack_settings.log_dir
    log_path = log_dir / "start-api.log"
    env_vars_container_path = f"/var/task/{samstack_settings.log_dir}/env_vars.json"

    all_args = [
        "--skip-pull-image",
        "--warm-containers", "EAGER",
        "--port", str(samstack_settings.api_port),
        "--env-vars", env_vars_container_path,
    ] + samstack_settings.start_api_args + sam_api_extra_args

    cmd = "sam local start-api " + " ".join(all_args)

    container = (
        DockerContainer(samstack_settings.sam_image)
        .with_kwargs(network=docker_network)
        .with_volume_mapping(str(samstack_settings.project_root), "/var/task", "rw")
        .with_volume_mapping("/var/run/docker.sock", "/var/run/docker.sock", "rw")
        .with_exposed_ports(samstack_settings.api_port)
        .with_command(cmd)
    )
    container.start()
    stream_logs_to_file(container._container.id, log_path)

    host_port = int(container.get_exposed_port(samstack_settings.api_port))
    wait_for_port("127.0.0.1", host_port, log_path=log_path, timeout=120.0)

    try:
        yield f"http://127.0.0.1:{host_port}"
    finally:
        container.stop()
```

- [ ] **Step 3: Verify the module imports cleanly**

```bash
uv run python -c "from samstack.fixtures.sam_api import sam_api_extra_args, sam_api; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/samstack/fixtures/sam_api.py
git commit -m "feat(fixtures): add sam_api_extra_args and sam_api"
```

---

## Task 8: SAM Lambda Fixture

**Files:**
- Create: `src/samstack/fixtures/sam_lambda.py`

- [ ] **Step 1: Create `src/samstack/fixtures/sam_lambda.py`**

```python
from __future__ import annotations

from collections.abc import Iterator

import boto3
import pytest
from mypy_boto3_lambda import LambdaClient
from testcontainers.core.container import DockerContainer

from samstack._process import stream_logs_to_file, wait_for_port
from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def sam_lambda_extra_args() -> list[str]:
    """
    Extra CLI args appended to `sam local start-lambda` after the defaults.

    Override in your conftest.py:

        @pytest.fixture(scope="session")
        def sam_lambda_extra_args() -> list[str]:
            return ["--debug"]
    """
    return []


@pytest.fixture(scope="session")
def sam_lambda_endpoint(
    samstack_settings: SamStackSettings,
    sam_build: None,
    docker_network: str,
    sam_lambda_extra_args: list[str],
) -> Iterator[str]:
    """
    Start `sam local start-lambda` in Docker. Yields the endpoint URL
    http://127.0.0.1:{lambda_port} for use with boto3 Lambda client.
    Logs written to {log_dir}/start-lambda.log.
    """
    log_dir = samstack_settings.project_root / samstack_settings.log_dir
    log_path = log_dir / "start-lambda.log"
    env_vars_container_path = f"/var/task/{samstack_settings.log_dir}/env_vars.json"

    all_args = [
        "--skip-pull-image",
        "--warm-containers", "EAGER",
        "--port", str(samstack_settings.lambda_port),
        "--env-vars", env_vars_container_path,
    ] + samstack_settings.start_lambda_args + sam_lambda_extra_args

    cmd = "sam local start-lambda " + " ".join(all_args)

    container = (
        DockerContainer(samstack_settings.sam_image)
        .with_kwargs(network=docker_network)
        .with_volume_mapping(str(samstack_settings.project_root), "/var/task", "rw")
        .with_volume_mapping("/var/run/docker.sock", "/var/run/docker.sock", "rw")
        .with_exposed_ports(samstack_settings.lambda_port)
        .with_command(cmd)
    )
    container.start()
    stream_logs_to_file(container._container.id, log_path)

    host_port = int(container.get_exposed_port(samstack_settings.lambda_port))
    wait_for_port("127.0.0.1", host_port, log_path=log_path, timeout=120.0)

    try:
        yield f"http://127.0.0.1:{host_port}"
    finally:
        container.stop()


@pytest.fixture(scope="session")
def lambda_client(
    samstack_settings: SamStackSettings,
    sam_lambda_endpoint: str,
) -> LambdaClient:
    """
    Boto3 Lambda client pointed at the local SAM Lambda endpoint.

    Use this to invoke functions directly without HTTP:
        result = lambda_client.invoke(FunctionName="MyFunction", Payload=b"{}")
    """
    return boto3.client(
        "lambda",
        endpoint_url=sam_lambda_endpoint,
        region_name=samstack_settings.region,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
uv run python -c "from samstack.fixtures.sam_lambda import sam_lambda_extra_args, sam_lambda_endpoint, lambda_client; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/samstack/fixtures/sam_lambda.py
git commit -m "feat(fixtures): add sam_lambda_extra_args, sam_lambda_endpoint, lambda_client"
```

---

## Task 9: Plugin Registration

**Files:**
- Create: `src/samstack/plugin.py`

- [ ] **Step 1: Create `src/samstack/plugin.py`**

```python
"""
Pytest plugin entry point for samstack.

Registered via [project.entry-points."pytest11"] in pyproject.toml:
    samstack = "samstack.plugin"

This module registers all fixtures and provides the samstack_settings fixture
by reading [tool.samstack] from the child project's pyproject.toml.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from samstack.fixtures.localstack import (
    docker_network,
    localstack_container,
    localstack_endpoint,
)
from samstack.fixtures.sam_api import sam_api, sam_api_extra_args
from samstack.fixtures.sam_build import sam_build, sam_env_vars
from samstack.fixtures.sam_lambda import lambda_client, sam_lambda_endpoint, sam_lambda_extra_args
from samstack.settings import SamStackSettings, load_settings

# Re-export all fixtures so pytest can discover them via this module
__all__ = [
    "docker_network",
    "lambda_client",
    "localstack_container",
    "localstack_endpoint",
    "sam_api",
    "sam_api_extra_args",
    "sam_build",
    "sam_env_vars",
    "sam_lambda_endpoint",
    "sam_lambda_extra_args",
    "samstack_settings",
]


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    """
    Load [tool.samstack] from the child project's pyproject.toml.

    samstack searches upward from the current working directory for pyproject.toml.
    Override this fixture to supply settings programmatically:

        @pytest.fixture(scope="session")
        def samstack_settings() -> SamStackSettings:
            return SamStackSettings(sam_image="public.ecr.aws/sam/build-python3.13")
    """
    cwd = Path.cwd()
    # Search upward for pyproject.toml
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.exists():
            return load_settings(parent)
    raise FileNotFoundError(
        "pyproject.toml not found. samstack requires [tool.samstack] in pyproject.toml."
    )
```

- [ ] **Step 2: Verify the plugin imports cleanly**

```bash
uv run python -c "import samstack.plugin; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify pytest discovers the plugin**

```bash
uv run pytest --co -q 2>&1 | head -20
```

Expected: no import errors; samstack fixtures appear in the fixture list.

- [ ] **Step 4: Commit**

```bash
git add src/samstack/plugin.py
git commit -m "feat(plugin): register pytest11 entry point and samstack_settings fixture"
```

---

## Task 10: Hello World Lambda Test Fixture

**Files:**
- Create: `tests/fixtures/hello_world/template.yaml`
- Create: `tests/fixtures/hello_world/src/handler.py`

This is the minimal Lambda used by samstack's own integration tests.

- [ ] **Step 1: Create `tests/fixtures/hello_world/src/handler.py`**

```python
"""
Hello World Lambda handler for samstack integration tests.

GET  /hello            → 200 {"message": "hello"}
POST /hello            → writes body to S3 bucket TEST_BUCKET → 201 {"key": "<uuid>"}
Direct invoke (no http) → 200 {"message": "hello"}
"""
from __future__ import annotations

import json
import os
from uuid import uuid4

import boto3


def handler(event: dict, context: object) -> dict:
    http_method = event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method")

    if http_method == "POST":
        bucket = os.environ["TEST_BUCKET"]
        key = f"uploads/{uuid4().hex}.json"
        body = event.get("body", "{}")
        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("AWS_ENDPOINT_URL"),
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        )
        s3.put_object(Bucket=bucket, Key=key, Body=body.encode())
        return {
            "statusCode": 201,
            "body": json.dumps({"key": key}),
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "hello"}),
    }
```

- [ ] **Step 2: Create `tests/fixtures/hello_world/template.yaml`**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: samstack hello_world test fixture

Globals:
  Function:
    Timeout: 10
    MemorySize: 128
    Environment:
      Variables:
        AWS_ENDPOINT_URL: !Ref AWS::NoValue
        AWS_DEFAULT_REGION: us-east-1
        AWS_ACCESS_KEY_ID: test
        AWS_SECRET_ACCESS_KEY: test
        TEST_BUCKET: samstack-integration-test

Resources:
  HelloWorldFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: HelloWorldFunction
      CodeUri: src/
      Handler: handler.handler
      Runtime: python3.13
      Events:
        GetHello:
          Type: Api
          Properties:
            Path: /hello
            Method: get
        PostHello:
          Type: Api
          Properties:
            Path: /hello
            Method: post
```

- [ ] **Step 3: Verify handler syntax**

```bash
uv run python -c "import ast; ast.parse(open('tests/fixtures/hello_world/src/handler.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/
git commit -m "test(fixtures): add hello_world Lambda for integration tests"
```

---

## Task 11: Library Integration Tests

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_sam_build.py`
- Create: `tests/test_sam_api.py`
- Create: `tests/test_sam_lambda.py`
- Create: `tests/test_localstack_integration.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
"""
Configure samstack to use the hello_world test fixture project.
All integration tests share one session: build → start-api → start-lambda → tests.
"""
from __future__ import annotations

from pathlib import Path

import boto3
import pytest
from mypy_boto3_s3 import S3Client

from samstack.settings import SamStackSettings

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hello_world"
INTEGRATION_BUCKET = "samstack-integration-test"


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        project_root=FIXTURE_DIR,
        log_dir="logs/sam",
        add_gitignore=False,  # don't modify the fixture dir's .gitignore
    )


@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars: dict) -> dict:
    """Extend default env vars with TEST_BUCKET for localstack integration test."""
    sam_env_vars["Parameters"]["TEST_BUCKET"] = INTEGRATION_BUCKET
    return sam_env_vars


@pytest.fixture(scope="session")
def s3_client(localstack_endpoint: str) -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=localstack_endpoint,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


@pytest.fixture(scope="session")
def integration_bucket(s3_client: S3Client) -> str:
    s3_client.create_bucket(Bucket=INTEGRATION_BUCKET)
    return INTEGRATION_BUCKET
```

- [ ] **Step 2: Create `tests/test_sam_build.py`**

```python
"""sam build succeeds and produces .aws-sam/ build directory."""
from pathlib import Path

from samstack.settings import SamStackSettings

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "hello_world"


def test_build_produces_aws_sam_dir(sam_build: None, samstack_settings: SamStackSettings) -> None:
    aws_sam_dir = samstack_settings.project_root / ".aws-sam"
    assert aws_sam_dir.exists(), f".aws-sam not found at {aws_sam_dir}"


def test_build_produces_build_dir(sam_build: None, samstack_settings: SamStackSettings) -> None:
    build_dir = samstack_settings.project_root / ".aws-sam" / "build"
    assert build_dir.exists(), f".aws-sam/build not found at {build_dir}"
```

- [ ] **Step 3: Create `tests/test_sam_api.py`**

```python
"""sam local start-api: HTTP requests via API Gateway."""
import requests


def test_get_hello_returns_200(sam_api: str) -> None:
    response = requests.get(f"{sam_api}/hello", timeout=10)
    assert response.status_code == 200


def test_get_hello_returns_message(sam_api: str) -> None:
    response = requests.get(f"{sam_api}/hello", timeout=10)
    body = response.json()
    assert body["message"] == "hello"


def test_unknown_path_returns_404(sam_api: str) -> None:
    response = requests.get(f"{sam_api}/nonexistent", timeout=10)
    assert response.status_code == 404
```

- [ ] **Step 4: Create `tests/test_sam_lambda.py`**

```python
"""sam local start-lambda: direct Lambda invocation via boto3."""
import json

from mypy_boto3_lambda import LambdaClient


def test_invoke_hello_world_returns_200(lambda_client: LambdaClient) -> None:
    result = lambda_client.invoke(
        FunctionName="HelloWorldFunction",
        Payload=b"{}",
    )
    assert result["StatusCode"] == 200


def test_invoke_hello_world_returns_message(lambda_client: LambdaClient) -> None:
    result = lambda_client.invoke(
        FunctionName="HelloWorldFunction",
        Payload=b"{}",
    )
    payload = json.loads(result["Payload"].read())
    body = json.loads(payload["body"])
    assert body["message"] == "hello"


def test_invoke_does_not_raise_function_error(lambda_client: LambdaClient) -> None:
    result = lambda_client.invoke(
        FunctionName="HelloWorldFunction",
        Payload=b"{}",
    )
    assert "FunctionError" not in result
```

- [ ] **Step 5: Create `tests/test_localstack_integration.py`**

```python
"""Lambda interacts with LocalStack S3 via shared Docker network."""
import json

import requests
from mypy_boto3_s3 import S3Client


def test_post_hello_writes_to_s3(
    sam_api: str,
    s3_client: S3Client,
    integration_bucket: str,
) -> None:
    payload = {"item": "book", "qty": 1}
    response = requests.post(
        f"{sam_api}/hello",
        json=payload,
        timeout=15,
    )
    assert response.status_code == 201

    body = response.json()
    key = body["key"]
    assert key.startswith("uploads/")

    # Verify the object actually landed in LocalStack S3
    obj = s3_client.get_object(Bucket=integration_bucket, Key=key)
    stored = json.loads(obj["Body"].read())
    assert stored["item"] == "book"


def test_post_hello_returns_key(sam_api: str, integration_bucket: str) -> None:
    response = requests.post(f"{sam_api}/hello", json={"x": 1}, timeout=15)
    assert response.status_code == 201
    assert "key" in response.json()
```

- [ ] **Step 6: Run the unit tests (no Docker)**

```bash
uv run pytest tests/test_settings.py tests/test_process.py tests/test_errors.py -v
```

Expected: all pass.

- [ ] **Step 7: Run the full integration test suite**

> This requires Docker running locally. First run will pull images and may take a few minutes.

```bash
uv run pytest tests/ -v --timeout=300
```

Expected: all tests PASS. If `test_localstack_integration` fails with a network error, check that the `samstack-*` Docker network exists during the test and that the LocalStack container has alias `localstack` on it.

- [ ] **Step 8: Lint and type-check**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
```

Fix any issues before committing.

- [ ] **Step 9: Commit**

```bash
git add tests/
git commit -m "test: add integration tests for sam_build, sam_api, sam_lambda, localstack"
```

---

## Task 12: Final Verification and README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md` with child project onboarding instructions**

```markdown
# samstack

Pytest fixtures for testing AWS SAM Lambda functions locally. No host AWS SAM CLI required — everything runs in Docker.

## Requirements

- Docker (Desktop or Engine)
- Python 3.13+
- uv

## Installation

```toml
[dependency-groups]
dev = [
    "samstack>=0.1.0",
    "pytest>=8.0.0",
    "requests",
]
```

## Configuration

Add to your `pyproject.toml`:

```toml
[tool.samstack]
template = "template.yaml"
region = "us-east-1"
sam_image = "public.ecr.aws/sam/build-python3.13"
```

## Usage

Fixtures are auto-available after installing `samstack`. No imports needed.

```python
import requests

def test_my_api(sam_api):
    r = requests.get(f"{sam_api}/endpoint")
    assert r.status_code == 200

def test_direct_invoke(lambda_client):
    result = lambda_client.invoke(FunctionName="MyFunction", Payload=b"{}")
    assert result["StatusCode"] == 200
```

## Available Fixtures

| Fixture | Returns | Description |
|---|---|---|
| `samstack_settings` | `SamStackSettings` | Parsed config from `[tool.samstack]` |
| `localstack_container` | `LocalStackContainer` | Running LocalStack instance |
| `localstack_endpoint` | `str` | LocalStack URL for boto3 clients in tests |
| `sam_env_vars` | `dict` | Env vars injected into Lambda runtime |
| `sam_build` | `None` | Triggers `sam build` (session-scoped) |
| `sam_api` | `str` | Base URL for `sam local start-api` |
| `sam_api_extra_args` | `list[str]` | Extra CLI args for start-api |
| `sam_lambda_endpoint` | `str` | Endpoint URL for `sam local start-lambda` |
| `sam_lambda_extra_args` | `list[str]` | Extra CLI args for start-lambda |
| `lambda_client` | `LambdaClient` | boto3 Lambda client → SAM endpoint |

## Customising Fixtures

Override any fixture in your `conftest.py`:

```python
@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars):
    sam_env_vars["MyFunction"] = {"MY_FEATURE_FLAG": "true"}
    return sam_env_vars

@pytest.fixture(scope="session")
def sam_api_extra_args() -> list[str]:
    return ["--debug"]
```
```

- [ ] **Step 2: Run the full test suite one final time**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 3: Final lint + type check**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
```

Expected: no errors.

- [ ] **Step 4: Final commit**

```bash
git add README.md
git commit -m "docs: add README with child project onboarding guide"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered in task |
|---|---|
| sam local start-api in Docker | Task 7 |
| sam local start-lambda in Docker | Task 8 |
| LocalStack via testcontainers | Task 5 |
| Shared Docker network | Task 5 |
| AWS_ENDPOINT_URL injected into Lambda | Task 6 |
| --skip-pull-image default | Tasks 7, 8 |
| --warm-containers EAGER default | Tasks 7, 8 |
| log_dir config + log files | Tasks 6, 7, 8 |
| sam_api_extra_args / sam_lambda_extra_args | Tasks 7, 8 |
| [tool.samstack.start_api_args] | Task 3 (settings), Tasks 7, 8 |
| pyproject.toml config section | Task 3 |
| samstack_settings fixture | Task 9 |
| pytest11 entry point | Task 1, 9 |
| sam_build session-scoped | Task 6 |
| error hierarchy | Task 2 |
| SamBuildError with logs | Tasks 2, 6 |
| SamStartupError with log tail | Tasks 2, 4 |
| LocalStackStartupError | Task 2 |
| DockerNetworkError | Tasks 2, 5 |
| add_gitignore setting | Task 6 |
| hello_world test Lambda | Task 10 |
| test_sam_build / test_sam_api / test_sam_lambda / test_localstack_integration | Task 11 |
| lambda_client fixture | Task 8 |
| Child project onboarding (3 steps) | Task 12 |

All requirements covered. No gaps found.

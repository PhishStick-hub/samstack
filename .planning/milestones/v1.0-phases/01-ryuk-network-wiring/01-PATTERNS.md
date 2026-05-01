# Phase 1: Ryuk Network Wiring - Pattern Map

**Mapped:** 2026-04-23
**Files analyzed:** 3 (1 modified, 2 new test files)
**Analogs found:** 3 / 3

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/samstack/fixtures/localstack.py` | fixture/middleware | event-driven (lifecycle) | itself (current `docker_network`) | self-analog |
| `tests/unit/test_docker_network.py` | test | request-response (mock) | `tests/unit/test_mock_handler.py` | role-match |
| `tests/integration/test_ryuk_crash.py` | test | event-driven (subprocess + Docker poll) | `tests/test_process.py` + `tests/integration/` structure | role-match |

---

## Pattern Assignments

### `src/samstack/fixtures/localstack.py` — `docker_network` fixture (modified)

**Analog:** The existing `docker_network` body in this same file plus `localstack_container` for the `warnings.warn` pattern.

**Current imports block** (lines 1–19):
```python
from __future__ import annotations

import contextlib
import warnings
from collections.abc import Iterator
from typing import TYPE_CHECKING
from uuid import uuid4

import docker as docker_sdk
import pytest
from testcontainers.localstack import LocalStackContainer

from samstack._errors import DockerNetworkError, LocalStackStartupError
from samstack._process import stream_logs_to_file
from samstack.fixtures._sam_container import (
    DOCKER_SOCKET,
    _connect_container_with_alias,
    _disconnect_container_from_network,
)
from samstack.settings import SamStackSettings
```

**New imports to add** (insert after existing testcontainers import, before samstack imports):
```python
from testcontainers.core.config import testcontainers_config
from testcontainers.core.container import Reaper
from testcontainers.core.labels import LABEL_SESSION_ID, SESSION_ID
```

**Current `docker_network` fixture** (lines 68–79) — this is the section being modified:
```python
@pytest.fixture(scope="session")
def docker_network(docker_network_name: str) -> Iterator[str]:
    """Create a Docker bridge network shared by LocalStack and SAM containers."""
    client = docker_sdk.from_env()
    try:
        network = client.networks.create(docker_network_name, driver="bridge")
    except Exception as exc:
        raise DockerNetworkError(name=docker_network_name, reason=str(exc)) from exc
    try:
        yield docker_network_name
    finally:
        _teardown_network(network, docker_network_name)
```

**warnings.warn pattern** (lines 37–41, `_stop_network_container`; lines 52–56, `_teardown_network`):
```python
    except Exception as exc:
        warnings.warn(
            f"samstack: failed to stop container during network teardown: {exc}",
            stacklevel=2,
        )
```
Note: `stacklevel=2` is the established project baseline for warnings emitted from inside fixture helpers. Apply the same level for the Ryuk socket failure warning.

**Target shape for modified `docker_network`** — execution order per D-01 through D-07:
```python
@pytest.fixture(scope="session")
def docker_network(docker_network_name: str) -> Iterator[str]:
    """Create a Docker bridge network shared by LocalStack and SAM containers."""
    client = docker_sdk.from_env()
    try:
        network = client.networks.create(
            docker_network_name,
            driver="bridge",
            labels={LABEL_SESSION_ID: SESSION_ID},   # D-01
        )
    except Exception as exc:
        raise DockerNetworkError(name=docker_network_name, reason=str(exc)) from exc
    if not testcontainers_config.ryuk_disabled:       # D-03
        Reaper.get_instance()                         # D-06
        try:
            Reaper._socket.send(                      # D-07
                f"network=name={docker_network_name}\r\n".encode()
            )
        except Exception as exc:                      # D-04
            warnings.warn(
                f"samstack: failed to register network with Ryuk: {exc}",
                stacklevel=2,
            )
    try:
        yield docker_network_name
    finally:
        _teardown_network(network, docker_network_name)  # D-05
```

---

### `tests/unit/test_docker_network.py` (new, TEST-01 + TEST-02)

**Analog:** `tests/unit/test_mock_handler.py` — uses `monkeypatch`, `MagicMock`, module-level patches, and groups tests into classes.

**File header pattern** (from `test_mock_handler.py` lines 1–11):
```python
from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

import pytest
```

**monkeypatch + MagicMock fixture pattern** (from `test_mock_handler.py` lines 25–36):
```python
@pytest.fixture
def s3_stub(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    stub = MagicMock(spec=S3Client)
    stub.get_object.side_effect = ClientError(...)
    monkeypatch.setattr(mh.boto3, "client", _fake_boto3_client)
    return stub
```
Apply this pattern for patching `testcontainers_config.ryuk_disabled`, `Reaper.get_instance`, and `Reaper._socket`.

**pytest.warns pattern** — use `pytest.warns(UserWarning)` as context manager to assert `warnings.warn` calls (standard pytest; no analog yet in this codebase, but consistent with `pytest.raises` usage in `test_mock_types.py`).

**Class grouping pattern** (from `test_mock_handler.py`):
```python
class TestSpyHandler:
    def test_captures_call_and_returns_default_http(
        self, env: None, s3_stub: MagicMock
    ) -> None:
        ...
```
Use the same class-per-scenario structure: `class TestDockerNetworkRyukEnabled` and `class TestDockerNetworkRyukDisabled`.

**autouse fixture pattern** (from `test_mock_handler.py` lines 14–16):
```python
@pytest.fixture(autouse=True)
def _reset_module_client() -> None:
    mh._s3 = None
```
Use an `autouse` fixture to reset any patched module state between unit tests if needed.

---

### `tests/integration/test_ryuk_crash.py` (new, TEST-03)

**Analog:** `tests/test_process.py` for subprocess + timeout patterns; `tests/integration/conftest.py` for session override pattern; `tests/integration/test_s3_fixtures.py` for the file header and class structure used in integration tests.

**Integration test file header** (from `tests/integration/test_s3_fixtures.py` lines 1–8):
```python
"""Integration tests for S3 resource fixtures against real LocalStack."""

from __future__ import annotations

from collections.abc import Callable

from samstack.resources.s3 import S3Bucket
```

**Integration conftest override pattern** (`tests/integration/conftest.py` lines 1–17) — the crash test needs its own throwaway conftest for the subprocess pytest session:
```python
"""
Shared fixtures for integration tests against a real LocalStack instance.
"""
from __future__ import annotations

import pytest
from samstack.settings import SamStackSettings


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
    )
```
The subprocess conftest for TEST-03 must override `samstack_settings` (or omit it) so only `docker_network` runs — no SAM build, no LocalStack pull.

**Wait/poll pattern** (from `tests/test_process.py` lines 39–44):
```python
def test_wait_for_port_raises_on_timeout(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("some log line")
    with pytest.raises(SamStartupError) as exc_info:
        wait_for_port("127.0.0.1", 19999, log_path=log, timeout=1.0, interval=0.2)
    assert "19999" in str(exc_info.value)
```
Apply the same `timeout + interval` keyword pattern for the poll loop in the crash test. Per D-10: poll timeout 2–5 s, interval 0.5 s.

**subprocess pattern** — no existing analog in this codebase; use `subprocess.Popen` with `signal.SIGKILL` on the child process:
```python
import os
import signal
import subprocess
import time

proc = subprocess.Popen(["uv", "run", "pytest", str(conftest_dir), "-v"])
time.sleep(N)           # let docker_network fixture run past network creation
os.kill(proc.pid, signal.SIGKILL)
proc.wait()
```
Then poll Docker SDK until `client.networks.get(network_name)` raises `docker.errors.NotFound` (404) — hard assert per D-10.

---

## Shared Patterns

### `warnings.warn` with `stacklevel=2`
**Source:** `src/samstack/fixtures/localstack.py` lines 37–41 and 52–56
**Apply to:** Ryuk socket failure in modified `docker_network`
```python
warnings.warn(
    f"samstack: <descriptive message>: {exc}",
    stacklevel=2,
)
```

### `contextlib.suppress(Exception)` for best-effort teardown
**Source:** `src/samstack/fixtures/localstack.py` line 43
**Apply to:** Crash test teardown assertions where Docker state may already be gone
```python
with contextlib.suppress(Exception):
    network.disconnect(container, force=True)
```

### `from __future__ import annotations` header
**Source:** Every source and test file in this project
**Apply to:** All new files — mandatory first line.

### Type annotations on all function signatures
**Source:** All existing files — every function has return type annotation
**Apply to:** All new test helpers and fixtures

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/integration/test_ryuk_crash.py` subprocess section | test | event-driven (SIGKILL + Docker poll) | No SIGKILL subprocess pattern exists in this codebase — use stdlib `subprocess.Popen` + `os.kill` |

---

## Metadata

**Analog search scope:** `src/samstack/fixtures/`, `tests/unit/`, `tests/integration/`, `tests/test_process.py`, `tests/test_errors.py`, `tests/test_plugin.py`
**Files scanned:** 9
**Pattern extraction date:** 2026-04-23

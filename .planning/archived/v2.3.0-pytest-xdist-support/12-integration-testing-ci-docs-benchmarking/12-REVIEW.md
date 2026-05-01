---
phase: 12-integration-testing-ci-docs-benchmarking
reviewed: 2026-05-01T12:00:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - .github/workflows/_ci.yml
  - README.md
  - pyproject.toml
  - scripts/benchmark.py
  - src/samstack/_xdist.py
  - src/samstack/fixtures/localstack.py
  - src/samstack/fixtures/sam_api.py
  - tests/conftest.py
  - tests/unit/test_xdist_sam_api.py
  - tests/xdist/conftest.py
  - tests/xdist/test_basic.py
  - tests/xdist/test_crash/conftest.py
  - tests/xdist/test_crash/test_crash.py
  - tests/xdist/test_crash/test_infra_trigger.py
  - tests/xdist/test_resource_parallelism.py
findings:
  critical: 1
  warning: 1
  info: 5
  total: 7
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-05-01
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Reviewed all 15 files changed during Phase 12 (integration testing, CI, docs, benchmarking for v2.3.0 xdist support). The implementation is well-structured and thorough — the xdist coordination layer, test suite, CI pipeline, and documentation form a cohesive deliverable. 

One **critical** race condition was identified in the shared state file write path: `write_state_file()` uses `threading.Lock()` which does not protect across xdist worker processes. Under concurrent teardown, `gwN_done` keys can be lost, causing gw0 to wait the full 300s timeout and fail the run. One **warning** was identified in the `docker_network` fixture's lock-failure fallback path. Five **info** items cover type annotations, import hygiene, and code style.

The xdist crash test, resource parallelism tests, SAM API fixture dependency chain, CI workflow steps, README documentation, and benchmark script are all correct and well-tested.

---

## Critical Issues

### CR-01: Cross-process TOCTOU race in `write_state_file` — `threading.Lock` does not protect across xdist workers

**File:** `src/samstack/_xdist.py:64-69`

**Issue:** `write_state_file()` reads the full state JSON, adds a key, and writes it back under a `threading.Lock` (`_state_lock`, line 17). Under pytest-xdist, workers are separate **processes**, not threads. A `threading.Lock` only serializes access within a single process. Two workers writing different keys simultaneously will produce a classic read-modify-write race:

1. Worker 1 reads state `{"localstack_endpoint": "...", "sam_api_endpoint": "..."}`
2. Worker 2 reads the same state
3. Worker 1 writes `{"localstack_endpoint": "...", "sam_api_endpoint": "...", "gw1_done": true}`
4. Worker 2 writes `{"localstack_endpoint": "...", "sam_api_endpoint": "...", "gw2_done": true}` — **Worker 1's `gw1_done` is lost**

The concrete failure mode: during teardown, workers 1+ write `gwN_done` to shared state via `localstack_container`'s finally block (localstack.py:235). If two `gwN_done` writes race, one key is silently dropped. Gw0's `_wait_for_workers_done()` then waits the full 300s timeout and calls `pytest.fail()`, failing the entire test run.

Additionally, `state_path.write_text(json.dumps(state))` (line 69) is not an atomic filesystem operation. A concurrent `read_state_file()` in another process could read a partially-written file, though in practice small JSON writes tend to be OS-atomic on Linux.

**Fix:** Replace `threading.Lock` with a file-based lock using the `filelock` package (already a project dependency at `pyproject.toml:30`). Use atomic write-to-temp-then-rename:

```python
import os
import tempfile
from filelock import FileLock

_STATE_FILE_LOCK: FileLock | None = None

def _get_state_lock() -> FileLock:
    global _STATE_FILE_LOCK
    if _STATE_FILE_LOCK is None:
        lock_path = get_state_dir() / "state.lock"
        _STATE_FILE_LOCK = FileLock(str(lock_path), timeout=10.0)
    return _STATE_FILE_LOCK

def write_state_file(key: str, value: Any) -> None:
    with _get_state_lock():
        state = read_state_file()
        state[key] = value
        state_path = get_state_dir() / "state.json"
        # Atomic write: temp file + rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(state_path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f)
            os.replace(tmp_path, str(state_path))
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_path)
            raise
```

Note: `read_state_file()` (line 57-61) also benefits from lock protection. While its current `json.loads()` is safe against partial reads (it raises `JSONDecodeError`), a concurrent write mid-read could produce stale data. Wrap reads in the same lock for correctness.

---

## Warnings

### WR-01: `docker_network` lock-failure fallback yields uncreated network name — downstream fixtures fail with confusing errors

**File:** `src/samstack/fixtures/localstack.py:120-123`

**Issue:** When `acquire_infra_lock()` returns `False` on gw0 (line 121), the fixture yields `docker_network_name` (line 122) and returns immediately (line 123) — without creating the Docker network. Downstream fixtures (`localstack_container`, `sam_api`, `sam_lambda_endpoint`) receive a network name string for a network that doesn't exist. They will fail with opaque Docker API errors (e.g., `DockerNetworkError`, `docker.errors.NotFound`) that are hard to diagnose.

Under normal operation, gw0 should always win the lock race (it's the only gw0 process). The lock-failure path is defensive but the current behavior — yielding a useless name — is worse than failing loudly. If gw0 can't acquire the infrastructure lock, something is wrong and the user should know immediately.

**Fix:** Raise a descriptive error instead of silently yielding:

```python
if worker_id == "gw0":
    if not acquire_infra_lock():
        pytest.fail(
            "gw0 failed to acquire infrastructure lock — "
            "another process may already hold it. "
            "This should not happen under normal xdist operation."
        )
```

Alternatively, use `wait_for_state_key("docker_network", timeout=120)` on the lock-failure path (same as gw1+), since the real gw0 already wrote it:

```python
if worker_id == "gw0":
    if not acquire_infra_lock():
        resolved_name = wait_for_state_key("docker_network", timeout=120)
        yield resolved_name
        return
```

---

## Info

### IN-01: Module-level `_lock: Any` type annotation — should use `FileLock | None`

**File:** `src/samstack/_xdist.py:18`

**Issue:** `_lock: Any = None` discards type safety. The variable stores a `FileLock` instance or `None`. Using `Any` prevents ty from catching misuse.

**Fix:**
```python
from filelock import FileLock

_lock: FileLock | None = None
```

### IN-02: Local `import os` / `import time` / `import pytest` inside `_wait_for_workers_done` — should be module-level

**File:** `src/samstack/fixtures/localstack.py:184-185, 205-206`

**Issue:** `_wait_for_workers_done()` does `import os as _os`, `import time as _time` (lines 184-185), and `import pytest` (line 206) inside the function body. Module-level imports for `os` and `time` are missing from the file top, and `pytest` is already imported at line 10 (`import pytest`). Local imports inside function bodies are a code smell — they obscure dependencies and add redundant import overhead on every call.

**Fix:** Add `import os` and `import time` to the module-level imports. Remove the `import pytest` from the function body (reuse line 10). Remove the local imports:

```python
# Top of file (add to existing imports)
import os
import time
```

Then replace `_os.environ.get(...)` with `os.environ.get(...)`, `_time.monotonic()` with `time.monotonic()`, `_time.sleep(0.5)` with `time.sleep(0.5)`, and remove `import pytest` from the internal `if expected:` block.

### IN-03: Broad `except Exception` in benchmark script error handling

**File:** `scripts/benchmark.py:83`

**Issue:** `except Exception as exc:` catches all exception types, which could mask unexpected errors from `time.perf_counter()` or other runtime failures. While this is a development tool (not production code), specific exception handling is still preferred.

**Fix:** Catch the specific exceptions that `subprocess.run` and `time.perf_counter()` can raise:
```python
except (subprocess.SubprocessError, OSError) as exc:
    print(f"ERROR: {exc}")
    results[name] = (0.0, -1)
```

### IN-04: Hardcoded `time.sleep(0.5)` for SNS→SQS propagation delay

**File:** `tests/xdist/test_resource_parallelism.py:64, 68`

**Issue:** Two `time.sleep(0.5)` calls (lines 64 and 68) wait for SNS-to-SQS message delivery on LocalStack. Hardcoded sleeps make tests brittle and slow. A polling approach with timeout would be more robust and potentially faster.

**Fix:** Replace sleep-then-read with a poll loop:
```python
def _wait_for_messages(
    sqs_queue: SqsQueue, min_count: int = 1, timeout: float = 5.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages = sqs_queue.receive(max=10, wait=1)
        if len(messages) >= min_count:
            return
        time.sleep(0.2)
```
Note: this is test code only; the current implementation is functional and documented. This is a maintainability suggestion, not a bug.

### IN-05: `_wait_for_workers_done` may mask test failures via `pytest.fail()` in `finally`

**File:** `src/samstack/fixtures/localstack.py:286-287`

**Issue:** `_wait_for_workers_done()` calls `pytest.fail()` (via internal `pytest.fail`, line 207) on timeout. This call is inside the `localstack_container` fixture's `finally` block. In Python, an exception raised in a `finally` block replaces the original exception from the `yield`. If a test failed and then teardown times out waiting for workers, the test failure is masked by the timeout error.

**Fix:** Guard the call to avoid replacing existing exceptions:
```python
except Exception:
    if worker_id == "gw0":
        with contextlib.suppress(Exception):
            _wait_for_workers_done()
    raise
else:
    if worker_id == "gw0":
        _wait_for_workers_done()
```
This only affects the edge case where a test failure coincides with worker timeout. In normal operation, workers complete before gw0's teardown, so this path is rarely exercised.

---

*Reviewed: 2026-05-01T12:00:00Z*
*Reviewer: the agent (gsd-code-reviewer)*
*Depth: standard*

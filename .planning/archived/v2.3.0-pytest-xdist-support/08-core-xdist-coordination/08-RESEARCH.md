# Phase 8: Core Xdist Coordination — Research

**Researched:** 2026-04-30
**Status:** Complete

## Research Questions

1. How does pytest-xdist expose worker identity?
2. What coordination primitives are available for singleton infrastructure creation?
3. What is the existing samstack fixture architecture and where does xdist injection fit?
4. How to achieve import-safe detection (COORD-01)?

---

## 1. pytest-xdist Worker Detection

### The `worker_id` Fixture

pytest-xdist provides a built-in `worker_id` fixture available in all tests and fixtures:

- **No xdist** (`pytest` without `-n`): `worker_id == "master"`
- **With xdist** (`pytest -n 4`): `worker_id` is `"gw0"`, `"gw1"`, `"gw2"`, `"gw3"`

This fixture is provided by pytest-xdist itself. When xdist is NOT installed, the fixture does NOT exist — so directly requesting `worker_id` as a fixture parameter would cause a fixture-not-found error. This is the core challenge for COORD-01 (import-safe detection).

### Environment Variable Detection (import-safe)

pytest-xdist sets environment variables in worker processes:

- `PYTEST_XDIST_WORKER` — worker name (e.g., `"gw0"`, `"gw1"`)
- `PYTEST_XDIST_WORKER_COUNT` — total number of workers (e.g., `"4"`)

These env vars are **only set in worker processes**. The controller/scheduler process does NOT have them. When running without xdist, neither env var is set.

**Key insight:** `os.environ.get("PYTEST_XDIST_WORKER")` returns `None` when xdist is not installed — zero imports needed. This is the import-safe detection mechanism for COORD-01.

### The `xdist` Module API

When xdist IS installed:
```python
import xdist
xdist.is_xdist_worker(request)      # True if running as worker
xdist.is_xdist_controller(request)  # True if running as controller
xdist.get_xdist_worker_id(request)  # Returns "gw0", "gw1", etc.
```

But this requires `import xdist` which fails when xdist is not installed.

### Architecture Note: Controller vs. Worker

In pytest-xdist, there is NO "master" worker executing tests. The architecture is:

- **Controller** (scheduler): Orchestrates test distribution, does NOT execute tests or resolve fixtures
- **Workers** (gw0, gw1, ...): Execute tests, resolve fixtures, run setup/teardown

This means ALL samstack fixture resolution happens inside worker processes. There is no controller-side fixture lifecycle to hook into. **gw0 is our singleton creator** — it's the first worker and the only one that should start Docker infrastructure.

## 2. Coordination Primitives

### filelock (New Dependency)

`filelock` (PyPI package `filelock`, ≥3.13) is the standard Python library for cross-platform file locking. It's used by pytest-xdist's own test suite and is the recommended approach in the pytest-xdist docs for coordinating singleton resources.

**Library ID:** `/tox-dev/filelock`
**Package:** `filelock>=3.13`
**License:** Public Domain (Unlicense)
**Platforms:** Windows, macOS, Linux (auto-selects msvcrt/fcntl backend)

**API needed for Phase 8:**
```python
from filelock import FileLock, Timeout

# Guard singleton creation — only one worker wins
lock = FileLock("/tmp/samstack-<session>/infra.lock", timeout=0.5)
try:
    with lock.acquire(timeout=0):
        # We got the lock immediately → we're gw0
        create_infrastructure()
except Timeout:
    # Another worker holds the lock → we're gw1+
    wait_for_state_file()
```

The `timeout=0` pattern (non-blocking try) determines gw0 vs. gw1+: the first worker to acquire gets the lock, all others get `Timeout` and enter the wait path.

**Why not a TCP coordination server?**
- Adds complexity (port allocation, health checks, connection management)
- FileLock is battle-tested by pytest-xdist itself
- Filesystem-sharing is sufficient for same-host parallel testing (the only supported mode)

### JSON State File

A JSON file at a predictable temp path serves as the communication channel:

```json
{
  "session_id": "a1b2c3d4",
  "docker_network": "samstack-a1b2c3d4",
  "localstack_endpoint": "http://127.0.0.1:4566",
  "sam_api_endpoint": "http://127.0.0.1:3000",
  "sam_lambda_endpoint": "http://127.0.0.1:3001",
  "build_complete": true,
  "error": null
}
```

**Key design decisions:**
- gw0 writes keys incrementally as infrastructure is created (not all at once at the end)
- gw1+ polls the file with a configurable timeout (default 120s per COORD-03)
- `"error"` key signals gw0 failure → gw1+ calls `pytest.skip()` (COORD-04)
- Session ID (UUID) in the state file path prevents interference between concurrent `pytest` sessions (COORD-04, success criterion 4)

**State file path pattern:** `{temp_dir}/samstack-{session_uuid}/state.json`

Where `temp_dir` is platform-appropriate:
- Linux: `$XDG_RUNTIME_DIR` or `/tmp`
- macOS: `$TMPDIR` or `/tmp`
- The `session_uuid` ensures two concurrent `pytest` invocations get different state files.

## 3. Existing Fixture Architecture

### Dependency Chain (simplified)

```
samstack_settings
    ├── docker_network (creates Docker bridge network)
    │   └── localstack_container (starts LocalStack, connects to network)
    │       └── localstack_endpoint (returns LocalStack URL)
    ├── sam_env_vars (dict of env vars for Lambda functions)
    │   └── sam_build (runs `sam build` once)
    │       ├── sam_api (starts `sam local start-api`)
    │       └── sam_lambda_endpoint (starts `sam local start-lambda`)
    └── [resource fixtures depend on localstack_endpoint]
```

### Fixture Scopes

All infrastructure fixtures are `scope="session"`. This means:
- Each xdist worker has its OWN session → each worker resolves fixtures independently
- Without coordination, 4 workers = 4 Docker networks + 4 LocalStack containers + 4 sam builds

### Plugin Entry Point

`plugin.py` re-exports all fixtures via `__all__`. It also provides `samstack_settings` (the root fixture that reads `[tool.samstack]` from the downstream project's `pyproject.toml`).

### Override Pattern

Downstream projects override fixtures in their `conftest.py`:
```python
@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(sam_image="public.ecr.aws/sam/build-python3.13")
```

This pattern is well-established and must be preserved for backward compatibility (COORD-05).

## 4. Implementation Strategy

### Where xdist Logic Lives

Two options evaluated:

**Option A: Modify each fixture in-place** — Add `worker_id` detection to `docker_network`, `localstack_container`, `sam_build`, etc. Each fixture checks if it should create or wait.

**Option B: New coordination module** — Create a `samstack/xdist.py` (or `samstack/_xdist.py`) module with helper functions, then modify fixtures minimally to call these helpers.

**Decision: Option B.** Reasoning:
- Centralized coordination logic is testable in isolation (COORD-05 requires unit tests without Docker)
- Minimal fixture changes = lower regression risk for non-xdist path (COORD-05)
- Clean separation of concerns

### Module Structure (proposed)

```
src/samstack/
    _xdist.py          # NEW — coordination helpers
    fixtures/
        localstack.py  # MODIFIED — xdist-aware docker_network, localstack_container
        sam_build.py   # MODIFIED — xdist-aware sam_build
        sam_api.py     # MODIFIED — xdist-aware sam_api (Phase 10)
        sam_lambda.py  # MODIFIED — xdist-aware sam_lambda_endpoint (Phase 10)
```

### `_xdist.py` API (proposed)

```python
# Public helpers
def get_worker_id() -> str:
    """Return 'master', 'gw0', 'gw1', etc. Works without xdist installed."""
    ...

def is_controller() -> bool:
    """True if this worker should create Docker infrastructure."""
    ...

def is_xdist_worker() -> bool:
    """True if running under xdist (any worker, including gw0)."""
    ...

# State file helpers
def get_state_file_path() -> Path:
    """Return the session-unique state file path."""
    ...

def read_state_file() -> dict:
    """Read the shared JSON state file."""
    ...

def write_state_file(key: str, value: Any) -> None:
    """Write a key-value pair to the shared state file."""
    ...

# FileLock helpers
def acquire_infra_lock() -> bool:
    """Try to acquire the infrastructure creation lock. Returns True if acquired."""
    ...

def release_infra_lock() -> None:
    """Release the infrastructure creation lock."""
    ...
```

### Fixture Modification Pattern

Each infrastructure fixture follows this pattern:

```python
@pytest.fixture(scope="session")
def docker_network(worker_id: str, docker_network_name: str) -> Iterator[str]:
    if not is_controller(worker_id):
        # gw1+ worker — wait for gw0
        endpoint = wait_for_state_key("docker_network", timeout=120)
        yield endpoint
        return

    # gw0 worker — create infrastructure
    network = _create_docker_network(docker_network_name)
    write_state_file("docker_network", docker_network_name)
    try:
        yield docker_network_name
    finally:
        _teardown_network(network, docker_network_name)
```

**Wait — the worker_id fixture problem:** If xdist is not installed, `worker_id` fixture doesn't exist. We CANNOT list `worker_id` as a fixture parameter because it will cause a "fixture 'worker_id' not found" error when xdist is not installed.

### The Fixture Dependency Problem

This is the core architectural challenge. Options:

**Option 1: Dynamic fixture request**
```python
@pytest.fixture(scope="session")
def docker_network(request, docker_network_name: str) -> Iterator[str]:
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    ...
```
Use `request` fixture (always available) to access the pytest config, and use env vars for worker detection. This avoids `worker_id` fixture dependency.

**Option 2: Lazy import with fallback**
```python
try:
    from xdist import get_xdist_worker_id
except ImportError:
    get_xdist_worker_id = None
```
Still requires `request` fixture.

**Decision: Option 1 — env var detection.** Per COORD-01, detection must be import-safe. `os.environ.get("PYTEST_XDIST_WORKER", "master")` requires zero imports beyond stdlib. The `request` fixture is always available from pytest regardless of plugins.

### Revised Fixture Pattern

```python
@pytest.fixture(scope="session")
def docker_network(request, docker_network_name: str) -> Iterator[str]:
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")

    if worker_id not in ("master", "gw0"):
        # gw1+ worker
        state = wait_for_state_file(request, timeout=120)
        yield state["docker_network"]
        return

    # "master" (no xdist) or "gw0" (xdist controller)
    client = docker_sdk.from_env()
    network = client.networks.create(...)
    if worker_id == "gw0":
        write_state_file(request, "docker_network", docker_network_name)
    try:
        yield docker_network_name
    finally:
        _teardown_network(network, docker_network_name)
```

## 5. FileLock Coordinated Singleton

The FileLock pattern ensures only one worker (gw0) creates Docker infrastructure:

```python
def acquire_infra_lock(request) -> bool:
    """Try to acquire infrastructure lock. Returns True if acquired (gw0/master)."""
    lock_file = get_lock_path(request)
    lock = FileLock(lock_file, timeout=0)  # non-blocking
    try:
        lock.acquire(timeout=0)
        return True  # We're gw0
    except Timeout:
        return False  # We're gw1+
```

The lock file path is derived from the session state directory, ensuring session isolation.

## 6. Error Handling (COORD-04)

When gw0 fails during infrastructure startup:
1. gw0 catches the exception
2. gw0 writes `{"error": "LocalStack startup failed: ..."}` to state file
3. gw0 re-raises the exception (causes its own tests to fail)
4. gw1+ workers detect `"error"` key in state file
5. gw1+ workers call `pytest.skip("gw0 infrastructure startup failed: ...")`

gw1+ polling loop:
```python
def wait_for_state_key(request, key: str, timeout: float = 120.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_state_file(request)
        if "error" in state:
            pytest.skip(f"gw0 infrastructure startup failed: {state['error']}")
        if key in state:
            return state[key]
        time.sleep(0.5)
    pytest.skip(f"Timed out after {timeout}s waiting for gw0 to create {key}")
```

## 7. Session Isolation

Two concurrent `pytest` invocations on the same host must not interfere. Achieved via:

1. **Session UUID** — generated once at session start, used in:
   - State file directory: `{temp}/samstack-{uuid}/`
   - Lock file: `{temp}/samstack-{uuid}/infra.lock`
   - State file: `{temp}/samstack-{uuid}/state.json`

2. **FileLock per session** — each session has its own lock file

3. **State file key namespacing** — the session UUID ensures different sessions read different files

## 8. Testing Strategy (COORD-05)

Unit tests (no Docker required):
- `test_worker_detection.py` — `get_worker_id()` returns correct values for env var combinations
- `test_filelock.py` — `acquire_infra_lock()` returns True for first caller, False for second
- `test_state_file.py` — read/write round-trip, error key detection, timeout behavior
- `test_skip_cascade.py` — `wait_for_state_key()` skips when error key present

These tests verify the coordination logic in isolation without Docker dependencies.

## 9. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| State file path traversal | State directory uses UUID, not user input |
| FileLock directory permissions | Created in system temp dir with default permissions |
| Env var injection | `PYTEST_XDIST_WORKER` is set by pytest-xdist, not user-controlled |
| Race on state file write | FileLock serializes writes; JSON write is atomic on most filesystems (rename pattern if needed) |

## 10. Validation Architecture

### Unit Tests (no Docker)

| Test File | What It Tests | Key Assertions |
|-----------|---------------|----------------|
| `tests/unit/test_xdist_worker_detection.py` | `get_worker_id()` with various env var states | `"master"` when no env var, `"gw0"` when set, etc. |
| `tests/unit/test_xdist_state_file.py` | State file read/write, error key detection | Round-trip integrity, `pytest.skip()` on error, timeout behavior |
| `tests/unit/test_xdist_filelock.py` | `acquire_infra_lock()` exclusivity | First caller gets True, second gets False, lock release works |

### Integration Tests (Phase 12)

Dedicated xdist test suite with `-n 2` exercising the full coordination flow with real Docker infrastructure.

---

## Appendix: Dependencies

| Package | Version | Purpose | Justification |
|---------|---------|---------|---------------|
| `filelock` | `>=3.13` | FileLock for singleton coordination | Used by pytest-xdist's own tests; pure Python, no native deps |
| `pytest-xdist` | N/A (optional) | Downstream dependency, not samstack's | samstack only detects xdist context; does not import xdist |

Only `filelock` is a new samstack dependency. `pytest-xdist` is NOT added to samstack's dependencies — samstack detects xdist via env vars (import-safe), and the downstream project provides xdist.

---

*Research completed: 2026-04-30*
*Next: PLAN.md creation*

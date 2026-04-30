# Phase 9: Docker Infra Xdist-Awareness — Research

**Researched:** 2026-04-30
**Status:** Complete
**Depends on:** Phase 8 (Core Xdist Coordination)

## Research Questions

1. What did Phase 8 deliver and what patterns are established?
2. How does localstack_container become xdist-aware?
3. How does localstack_endpoint become xdist-aware?
4. How does sam_build become xdist-aware?
5. Are resource fixtures already per-worker isolated?

---

## 1. Phase 8 Deliverables

Phase 8 delivered two key artifacts:

### `src/samstack/_xdist.py` (107 lines, 10 functions)
- `get_worker_id()` — env-var detection, import-safe
- `is_xdist_worker()` / `is_controller()` — role detection
- `get_session_uuid()` / `get_state_dir()` — session isolation
- `read_state_file()` / `write_state_file()` / `wait_for_state_key()` — shared state I/O
- `acquire_infra_lock()` / `release_infra_lock()` — FileLock coordination

### `docker_network` xdist-aware fixture (in `localstack.py`)
- Master (no xdist): unchanged — creates network, full teardown
- gw0: acquires FileLock → creates network → writes `docker_network` key → yields → teardown + releases lock
- gw1+: `docker_network_name` waits for `docker_network` key → yields without Docker API calls → no teardown
- Error cascade: gw0 writes `error` key on failure → gw1+ calls `pytest.skip()`

**Established pattern:** `gw0-creates-gw1+-reads` — controller workers create infrastructure and write to shared state; non-controller workers read from state and yield without Docker operations.

## 2. localstack_container Xdist-Awareness

### Current State

```python
@pytest.fixture(scope="session")
def localstack_container(
    samstack_settings: SamStackSettings,
    docker_network: str,
) -> Iterator[LocalStackContainer]:
    container = LocalStackContainer(image=samstack_settings.localstack_image)
    container.with_volume_mapping(DOCKER_SOCKET, DOCKER_SOCKET, "rw")
    container.start()
    # ... log streaming, network connection ...
    yield container
    # ... teardown (disconnect from network, stop container)
```

Every worker calls this independently → 4 workers = 4 LocalStack containers.

### Required Changes

**gw0 path:**
- After `container.start()`, write `localstack_endpoint` to shared state: `write_state_file("localstack_endpoint", container.get_url())`
- Normal teardown (disconnect from network, stop container)
- NO FileLock needed — `docker_network` (parent fixture) already handles lock on gw0, blocking gw1+ from reaching this code before gw0 creates the network

**gw1+ path:**
- Wait for `localstack_endpoint` key via `wait_for_state_key("localstack_endpoint", timeout=120)`
- Yield a lightweight proxy object with `get_url()` → returns the endpoint from state
- No Docker API calls, no teardown

**Proxy class needed:**

```python
class _LocalStackContainerProxy:
    """Lightweight proxy for LocalStackContainer.get_url() on gw1+ workers."""
    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
    def get_url(self) -> str:
        return self._endpoint
    def get_wrapped_container(self) -> None:
        return None
```

This proxy satisfies the `LocalStackContainer` interface consumed by downstream code:
- `localstack_endpoint` calls `.get_url()` → works identically
- `_connect_container_with_alias` calls `.get_wrapped_container()` → returns None (connection skipped on gw1+)

**Why this approach works:**
- `localstack_endpoint` fixture stays unchanged: `localstack_container.get_url()`
- All resource fixtures depend on `localstack_endpoint` → automatically unblocked (INFRA-02 key insight)
- No type changes needed for downstream consumers

### No FileLock in localstack_container

The FileLock in `docker_network` already serializes gw0 vs gw1+:
1. gw0 acquires FileLock in `docker_network`
2. gw0 creates network, writes `docker_network` key
3. gw0 yields `docker_network`, continues to `localstack_container`
4. gw1+ waits in `docker_network_name` for `docker_network` key
5. gw1+ resolves `docker_network` (yields immediately)
6. gw1+ reaches `localstack_container` — gw0 has already started LocalStack by this point or is in progress
7. gw1+ polls `wait_for_state_key("localstack_endpoint")` until gw0 writes it

The FileLock remains held by gw0's `docker_network` fixture until teardown, preventing another gw0-like worker from starting Docker resources. Adding a second FileLock in `localstack_container` would cause deadlock (same process, same lock file).

## 3. localstack_endpoint Xdist-Awareness

### Current State

```python
@pytest.fixture(scope="session")
def localstack_endpoint(localstack_container: LocalStackContainer) -> str:
    return localstack_container.get_url()
```

### Required Changes

**None.** The fixture stays as-is. On gw1+, `localstack_container` is a proxy whose `.get_url()` reads from shared state. On gw0/master, it's a real container whose `.get_url()` returns the actual endpoint.

The URL must be written to shared state by `localstack_container` on gw0 (not by `localstack_endpoint`), because the endpoint is available immediately after `container.start()` — before `localstack_endpoint` resolves. Writing it in `localstack_container` makes it available to gw1+ as early as possible.

## 4. sam_build Xdist-Awareness

### Current State

```python
@pytest.fixture(scope="session")
def sam_build(
    samstack_settings: SamStackSettings,
    sam_env_vars: dict[str, dict[str, str]],
) -> None:
    # ... write env_vars.json, build command, run_one_shot_container ...
    # Raises SamBuildError if exit_code != 0
```

### Required Changes

**gw0/master path:**
- Run `sam build` as currently implemented
- After successful build, write `build_complete` flag to shared state: `write_state_file("build_complete", True)`
- On build failure, write `error` key (same pattern as docker_network): `write_state_file("error", "sam build failed: {error}")`
- FileLock not needed — same reasoning as localstack_container (parent fixture `docker_network` handles serialization)

**gw1+ path:**
- Skip build entirely
- Poll `wait_for_state_key("build_complete", timeout=300)` — 300s timeout (builds can take longer than container startup; COORD-03 default is 120s but build requires more)
- On error detection: `pytest.skip()` via `wait_for_state_key` mechanism
- Return immediately (fixture returns `None`, which is the current return type)

**Key design decisions:**
- `build_complete` flag value is `True` (boolean), matching the existing string-based state file pattern (state file stores JSON, so booleans work)
- Timeout: 300s vs 120s — `sam build` on a cold cache can take 2-3 minutes with Docker pulls; 120s is adequate for container startup but not for build
- The `env_vars.json` file is written BEFORE build in the master/gw0 path — gw1+ does not write this file (it doesn't need to — the SAM containers that use it run on the same filesystem mount)

## 5. Resource Fixture Per-Worker Isolation (INFRA-04)

### Analysis

All 12 resource fixtures use `uuid4().hex[:8]` for unique naming:

| Fixture | Name Pattern | Scope |
|---------|-------------|-------|
| `s3_bucket` | `test-{uuid8}` | function |
| `make_s3_bucket` | `{name}-{uuid8}` | session factory |
| `dynamodb_table` | `test-{uuid8}` | function |
| `make_dynamodb_table` | `{name}-{uuid8}` | session factory |
| `sqs_queue` | `test-{uuid8}` | function |
| `make_sqs_queue` | `{name}-{uuid8}` | session factory |
| `sns_topic` | `test-{uuid8}` | function |
| `make_sns_topic` | `{name}-{uuid8}` | session factory |

**Conclusion:** Per-worker isolation is already achieved without any code changes:
- Each xdist worker is a separate process → separate UUID4 stream
- Even if UUID4 collided (astronomically unlikely), the 8-char hex prefix makes collision probability negligible across 4-16 workers
- All resource operations go to the shared LocalStack instance (via shared `localstack_endpoint`), which correctly handles same-named resources as separate entities

**INFRA-04 requires verification only** — no code changes needed.

## 6. Implementation Strategy

### Files Modified

| File | Change | Plan |
|------|--------|------|
| `src/samstack/fixtures/localstack.py` | xdist-aware `localstack_container` + `_LocalStackContainerProxy` class | 09-01 |
| `src/samstack/fixtures/sam_build.py` | xdist-aware `sam_build` with `build_complete` flag | 09-02 |
| `tests/unit/test_xdist_localstack.py` | Unit tests for localstack_container/localstack_endpoint branching | 09-01 |
| `tests/unit/test_xdist_sam_build.py` | Unit tests for sam_build branching | 09-02 |

### No New Dependencies

All coordination goes through `_xdist.py` (delivered by Phase 8) and `filelock>=3.13` (already in dependencies).

### Parallel Execution

Plans 09-01 and 09-02 touch different files → Wave 1 parallel.

---

## 7. Validation Architecture

### Unit Tests (no Docker)

| Test File | What It Tests | Key Assertions |
|-----------|---------------|----------------|
| `tests/unit/test_xdist_localstack.py` | `localstack_container` branching (master, gw0, gw1+), `localstack_endpoint` integration, error cascade | gw0 writes endpoint to state; gw1+ yields proxy without Docker; proxy `.get_url()` returns state value |
| `tests/unit/test_xdist_sam_build.py` | `sam_build` branching (master, gw0, gw1+), `build_complete` flag, error cascade, resource fixture isolation verification | gw0 runs build + writes flag; gw1+ skips build + polls for flag; gw1+ skips on error |

### Pattern from Phase 8

All unit tests follow the Phase 8 pattern:
- Monkeypatch `loc.get_worker_id` and other `_xdist` functions imported into the fixture module
- Use `getattr(fixture_func, "__wrapped__")` to access raw generator functions
- Mock Docker SDK and `run_one_shot_container` (for sam_build)
- No Docker containers required — all Docker interactions are mocked

---

*Research completed: 2026-04-30*
*Next: PLAN.md creation*

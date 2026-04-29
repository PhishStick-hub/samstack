# Architecture Research: pytest-xdist Integration

**Domain:** pytest plugin — Docker-based test fixtures with parallel worker coordination
**Researched:** 2026-04-30
**Confidence:** HIGH

## Standard Architecture

### System Overview

Under pytest-xdist, each worker is a separate Python process. All samstack fixtures are session-scoped, meaning each worker would normally create its own Docker network, LocalStack, and SAM containers. The xdist integration ensures **exactly one** set of Docker infrastructure is created (by worker 0 or the master process), while all other workers connect to it.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    pytest-xdist Controller                          │
│  (does NOT run tests — distributes and collects results)           │
└────────────────────────────┬────────────────────────────────────────┘
                             │ spawns workers
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│    Worker 0      │ │    Worker 1      │ │    Worker 2      │
│   (gw0/master)   │ │     (gw1)        │ │     (gw2)        │
├──────────────────┤ ├──────────────────┤ ├──────────────────┤
│ DOCKER INFRA     │ │ SHARED STATE     │ │ SHARED STATE     │
│ ┌──────────────┐ │ │ ┌──────────────┐ │ │ ┌──────────────┐ │
│ │docker_network│ │ │ │network_name  │ │ │ │network_name  │ │
│ │LocalStack    │ │ │ │ls_endpoint   │ │ │ │ls_endpoint   │ │
│ │SAM API       │ │ │ │api_endpoint  │ │ │ │api_endpoint  │ │
│ │SAM Lambda    │ │ │ │lambda_endpt  │ │ │ │lambda_endpt  │ │
│ └──────────────┘ │ │ └──────────────┘ │ │ └──────────────┘ │
│       │          │ │       │          │ │       │          │
│       ▼          │ │       ▼          │ │       ▼          │
│  CREATE infra    │ │  READ from state │ │  READ from state │
│  WRITE to file   │ │  (FileLock)      │ │  (FileLock)      │
│  MANAGE lifecycle│ │  SKIP teardown   │ │  SKIP teardown   │
└──────────────────┘ └──────────────────┘ └──────────────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Shared State File │
                    │  (tmp dir, JSON)   │
                    │                    │
                    │  network_name      │
                    │  localstack_url    │
                    │  sam_api_url       │
                    │  sam_lambda_url    │
                    │  worker0_pid       │
                    └────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Xdist Behavior |
|-----------|----------------|----------------|
| `_xdist_coordinator` (NEW) | Inter-worker state sharing, FileLock, endpoint serialization | Creates shared state file on gw0, reads on gw1+ |
| `docker_network` | Docker bridge network lifecycle | gw0/master creates + tears down; gw1+ reads name from state |
| `localstack_container` | LocalStack container lifecycle | gw0/master creates + tears down; gw1+ receives endpoint URL from `localstack_endpoint` |
| `localstack_endpoint` | LocalStack URL string | gw0: reads from container; gw1+: reads from shared state |
| `sam_build` | `sam build` one-shot container | gw0/master runs build; gw1+ NO-OP (build output is on disk) |
| `sam_api` | SAM start-api container lifecycle | gw0/master creates + tears down; gw1+ reads endpoint from shared state |
| `sam_lambda_endpoint` | SAM start-lambda container lifecycle | gw0/master creates + tears down; gw1+ reads endpoint from shared state |
| `sam_env_vars` | Lambda runtime env vars dict | All workers: unchanged (each worker gets its own dict; env vars point at shared services via Docker network DNS) |
| `lambda_client` | boto3 Lambda client | All workers: unchanged (each creates its own boto3 client pointed at shared endpoint) |
| `s3_client` / `dynamodb_client` / `sqs_client` / `sns_client` | boto3 service clients | All workers: unchanged (each creates its own client pointed at shared LocalStack URL) |
| Resource fixtures (`make_*`, `s3_bucket`, etc.) | Per-test AWS resources | All workers: unchanged (function-scoped resources are per-worker, all hitting shared LocalStack) |
| `make_lambda_mock` | LambdaMock factory | gw0/master creates spy bucket + wires env vars; gw1+ shares same bucket |

## Recommended Project Structure

```
src/samstack/
├── fixtures/
│   ├── __init__.py
│   ├── _sam_container.py      # SAM container helpers (unchanged)
│   ├── _xdist.py               # NEW: xdist coordination module
│   ├── localstack.py           # MODIFIED: add xdist awareness
│   ├── resources.py            # LARGELY UNCHANGED: clients use shared endpoint
│   ├── sam_api.py              # MODIFIED: conditional on worker_id
│   ├── sam_build.py            # MODIFIED: skip on non-gw0
│   └── sam_lambda.py           # MODIFIED: conditional on worker_id
├── mock/
│   └── fixture.py              # MODIFIED: shared spy bucket
└── plugin.py                   # MODIFIED: re-export new fixtures, add entry point
```

### Structure Rationale

- **`_xdist.py`**: New module containing all coordination logic — FileLock helpers, state read/write, worker ID detection, endpoint serialization. Keeps xdist complexity contained in one module.
- **`localstack.py`**: Gains `worker_id` parameter on `docker_network`, `localstack_container`, and `localstack_endpoint`. Container lifecycle only on gw0/master.
- **`sam_build.py`**: Short-circuits on gw1+ since build output is filesystem-shared across all workers (they share the same project directory).
- **`sam_api.py` / `sam_lambda.py`**: Conditional container creation — only gw0/master starts SAM services.
- **`resources.py`**: Minimal changes — client fixtures already accept `localstack_endpoint` (a string), so they work naturally when endpoint comes from shared state.
- **`mock/fixture.py`**: `make_lambda_mock` must share the spy bucket across workers. gw0 creates it; other workers use the same bucket name.

## Architectural Patterns

### Pattern 1: FileLock-Guarded Singleton Initialization (xdist canonical)

**What:** Use `filelock.FileLock` to ensure exactly one worker creates shared infrastructure. The first worker to acquire the lock creates resources and writes serialized state; all other workers read it.

**When to use:** For session-scoped fixtures that must execute exactly once across all xdist workers. Docker container creation is the textbook use case — containers are expensive and must not be duplicated.

**Trade-offs:**
- ✅ Simple, battle-tested, recommended by pytest-xdist docs
- ✅ No extra daemon processes or TCP coordination servers
- ✅ Works on all platforms (lock files are OS-agnostic with filelock)
- ⚠️ Worker 0 crash leaves other workers waiting (mitigated with timeout + clear error)
- ⚠️ Container lifecycle outlives FileLock critical section (requires separate teardown handling)

**Example (conceptual):**
```python
# In samstack/fixtures/_xdist.py
import json
import time
from pathlib import Path
from filelock import FileLock

def _xdist_state_path(tmp_path_factory) -> Path:
    root = tmp_path_factory.getbasetemp().parent
    return root / "samstack-xdist-state.json"

def _init_shared_state(tmp_path_factory, worker_id: str) -> dict:
    """Acquire lock, create infra on gw0, read on gw1+. Returns state dict."""
    state_file = _xdist_state_path(tmp_path_factory)
    lock_file = state_file.with_suffix(".lock")

    with FileLock(str(lock_file)):
        if state_file.is_file():
            return json.loads(state_file.read_text())
        elif worker_id in ("master", "gw0"):
            # We are first — create infra (will be populated by callers)
            return {}  # Empty state; fixtures fill it in
        else:
            # Worker 1+ waiting for gw0 — should not reach here
            # because gw0 holds lock until state is written
            raise RuntimeError("Unexpected: non-gw0 inside lock without state")
```

### Pattern 2: Conditional Fixture with Skip Cascade

**What:** Each session-scoped fixture checks `worker_id` and branches: gw0/master path creates Docker resources and manages lifecycle; gw1+ path reads from shared state and yields without teardown.

**When to use:** For every fixture that manages a Docker container lifecycle (create → yield → teardown). Non-Docker fixtures (boto3 clients, env var dicts) are unchanged.

**Trade-offs:**
- ✅ Each fixture self-contains its xdist behavior — easy to understand per-fixture
- ✅ Non-xdist path ("master") is untouched — backward compatible
- ⚠️ Duplication risk if many fixtures follow same pattern → extract to helper
- ⚠️ Error handling needs care: gw0 failure must cascade cleanly

**Example (docker_network):**
```python
@pytest.fixture(scope="session")
def docker_network(docker_network_name, worker_id, tmp_path_factory):
    if worker_id == "master":
        # Standard path — unchanged from current
        client = docker_sdk.from_env()
        network = client.networks.create(docker_network_name, driver="bridge",
                                         labels={LABEL_SESSION_ID: SESSION_ID})
        if not testcontainers_config.ryuk_disabled:
            Reaper.get_instance()
        try:
            yield docker_network_name
        finally:
            _teardown_network(network, docker_network_name)

    elif worker_id == "gw0":
        # Worker 0: create + write to state + manage lifecycle
        client = docker_sdk.from_env()
        network = client.networks.create(docker_network_name, driver="bridge",
                                         labels={LABEL_SESSION_ID: SESSION_ID})
        if not testcontainers_config.ryuk_disabled:
            Reaper.get_instance()
        _write_state(tmp_path_factory, "network_name", docker_network_name)
        try:
            yield docker_network_name
        finally:
            _teardown_network(network, docker_network_name)

    else:
        # gw1+: read network name from shared state
        yield _read_state(tmp_path_factory, "network_name", timeout=120.0)
```

### Pattern 3: Endpoint Passthrough (LocalStack → Resource Fixtures)

**What:** `localstack_endpoint` fixture returns a URL string regardless of worker role. On gw0/master, it calls `localstack_container.get_url()`. On gw1+, it reads the URL from shared state. Downstream boto3 client fixtures are unchanged.

**Why this works:** The boto3 client fixtures (`s3_client`, `dynamodb_client`, etc.) only depend on `localstack_endpoint: str`. They don't need the container object. By making `localstack_endpoint` yield the right URL for every worker, the entire resource fixture tree works automatically.

```
gw0 path:   localstack_container.get_url() → "http://127.0.0.1:4566"
gw1+ path:  shared_state["localstack_endpoint"] → "http://127.0.0.1:4566"

Both flow into:  s3_client(localstack_endpoint)  ← unchanged
                  dynamodb_client(localstack_endpoint) ← unchanged
                  etc.
```

### Pattern 4: State File with Timeout + Retry (Startup Race Mitigation)

**What:** gw1+ workers poll the shared state file with a configurable timeout. If gw0 hasn't written the state within the timeout (e.g., Docker pull takes a while), the reader raises a clear error.

**When to use:** On every `_read_state()` call from gw1+ fixtures. Protects against gw0 startup failures, slow Docker pulls, and race conditions.

**Trade-offs:**
- ✅ Clear error messages (not cryptic connection failures)
- ✅ Configurable timeout accommodates slow environments (CI, first run)
- ⚠️ Blocking wait — but this is session setup, not per-test, so acceptable
- ⚠️ Timeout value tuning needed per environment (default: 120s)

```python
def _read_state(tmp_path_factory, key: str, timeout: float = 120.0) -> str:
    state_file = _xdist_state_path(tmp_path_factory)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state_file.is_file():
            state = json.loads(state_file.read_text())
            if key in state:
                return state[key]
            # State file exists but key missing — gw0 errored?
            if "error" in state:
                pytest.skip(f"Worker 0 infrastructure failed: {state['error']}")
        time.sleep(0.5)
    raise RuntimeError(
        f"Timed out after {timeout}s waiting for worker 0 "
        f"to create shared infrastructure (key: {key}). "
        f"Check worker 0 (gw0) logs for Docker startup errors."
    )
```

## Data Flow

### Worker 0 (Infra Owner) Fixture Resolution Order

```
samstack_settings
    ↓
docker_network_name
    ↓
docker_network (CREATES network, writes to state)
    ↓                ↓
sam_env_vars    localstack_container (CREATES container, writes endpoint to state)
    ↓                ↓
sam_build       localstack_endpoint (reads from container)
(RUNS build)        ↓
    ↓           s3_client, dynamodb_client, sqs_client, sns_client
sam_api             (all point at shared LocalStack)
(CREATES container,
 writes endpoint)
    ↓
sam_lambda_endpoint
(CREATES container,
 writes endpoint)
    ↓
lambda_client

=== ALL TESTS EXECUTE ===

TEARDOWN (reverse order):
  lambda_client (no-op)
  sam_lambda_endpoint (STOPS container, removes from network)
  sam_api (STOPS container, removes from network)
  localstack_container (STOPS container, removes from network)
  docker_network (STOPS all attached containers, removes network)
```

### Worker 1+ (Consumer) Fixture Resolution Order

```
samstack_settings
    ↓
docker_network_name
    ↓
docker_network (READS network name from shared state, waits up to 120s)
    ↓
sam_env_vars (unchanged — mutates own dict)
    ↓
sam_build (NO-OP — build output on disk from gw0)
    ↓
sam_api (READS endpoint from shared state, waits up to 120s)
    ↓
sam_lambda_endpoint (READS endpoint from shared state, waits up to 120s)
    ↓
lambda_client (creates boto3 client pointed at shared endpoint)

    (localstack_endpoint, s3_client, etc. resolve through shared state)
    ↓
    Workers may attempt to resolve localstack_endpoint which also
    reads from shared state (populated by gw0's localstack_container)

=== ALL TESTS EXECUTE ===

TEARDOWN (all NO-OP):
  lambda_client (no-op)
  sam_lambda_endpoint (NO-OP — not our container)
  sam_api (NO-OP — not our container)
  docker_network (NO-OP — not our network)
```

### Shared State File Format

```json
{
  "network_name": "samstack-a1b2c3d4",
  "localstack_endpoint": "http://127.0.0.1:4566",
  "sam_api_endpoint": "http://127.0.0.1:3000",
  "sam_lambda_endpoint": "http://127.0.0.1:3001",
  "worker0_pid": 12345,
  "error": null
}
```

Written by gw0 incrementally as each Docker resource starts. Keys are written as each fixture's setup completes. gw1+ workers wait for specific keys they need (not the whole file).

### Key Data Flows

1. **Docker network name sharing:** gw0 creates `samstack-{uuid8}` network, writes name to state. gw1+ reads it. All worker boto3 clients and Lambda containers use this network name for DNS resolution (LocalStack at `localstack:4566`, SAM Lambda at `sam-lambda:3001`).

2. **LocalStack endpoint sharing:** gw0 starts LocalStack container, gets mapped port via `container.get_exposed_port(4566)`, writes `http://127.0.0.1:{port}` to state. gw1+ reads this URL. All `*_client` fixtures resolve this.

3. **SAM endpoint sharing:** gw0 starts SAM containers, gets mapped ports, writes URLs to state. gw1+ reads them. Lambda code inside SAM containers communicates via Docker network DNS (container-to-container), so the shared endpoints are only for test-side boto3/http clients.

4. **Build output reuse:** gw0 runs `sam build` → files written to `{project_root}/.aws-sam/`. gw1+ skips build since they share the same filesystem. This works because xdist workers are forked from the same process and share the working directory.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-4 workers (typical) | Single LocalStack + single SAM per session. FileLock coordination is sufficient. No resource contention. |
| 5-16 workers | Same architecture. LocalStack handles concurrent requests from all workers. SAM Lambda containers are per-invocation and auto-scaled by SAM CLI. No changes needed. |
| 16+ workers | Potential LocalStack throughput bottleneck. Consider: (a) LocalStack `EAGER_SERVICE_LOADING=1` to reduce cold-start latency, (b) separate D-* investigation for worker pool LocalStack sharding. Out of scope for v2.3.0. |

### Scaling Priorities

1. **First bottleneck:** LocalStack becomes CPU/memory-bound under high concurrent load. Mitigation: users can increase LocalStack container resource limits via docker-compose override.
2. **Second bottleneck:** SAM CLI can only run one `start-api`/`start-lambda` per port. Mitigation: already handled — only one SAM container of each type per session.
3. **Not a concern:** S3/DynamoDB/SQS/SNS fixtures. Each worker creates its own uniquely-named resources in the shared LocalStack. LocalStack handles this natively.

## Anti-Patterns

### Anti-Pattern 1: Per-Worker Docker Containers

**What people do:** Let xdist create Docker containers in every worker (each gw gets its own LocalStack).

**Why it's wrong:** Explodes resource usage (N workers × Docker containers). Port conflicts between workers. No shared state for mock spy buckets. SAM build runs N times.

**Do this instead:** Worker 0 owns all Docker infra. Other workers connect via shared endpoints. This is the entire point of the xdist integration.

### Anti-Pattern 2: TCP Socket Coordination Instead of FileLock

**What people do:** Spin up a small TCP server on worker 0; workers connect to exchange state.

**Why it's wrong:** Adds complexity (port allocation, connection handling, serialization). Unnecessary when all workers share a filesystem (they do in xdist). FileLock is the pytest-xdist documented approach.

**Do this instead:** Use `filelock.FileLock` + JSON state file in `tmp_path_factory.getbasetemp().parent`.

### Anti-Pattern 3: Skipping Worker ID Detection

**What people do:** Detect xdist via `PYTEST_XDIST_WORKER` environment variable only, without the `worker_id` fixture.

**Why it's wrong:** Environment variable is reliable for logging/config but `worker_id` fixture integrates with pytest's dependency injection. Fixtures that need worker ID must declare it as a parameter for proper resolution order.

**Do this instead:** Use `worker_id` as a fixture parameter. Also check `os.environ.get("PYTEST_XDIST_WORKER")` in `pytest_configure` hook for early-config needs (log file naming).

### Anti-Pattern 4: Teardown on Non-Owner Workers

**What people do:** Let every worker try to stop/remove Docker containers.

**Why it's wrong:** Workers race to tear down shared infra. One worker's teardown succeeds; others get Docker API errors (container/network not found). Error noise in test output.

**Do this instead:** Only gw0/master runs teardown. gw1+ fixtures are generators that yield immediately and have empty finally blocks (or explicit no-op branches).

## Integration Points

### External Dependencies

| Dependency | Purpose | Notes |
|-----------|---------|-------|
| `filelock` (NEW) | Cross-process file locking for xdist coordination | Pure Python, no system deps. Already referenced in pytest-xdist docs as the standard approach. |
| `pytest-xdist` (optional peer) | Provides `worker_id` fixture, `PYTEST_XDIST_WORKER` env var | samstack works without xdist installed. Coordination code only activates when `worker_id != "master"`. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `_xdist.py` ↔ fixture modules | Function calls (`_read_state`, `_write_state`, `_xdist_state_path`) | `_xdist.py` is a pure utility module; no circular deps |
| `localstack.py` ↔ `_xdist.py` | `_read_state` for network name and LocalStack URL | `docker_network` and `localstack_endpoint` use shared state on gw1+ |
| `sam_api.py` / `sam_lambda.py` ↔ `_xdist.py` | `_read_state` for SAM endpoint URLs | SAM fixtures use shared state on gw1+ |
| `sam_build.py` ↔ `worker_id` | Conditional execution — skip on gw1+ | Build output shared via filesystem |
| `mock/fixture.py` ↔ `_xdist.py` | Spy bucket name coordination | gw0 creates spy bucket; name shared via state |
| `resources.py` ↔ `localstack_endpoint` | Same interface — endpoint is always a string | No changes needed; `localstack_endpoint` returns correct URL regardless of worker |
| `plugin.py` ↔ all fixture modules | Re-exports all fixtures | Adds `worker_id` re-export, optional `pytest_configure` for xdist detection |

### Crossover with Existing Architecture

| Existing Component | Xdist Impact |
|-------------------|--------------|
| `docker_network` → named bridge `samstack-{uuid8}` | gw0 creates as before; name shared via state. Ryuk registration still on gw0 only. gw1+ don't register with Ryuk (no containers to track). |
| `localstack_container` → `LocalStackContainer` with network alias `localstack` | gw0 creates + attaches to network as before. gw1+ don't get container object — they get endpoint URL from `localstack_endpoint`. |
| `_run_sam_service` → context manager (start, wait, yield, stop) | Only called on gw0. gw1+ skip entirely and read endpoint from shared state. |
| `sam_build` → one-shot `sam build` container | gw0 runs it; gw1+ skip. Output is on shared filesystem. |
| Resource wrappers (`S3Bucket`, `DynamoTable`, etc.) | ALL WORKERS create their own wrappers. Only the boto3 clients underneath point at the shared LocalStack. Function-scoped resources (s3_bucket) remain per-worker. |
| `make_lambda_mock` → spy bucket + env var injection | Must coordinate: gw0 creates the shared spy bucket (or uses provided bucket). gw1+ reuse same bucket name. `sam_env_vars` mutation happens on every worker (needed for SAM's `--env-vars` JSON). |
| `sam_env_vars` → `Parameters` dict | Each worker gets its own dict. Mutations (mock wiring) must happen on ALL workers so the `--env-vars` JSON file is complete on each. |
| Ryuk / testcontainers | Only gw0 registers with Ryuk. gw1+ don't start testcontainers-managed containers. |

## Sources

- [pytest-xdist How-to: Making session-scoped fixtures execute only once](https://pytest-xdist.readthedocs.io/en/latest/how-to.html#making-session-scoped-fixtures-execute-only-once) — HIGH confidence: official docs, FileLock pattern
- [pytest-xdist worker_id fixture](https://pytest-xdist.readthedocs.io/en/latest/how-to.html#identifying-the-worker-process-during-a-test) — HIGH confidence: official API, 'gw0'/'master' semantics
- [Context7: pytest-xdist API functions](https://context7.com/pytest-dev/pytest-xdist/llms.txt) — HIGH confidence: `is_xdist_worker`, `get_xdist_worker_id`, `workerinput`
- [pytest-django fixtures.py](https://github.com/pytest-dev/pytest-django/blob/main/pytest_django/fixtures.py) — HIGH confidence: real-world example of `request.config.workerinput["workerid"]` for database suffixing
- [pytest-xdist distribution docs](https://pytest-xdist.readthedocs.io/en/latest/distribution.html) — HIGH confidence: `--dist loadscope`, `xdist_group` mark, `pytest_xdist_auto_num_workers` hook
- [filelock PyPI](https://pypi.org/project/filelock/) — HIGH confidence: standard cross-platform file locking library, used in xdist examples

---

*Architecture research for: samstack pytest-xdist Docker coordination*
*Researched: 2026-04-30*

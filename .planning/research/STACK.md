# Technology Stack: pytest-xdist Integration

**Project:** samstack v2.3.0 — pytest-xdist support
**Researched:** 2026-04-30

## Recommended Stack

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest | ≥8.0 | Test framework (existing) | Already the samstack foundation. xdist is a pytest plugin. |
| pytest-xdist | ≥3.0 | Parallel test distribution | Provides `worker_id` fixture, `--numprocesses/-n`, worker process management. Optional peer dependency — samstack works without it. |
| filelock | ≥3.13 | Cross-process file locking | Canonical approach for xdist session-fixture coordination. Pure Python, zero system deps. Referenced directly in pytest-xdist documentation. |

### Infrastructure (unchanged)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| testcontainers-python | existing | Docker container lifecycle | Ryuk integration, `LocalStackContainer`, `DockerContainer`. gw0 only. |
| docker SDK | existing | Network management, container inspection | `_connect_container_with_alias`, `_disconnect_container_from_network`. gw0 only. |
| LocalStack | existing (image) | AWS service emulation | Shared across all workers via Docker network DNS. |
| AWS SAM CLI | existing (image) | Lambda local execution | Shared across all workers. One start-api + one start-lambda per session. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| boto3 | existing | AWS SDK for test assertions | All workers — each creates its own clients pointed at shared LocalStack |
| boto3-stubs | existing (dev) | Type stubs for boto3 | Development only — no runtime impact on xdist |

## New Dependency Details

### filelock

```bash
uv add filelock
```

**Why filelock specifically:**
- pytest-xdist documentation uses it in the canonical "session fixture once" example
- Pure Python — no compiled extensions, works on all platforms samstack supports
- Simple API: `FileLock(path).acquire()` / context manager
- Timeout support built-in: `FileLock(path, timeout=10)`
- No external daemon or service required

**Integration:** Used only in `samstack/fixtures/_xdist.py`. Consumers (downstream projects) do not need to install or configure it separately — it's a transitive dependency of samstack.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| File locking | `filelock` | `fasteners` | `fasteners` is also solid but `filelock` is what pytest-xdist docs use. Ecosystem consistency. |
| File locking | `filelock` | `portalocker` | Windows-focused. `filelock` has better cross-platform support and is more widely used. |
| Coordination | FileLock + JSON file | TCP socket server (gw0 listens, gw1+ connect) | Over-engineered. Adds port allocation, connection handling, serialization. Unnecessary when workers share a filesystem. |
| Coordination | FileLock + JSON file | `multiprocessing.Manager` | Tight coupling to CPython multiprocessing internals. Not portable to `pytest-xdist --dist=load` with SSH-based workers (theoretical). |
| Coordination | FileLock + JSON file | Environment variables | Cannot communicate Docker-mapped ports (dynamic, per-run). Environment variables are static. |
| Session fixture | Conditional fixture | `pytest_configure_node` hook + `workerinput` dict | `workerinput` is good for static config but doesn't handle async Docker startup. FileLock + polling is needed for "wait for gw0 to finish starting containers." |

## Installation

```bash
# Add to samstack's dependencies
uv add filelock

# pytest-xdist is an optional peer — downstream projects add it themselves:
# uv add --group dev pytest-xdist
```

## Sources

- [pytest-xdist How-to: FileLock for session fixtures](https://pytest-xdist.readthedocs.io/en/latest/how-to.html#making-session-scoped-fixtures-execute-only-once) — HIGH confidence: official docs
- [filelock PyPI](https://pypi.org/project/filelock/) — HIGH confidence: 3.13+ supports all needed features
- [pytest-xdist worker_id fixture](https://pytest-xdist.readthedocs.io/en/latest/how-to.html#identifying-the-worker-process-during-a-test) — HIGH confidence: official API
- [pytest-django xdist database suffixing](https://github.com/pytest-dev/pytest-django/blob/main/pytest_django/fixtures.py) — HIGH confidence: real-world integration pattern

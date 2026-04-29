# Domain Pitfalls: pytest-xdist with Docker-Based Fixtures

**Domain:** pytest plugin — Docker container lifecycle under parallel test execution
**Researched:** 2026-04-30

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Letting Every Worker Run Docker Teardown

**What goes wrong:** Each xdist worker gets its own copy of session-scoped fixtures. If every worker's `docker_network` fixture runs `_teardown_network()`, workers race to stop containers and remove the network. The first worker succeeds; the others get Docker API errors (network/container not found). Error noise floods the test output.

**Why it happens:** The existing fixture code uses `yield` + `finally` for teardown. Under xdist, every copy of the fixture runs this teardown. Developers may not realize each worker is independent.

**Consequences:** Spurious test failures from Docker API errors during teardown. Hard to debug because errors appear at session end, not during test execution. May mask real test failures.

**Prevention:** Only gw0/master runs teardown. gw1+ fixtures must use a separate code path with no teardown (`yield value` without cleanup). Pattern:
```python
if worker_id == "gw0":
    # Create + yield + teardown
    ...
elif worker_id == "master":
    # Standard path (existing code)
    ...
else:
    # gw1+: read from state, yield, NO teardown
    yield _read_state(...)
```
**Detection:** Integration test that runs `pytest -n 2` and asserts clean exit code 0. Check that gw1+ doesn't produce Docker error output.

### Pitfall 2: Worker 0 Crash Leaves gw1+ Hanging Indefinitely

**What goes wrong:** Worker 0 starts Docker containers and is about to write endpoints to the shared state file. Worker 0 crashes (OOM, Docker daemon failure, SAM CLI bug). Workers 1+ are polling `_read_state()` waiting for the state file. Without a timeout, they hang forever.

**Why it happens:** The coordination model is asynchronous — worker 0 produces state; workers 1+ consume it. No heartbeat or health check mechanism exists.

**Consequences:** CI pipeline hangs until killed by a global timeout (often 10+ minutes). Hard to diagnose — pytest appears stuck with no output.

**Prevention:** `_read_state()` must have a configurable timeout (default 120s). On timeout, raise a clear error: "Timed out waiting for worker 0 (gw0) to create shared infrastructure. Check gw0 logs." Worker 0 should also write an `"error"` key to the state file if Docker startup fails, so gw1+ can `pytest.skip()` with the error message instead of timing out.

**Detection:** Integration test: force worker 0 to fail (e.g., point `sam_image` at a non-existent image), run with `-n 2`, assert that gw1 exits within timeout with a clear skip message. Ryuk ensures Docker cleanup on crash.

### Pitfall 3: `sam_env_vars` Mutation Not Propagated to All Workers

**What goes wrong:** `make_lambda_mock` mutates `sam_env_vars` to inject `MOCK_SPY_BUCKET`, `MOCK_FUNCTION_NAME`, etc. Under xdist, each worker has its own `sam_env_vars` dict. If gw0 adds mock env vars but gw1+ doesn't, the `--env-vars` JSON file on gw1+ won't include the mock wiring. Lambda functions running in SAM won't receive the mock configuration.

**Why it happens:** `sam_env_vars` is a session-scoped fixture returning a mutable dict. `make_lambda_mock` mutates it. But xdist gives each worker its own dict instance. gw1+ workers may not have called `make_lambda_mock` with the same mock configuration.

**Consequences:** Tests on gw1+ that rely on Lambda mocks will fail because Lambda A (running in SAM) can't find the spy bucket or doesn't know it's being mocked. Inconsistent behavior between workers — mock-dependent tests pass on gw0, fail on gw1+.

**Prevention:** Two approaches:
1. **Shared mock initialization**: gw0 creates mock wiring, serializes the `sam_env_vars` mutations to shared state, and gw1+ applies the same mutations to their `sam_env_vars` dict before `sam_build` runs.
2. **gw0-only mock wiring**: Only gw0 calls `make_lambda_mock`. gw1+ tests that need mocks run on gw0 via `@pytest.mark.xdist_group`. Simpler but limits parallelism.

Recommended: Approach 1 for transparent compatibility. Approach 2 as a documented fallback.

**Detection:** Integration test with `-n 2` using the multi_lambda fixture. Assert that mock calls from Lambda A are visible to both gw0 and gw1 test assertions.

### Pitfall 4: SAM Build Runs on gw1+ Before gw0 Finishes

**What goes wrong:** All workers start simultaneously. If gw1+ reaches `sam_build` before gw0 has finished building, gw1+ may read incomplete build output or race with gw0's build process.

**Why it happens:** `sam_build` writes to `{project_root}/.aws-sam/` on the shared filesystem. xdist provides no built-in ordering guarantee for when workers resolve fixtures.

**Consequences:** gw1+ sees incomplete `.aws-sam/` directory. SAM start-api/start-lambda fails with build-related errors. Non-deterministic — works when gw0 is fast, fails when gw0 is slow.

**Prevention:** gw1+ must wait for gw0's build to complete before skipping. gw0 writes a "build_complete" flag to shared state after `sam_build` finishes. gw1+ polls for this flag with timeout. This is a variant of the FileLock pattern — gw0 writes state AFTER build; gw1+ reads before proceeding.

```python
# In sam_build fixture:
if worker_id == "gw0":
    run_sam_build()
    _write_state(tmp_path_factory, "build_complete", "true")
elif worker_id != "master":
    _read_state(tmp_path_factory, "build_complete", timeout=300.0)
```

**Detection:** Run with `-n 4`, add a deliberate slow step in gw0's build, verify gw1+ waits correctly.

## Moderate Pitfalls

### Pitfall 5: LocalStackContainer Object Not Available on gw1+

**What goes wrong:** Tests or fixtures that directly use `localstack_container` (the `LocalStackContainer` object) for operations beyond `get_url()` will fail on gw1+. The object doesn't exist on non-gw0 workers.

**Why it happens:** The `localstack_container` fixture yields the actual container object. On gw1+, there is no container to yield. The fixture must yield something else (e.g., the endpoint URL, or `None`).

**Prevention:** Refactor `localstack_container` to yield `None` (or a sentinel) on gw1+. All consumers should use `localstack_endpoint` (a string) instead of `localstack_container` (an object). If any internal samstack code uses `localstack_container` directly, refactor to use `localstack_endpoint`. Document that downstream projects should not depend on `localstack_container` in xdist mode.

**Detection:** Type checker (ty) will catch direct `localstack_container` usage if the return type changes.

### Pitfall 6: `docker_network_name` Collision Between Pytest Sessions

**What goes wrong:** Two concurrent pytest sessions (e.g., CI matrix builds on the same host) generate the same `samstack-{uuid8}` network name. Docker network creation fails with "network already exists."

**Why it happens:** `uuid4().hex[:8]` provides 32 bits of entropy — ~4 billion combinations. Collision probability is extremely low but non-zero. In CI environments with many concurrent runs, the birthday paradox reduces the effective space.

**Prevention:** Pre-existing issue, not xdist-specific. But xdist increases the number of concurrent pytest invocations, amplifying the risk. Consider using `uuid4().hex[:12]` (48 bits) or including a timestamp. Out of scope for v2.3.0 — document as known limitation.

### Pitfall 7: Port Conflicts Between SAM Containers and Host Services

**What goes wrong:** SAM start-api defaults to port 3000, start-lambda to port 3001. If another process on the host is using these ports, Docker port mapping fails.

**Why it happens:** These are the default ports in `SamStackSettings`. Under xdist, the risk is the same as non-xdist — only one SAM container per type starts per session.

**Prevention:** Users can override `api_port` and `lambda_port` in `[tool.samstack]`. No xdist-specific change needed. Document in xdist usage guide.

## Minor Pitfalls

### Pitfall 8: Ryuk Session ID Mismatch

**What goes wrong:** Ryuk (testcontainers' reaper) uses `SESSION_ID` to track containers. Under xdist, each worker process has its own `SESSION_ID`. gw0 creates containers with its session ID; gw1+ doesn't create testcontainers-managed containers.

**Prevention:** Only gw0 registers containers with Ryuk. gw1+ don't start testcontainers containers. Ryuk cleanup via network label still works because the network carries `LABEL_SESSION_ID`. SAM Lambda sub-containers attach to the labeled network, so Ryuk cascade still applies. No changes needed.

### Pitfall 9: log_dir Conflicts

**What goes wrong:** All workers write to the same `log_dir` (e.g., `logs/`). Worker 0's `stream_logs_to_file` writes to `localstack.log`, `start-api.log`, etc. gw1+ workers don't write these logs (they don't create containers), but if they did, they'd append to the same files.

**Prevention:** gw1+ doesn't create containers, so no log conflicts. If future features add per-worker logging, use `worker_id` to create separate log files (e.g., `logs/gw1-tests.log`). The xdist docs recommend this pattern.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Core coordination (`_xdist.py`) | FileLock platform compatibility (Windows vs Unix) | `filelock` handles this. Test on all platforms in CI. |
| Docker infra fixtures | `localstack_container` yielding on gw1+ | Use `localstack_endpoint` for all consumers; make `localstack_container` gw0-only |
| `sam_build` coordination | Race condition — gw1+ reads build output before gw0 finishes | Add `build_complete` flag to shared state; gw1+ polls for it |
| `make_lambda_mock` | `sam_env_vars` mutations not propagated to gw1+ | Serialize mock-wired env vars to shared state; gw1+ applies same mutations |
| Integration testing | xdist test discovery excludes samstack's own tests | Use `-n 2 --dist loadfile` with dedicated xdist test fixtures |
| Crash recovery | gw0 Docker failure leaves gw1+ hanging | Timeout + error-key in state file + `pytest.skip()` cascade |

## Sources

- [pytest-xdist How-to: session fixtures once](https://pytest-xdist.readthedocs.io/en/latest/how-to.html#making-session-scoped-fixtures-execute-only-once) — HIGH confidence: FileLock, race condition awareness
- [pytest-xdist worker environment variables](https://pytest-xdist.readthedocs.io/en/latest/how-to.html#identifying-workers-from-the-system-environment) — HIGH confidence: `PYTEST_XDIST_WORKER`, process title
- [pytest-django xdist database isolation](https://github.com/pytest-dev/pytest-django/blob/main/pytest_django/fixtures.py) — HIGH confidence: `workerinput["workerid"]` for per-worker resource suffixing
- [samstack CLAUDE.md](https://github.com/ivan-shcherbenko/samstack/CLAUDE.md) — HIGH confidence: existing fixture chain, Ryuk integration, SAM container lifecycle
- [samstack PROJECT.md](https://github.com/ivan-shcherbenko/samstack/.planning/PROJECT.md) — HIGH confidence: active requirements, out-of-scope decisions

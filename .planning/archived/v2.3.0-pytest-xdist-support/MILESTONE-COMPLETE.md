# Milestone Complete: v2.3.0 "pytest-xdist Support"

**Completed:** 2026-05-01
**Archive:** `.planning/archived/v2.3.0-pytest-xdist-support/`
**Plans shipped:** 9 plans across 5 phases (8-12)

## Goal

Enable downstream projects to run tests in parallel via pytest-xdist, with a single shared set of Docker infrastructure across all workers. Worker 0 manages all Docker lifecycle; workers 1+ read endpoint URLs from a shared JSON state file with FileLock coordination. Non-xdist backward compatibility preserved with zero user-facing changes.

## What Was Shipped

### Phase 8: Core Xdist Coordination (2 plans)
- `src/samstack/_xdist.py` — worker detection (`get_worker_id`, `is_controller`), shared state file I/O (`read_state_file`, `write_state_file`, `wait_for_state_key`), cross-process `FileLock` infrastructure lock (`acquire_infra_lock`, `release_infra_lock`), session UUID generation for state directory isolation
- `docker_network` xdist-aware: gw0 creates network + acquires lock, gw1+ polls state file and waits
- Unit tests: state file read/write, worker role detection, lock acquisition, skip cascade on error

### Phase 9: Docker Infra Xdist-Awareness (2 plans)
- `localstack_container` xdist-aware: gw0 creates LocalStack via `_LocalStackContainerProxy`, gw1+ reads endpoint from shared state
- `localstack_endpoint` passthrough: reading from shared state on gw1+ automatically unblocks all resource fixtures with zero changes to `resources.py`/`plugin.py`
- `sam_build` xdist-aware: gw0 runs `sam build` once, writes `build_complete` flag; gw1+ waits (300s timeout)
- Per-worker AWS resource isolation preserved via UUID4 per-call naming
- Bug fixes: `release_infra_lock()` added to docker_network exception path, `pytest.skip` → `pytest.fail` in `wait_for_state_key`, `container.stop()` wrapped in try/except in LocalStack finally block, removed redundant `is_controller` double-stubs from unit tests

### Phase 10: SAM API + Lambda Xdist-Awareness (2 plans)
- `sam_api` xdist-aware: gw0 starts SAM API container + pre-warms functions, writes endpoint to shared state; gw1+ polls and yields endpoint URL
- `sam_lambda_endpoint` xdist-aware: same pattern; `lambda_client` fixture works unchanged from all workers
- Warm container coordination: pre-warming runs once on gw0; warm containers serve all workers
- `sam_lambda_endpoint` added as dependency of `sam_api` to ensure both resolve on gw0
- Bug fix: unclosed HTTP response in `_pre_warm_api_routes` wrapped with `contextlib.closing()`

### Phase 11: Mock Coordination (1 plan)
- `make_lambda_mock` fixture xdist-aware: gw0 creates spy bucket + injects env vars; gw1+ reads bucket name from sam_env_vars + MOCK_FUNCTION_NAME
- `samstack.mock` spy buckets transparently shared across all workers
- Mock env vars (`MOCK_SPY_BUCKET`, `MOCK_FUNCTION_NAME`) correctly propagated to SAM containers

### Phase 12: Integration Testing, CI, Docs, Benchmarking (2 plans)
- `tests/xdist/test_basic.py` — 4 tests: GET/POST hello API, lambda_client.invoke, shared LocalStack
- `tests/xdist/test_resource_parallelism.py` — 4 tests: S3, DynamoDB, SQS, SNS concurrent read/write across workers
- `tests/xdist/test_crash/` — gw0 crash recovery: invalid image → gw1+ fails cleanly, no docker.errors leak
- `scripts/benchmark.py` — baseline vs `-n 2/4/auto` speedup table
- README `## Parallel testing with pytest-xdist` section — installation, usage, `--dist` modes table, CI YAML, known limitations (5 items)
- `.github/workflows/_ci.yml` — xdist integration tests (`-n 2`) + crash test in CI pipeline
- `pyproject.toml` — `pytest-xdist>=3.8.0` dev dependency
- Bug fixes found during test execution: session UUID shared via `PYTEST_XDIST_TESTRUNUID`, `sam_lambda_endpoint` resolved on gw0, `_wait_for_workers_done()` prevents premature gw0 teardown
- Code review fixes: cross-process TOCTOU race fixed via `FileLock` + atomic write-to-temp-then-rename, lock-failure fallback replaced with `pytest.fail()`

## Key Decisions & Discoveries

| Decision | Rationale |
|----------|-----------|
| `FileLock` + JSON state file (no TCP coordination server) | Simplest cross-process coordination; single new dependency (`filelock>=3.13`, already in project) |
| gw0-only teardown pattern | gw1+ fixtures yield without Docker lifecycle calls — prevents teardown races |
| `localstack_endpoint` passthrough from shared state | Unblocked all resource fixtures with zero code changes to `resources.py` or `plugin.py` |
| `_LocalStackContainerProxy` with `get_url()`/`stop()` | Transparent to all downstream fixtures — no changes to boto3 clients |
| 300s `build_complete` timeout | Cold-cache SAM builds with Docker pulls need extended wait (vs 120s default) |
| UUID4 per-call naming for resources | Preserves per-worker AWS resource isolation without code changes to `resources.py` |
| `pytest.fail()` instead of `pytest.skip()` on gw0 failure | CI must see infrastructure failures as red, not silently green |
| `--dist=load` and `--dist=worksteal` supported; `each`/`no` not | Documented limitation — samstack requires shared fixtures, not per-worker copies |

## Bugs Fixed During Milestone

1. **Cross-process TOCTOU race in `write_state_file`** (Phase 12 review) — `threading.Lock` replaced with `filelock.FileLock` + atomic write (tempfile + os.replace)
2. **`release_infra_lock()` missing in docker_network exception path** (Phase 9 review) — lock could be orphaned if network creation failed after acquisition
3. **`pytest.skip()` on gw0 failure masked infra errors in CI** (Phase 9 review) — changed to `pytest.fail()` so failures surface as red
4. **`container.stop()` exception in finally block suppressed original errors** (Phase 9 review) — wrapped in try/except with warnings.warn
5. **Unclosed HTTP response in `_pre_warm_api_routes`** (Phase 10 review) — wrapped with `contextlib.closing()`
6. **Session UUID not shared across xdist workers** (Phase 12 execution) — `get_session_uuid()` now reads `PYTEST_XDIST_TESTRUNUID`
7. **`sam_lambda_endpoint` not resolved on gw0** (Phase 12 execution) — added as dependency of `sam_api` fixture
8. **Premature gw0 teardown** (Phase 12 execution) — `_wait_for_workers_done()` polls for `gwN_done` keys before stopping containers
9. **`docker_network` lock-failure fallback yielded uncreated network** (Phase 12 review) — replaced with `pytest.fail()` descriptive error
10. **`SqsQueue.arn` used but doesn't exist** (Phase 12 execution) — switched to `get_queue_attributes`
11. **Redundant `is_controller` double-stubs in unit tests** (Phase 9 review) — removed to let real logic execute
12. **Dependency inversion in `docker_network_name`** (Phase 9 review) — moved gw1+ `wait_for_state_key` into `docker_network` fixture

## Outstanding Items

| Item | Status | Phase | Notes |
|------|--------|-------|-------|
| HUMAN-UAT: basic xdist tests `-n 2` | Pending | 12 | Requires Docker daemon + SAM image pull |
| HUMAN-UAT: resource parallelism `-n 4` | Pending | 12 | Requires Docker + 4 workers sharing LocalStack |
| HUMAN-UAT: crash recovery test | Pending | 12 | Linux + Docker-in-Docker + Ryuk required; macOS skips |
| HUMAN-UAT: benchmark script | Pending | 12 | Requires Docker; ~5-15 min runtime |
| HUMAN-UAT: no dangling containers post-crash | Pending | 12 | Requires Docker socket inspection |
| VERIFICATION: `human_needed` status | Acknowledged | 12 | All 6 truths verified statically; 5 Docker tests pending manual run |

## Archive Contents

```
.planning/archived/v2.3.0-pytest-xdist-support/
├── 08-core-xdist-coordination/       (2 plans, 2 summaries, research, context)
├── 09-docker-infra-xdist-awareness/   (2 plans, 2 summaries, review, review-fix, research, security, UAT, validation)
├── 10-sam-api-lambda-xdist-awareness/ (2 plans, 2 summaries, context, discussion-log, review, review-fix)
├── 11-mock-coordination/             (1 plan, 1 summary, context, discussion-log, research, validation)
├── 12-integration-testing-ci-docs-benchmarking/ (2 plans, 2 summaries, context, discussion-log, research, review, review-fix, HUMAN-UAT, VERIFICATION)
├── REQUIREMENTS.md
├── ROADMAP-v2.3.0.md
├── STATE-v2.3.0.md
└── MILESTONE-COMPLETE.md
```

---

*Milestone completed 2026-05-01. Total: 20 plans across 12 phases across 3 milestones (v2.0.0, v2.2.0, v2.3.0).*

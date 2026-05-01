---
phase: 12-integration-testing-ci-docs-benchmarking
plan: 01
subsystem: xdist-integration-tests
tags: [xdist, integration-testing, crash-recovery, resource-isolation, docker]
requires:
  - Phase 08 (core-xdist-coordination)
  - Phase 09 (docker-infra-xdist-awareness)
  - Phase 10 (sam-api-lambda-xdist-awareness)
provides:
  - xdist integration test suite (TEST-01, TEST-03)
  - xdist crash recovery test (TEST-02)
  - root conftest xdist ignore hook
affects:
  - src/samstack/_xdist.py (session UUID sharing fix)
  - src/samstack/fixtures/localstack.py (teardown coordination)
  - src/samstack/fixtures/sam_api.py (sam_lambda_endpoint dependency)
  - tests/conftest.py (xdist ignore hook)
tech-stack:
  added: [pytest-xdist 3.8.0]
  patterns: [subprocess crash verification, UUID-based resource isolation, xdist teardown coordination]
key-files:
  created:
    - tests/xdist/conftest.py (xdist suite configuration)
    - tests/xdist/test_basic.py (4 basic xdist tests)
    - tests/xdist/test_resource_parallelism.py (4 resource parallelism tests)
    - tests/xdist/test_crash/conftest.py (crash test conftest)
    - tests/xdist/test_crash/test_infra_trigger.py (infra trigger for crash)
    - tests/xdist/test_crash/test_crash.py (subprocess crash verification)
  modified:
    - src/samstack/_xdist.py (session UUID fix)
    - src/samstack/fixtures/localstack.py (teardown coordination, import fix)
    - src/samstack/fixtures/sam_api.py (add sam_lambda_endpoint dependency)
    - tests/unit/test_xdist_sam_api.py (update for new signature)
    - tests/conftest.py (add xdist to ignore hook)
    - pyproject.toml (pytest-xdist dep)
    - uv.lock (pytest-xdist dep)
decisions:
  - "Use PYTEST_XDIST_TESTRUNUID env var for cross-worker session UUID sharing instead of per-process UUID generation"
  - "Make sam_api depend on sam_lambda_endpoint to ensure gw0 always starts Lambda runtime for gw1+ workers"
  - "Implement _wait_for_workers_done() coordination in localstack_container teardown to prevent premature infrastructure shutdown"
  - "Use get_queue_attributes API instead of non-existent SqsQueue.arn property for SQS→SNS subscription"
duration: 420s
completed: 2026-05-01
---

# Phase 12 Plan 01: xdist Integration Test Suite Summary

**One-liner:** End-to-end xdist integration tests validating shared Docker infrastructure, per-worker resource isolation, and crash recovery — plus three bug fixes to the xdist coordination layer discovered during test execution.

## Completed Tasks

| Task | Name                                     | Commit   | Files                                                  |
|------|------------------------------------------|----------|--------------------------------------------------------|
| 1    | Create xdist integration conftest and basic tests | c96af6b  | `tests/xdist/conftest.py`, `tests/xdist/test_basic.py` |
| 2    | Create resource parallelism tests        | 08ccfb7  | `tests/xdist/test_resource_parallelism.py`             |
| 3    | Create crash recovery test and update root conftest | f17a377  | `tests/xdist/test_crash/*.py`, `tests/conftest.py`     |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Session UUID not shared across xdist workers**
- **Found during:** Task 1 (first `-n 2` test run)
- **Issue:** Each xdist worker process generated its own `uuid.uuid4()` session UUID, creating separate state directories (`/tmp/samstack-<different-uuid>/`). gw0 wrote infrastructure keys to its own directory; gw1 never saw them.
- **Fix:** Modified `get_session_uuid()` in `_xdist.py` to check `PYTEST_XDIST_TESTRUNUID` environment variable (set by pytest-xdist on all worker subprocesses). When present, uses the shared testrun UID (truncated to 8 hex chars) instead of generating a new UUID.
- **Files modified:** `src/samstack/_xdist.py`
- **Commit:** c96af6b

**2. [Rule 1 - Bug] sam_lambda_endpoint never resolved on gw0**
- **Found during:** Task 1 (gw1 timed out waiting for `sam_lambda_endpoint`)
- **Issue:** `sam_api` and `sam_lambda_endpoint` were independent session-scoped fixtures. gw0's test allocation included only API tests (`test_get_hello_from_sam_api`, `test_post_hello_writes_to_s3`), so `sam_lambda_endpoint` was never resolved on gw0. gw1 waited 120s for a state key that was never written.
- **Fix:** Added `sam_lambda_endpoint` as a dependency of `sam_api` in `sam_api.py`. This ensures whenever `sam_api` is resolved (which happens for API tests), `sam_lambda_endpoint` is also resolved, and gw0 writes both endpoints to shared state.
- **Files modified:** `src/samstack/fixtures/sam_api.py`, `tests/unit/test_xdist_sam_api.py` (updated test signatures)
- **Commit:** c96af6b

**3. [Rule 2 - Auto-add missing critical functionality] Premature gw0 teardown under xdist**
- **Found during:** Task 1 (gw1 `ConnectionRefusedError` to LocalStack)
- **Issue:** gw0 finished its 2 tests quickly and its session fixture teardown stopped the LocalStack container. gw1 was still resolving fixtures and trying to use LocalStack — got `ConnectionRefusedError` because the container was already gone. The teardown had no cross-worker coordination.
- **Fix:** Implemented `_wait_for_workers_done()` in `localstack.py`. gw1+ workers write `{worker_id}_done` to shared state when their `localstack_container` fixture teardown fires. gw0's `localstack_container` finally block calls `_wait_for_workers_done()` (polling for all `gwN_done` keys, 300s timeout) before stopping the container and disconnecting from the network.
- **Files modified:** `src/samstack/fixtures/localstack.py`
- **Commit:** c96af6b

**4. [Rule 1 - Bug] Missing imports for acquire_infra_lock/release_infra_lock**
- **Found during:** Task 1 (LSP errors in localstack.py)
- **Issue:** `acquire_infra_lock` and `release_infra_lock` were used in `docker_network` fixture but not imported from `_xdist.py`. Pre-existing bug — code worked at runtime but caused type checker errors.
- **Fix:** Added `acquire_infra_lock` and `release_infra_lock` to the import from `samstack._xdist`.
- **Files modified:** `src/samstack/fixtures/localstack.py`
- **Commit:** c96af6b

**5. [Rule 3 - Auto-fix blocking] SqsQueue.arn property does not exist**
- **Found during:** Task 2 (SNS test implementation)
- **Issue:** The plan's example used `sqs_queue.arn` to get the queue ARN for SNS subscription, but `SqsQueue` class has no `arn` property.
- **Fix:** Used `sqs_client.get_queue_attributes(QueueUrl=sqs_queue.url, AttributeNames=["QueueArn"])` to retrieve the ARN. Added `sqs_client` fixture parameter to the test.
- **Files modified:** `tests/xdist/test_resource_parallelism.py`
- **Commit:** 08ccfb7

**6. [Rule 2 - Auto-add missing critical functionality] Crash test directory lacks trigger test**
- **Found during:** Task 3 (crash test implementation)
- **Issue:** The crash test conftest alone doesn't trigger infrastructure resolution — without a test that uses a samstack fixture, gw0 never tries to start Docker containers with the invalid image.
- **Fix:** Created `tests/xdist/test_crash/test_infra_trigger.py` with a minimal test that depends on `sam_api`. The crash test's subprocess uses `-k test_trigger_docker_infra` to run only this trigger test, avoiding infinite recursion into the subprocess-launching test itself.
- **Files modified:** `tests/xdist/test_crash/test_infra_trigger.py`, `tests/xdist/test_crash/test_crash.py`
- **Commit:** f17a377

## Verification Results

```bash
# TEST-01: xdist basic integration tests
uv run pytest tests/xdist/test_basic.py -v -n 2 --timeout=600
# → 4 passed in 8.78s

# TEST-03: resource parallelism
uv run pytest tests/xdist/test_resource_parallelism.py -v -n 4 --timeout=300
# → 4 passed in 5.70s

# TEST-02: crash recovery (skipped on macOS)
uv run pytest tests/xdist/test_crash/test_crash.py -v --timeout=300
# → 1 skipped (darwin + non-Ryuk)

# Backward compatibility: existing integration tests
uv run pytest tests/ -v --timeout=300 \
  --ignore=tests/unit --ignore=tests/warm \
  --ignore=tests/multi_lambda --ignore=tests/xdist \
  --ignore=tests/integration/test_warm_crash.py
# → 62 passed, 1 skipped in 24.14s

# Lint/format/type check
uv run ruff check tests/xdist/ tests/conftest.py  # → All checks passed!
uv run ruff format --check tests/xdist/ tests/conftest.py  # → 7 files already formatted
uv run ty check tests/conftest.py  # → All checks passed!

# All 155 unit tests still pass
uv run pytest tests/unit/ -v  # → 155 passed in 1.04s
```

## Threat Flags

No new threat surface introduced beyond what the plan's threat model covers. The crash test's subprocess timeout (`timeout + 30s`) and `proc.kill()` fallback mitigate zombie process risk (T-12-01). No secrets, credentials, or production endpoints in test code.

## Self-Check

- [x] All created files exist at expected paths
- [x] All 3 commits confirmed: c96af6b, 08ccfb7, f17a377
- [x] No stubs detected in new or modified files
- [x] All 155 unit tests pass
- [x] All 62 existing integration tests pass (no regressions)
- [x] xdist basic tests: 4/4 pass with `-n 2`
- [x] xdist resource parallelism: 4/4 pass with `-n 4`
- [x] Crash test skips correctly on macOS (test code verified)
- [x] Root conftest `pytest_ignore_collect` includes `"xdist"`
- [x] Ruff check, format check, and ty check all pass

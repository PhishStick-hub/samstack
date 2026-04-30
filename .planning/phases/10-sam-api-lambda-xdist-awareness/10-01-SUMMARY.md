---
phase: 10-sam-api-lambda-xdist-awareness
plan: 01
subsystem: infra
tags: [xdist, pytest, sam, docker, fixtures]

# Dependency graph
requires:
  - phase: 09-docker-infra-xdist-awareness
    provides: "gw0-create/gw1+-wait pattern, _xdist module (get_worker_id, is_controller, write_state_file, wait_for_state_key), shared state coordination"
provides:
  - "Xdist-aware sam_api fixture: gw0 starts single SAM start-api container, gw1+ workers yield endpoint URL from shared state"
  - "Unit test suite covering master, gw0 (success + 2 error paths), gw1+ (success + return) — 7 tests"
affects: [sam_lambda_xdist, warm_container_xdist, mock_xdist]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "gw0-create/gw1+-wait for SAM service containers — gw0 starts container, writes endpoint to shared state; gw1+ polls and yields"
    - "gw1+ no-teardown pattern — yields endpoint and returns without any Docker lifecycle calls"

key-files:
  created:
    - tests/unit/test_xdist_sam_api.py
  modified:
    - src/samstack/fixtures/sam_api.py

key-decisions:
  - "Followed Phase 9 gw0-create/gw1+-wait pattern exactly — no proxy class needed since sam_api already yields str (per D-01, D-02)"
  - "gw0 writes sam_api_endpoint after pre-warm succeeds; gw1+ polls with 120s timeout (per D-03, D-04, D-06)"
  - "gw1+ yields endpoint and returns immediately — no Docker lifecycle calls (per D-05)"
  - "Pre-warm failure on gw0 writes error key to shared state and re-raises SamStartupError (per D-07)"
  - "Master path (plain pytest) preserves existing behavior — container starts/stops normally, no state file writes"

patterns-established:
  - "SAM container xdist branching: worker_id = get_worker_id(); if not is_controller(worker_id): wait → yield → return; else: try/with/except with write_state_file on gw0"
  - "gw1+ 120s endpoint timeout matches localstack_endpoint timeout (consistent across Phase 9/10)"

requirements-completed: [SERV-01, SERV-04]

# Metrics
duration: 6min
completed: 2026-04-30
---

# Phase 10 Plan 01: SAM API Xdist Awareness Summary

**Xdist-aware sam_api fixture with gw0-create/gw1+-wait pattern — one shared SAM start-api container for all xdist workers, no proxy class needed**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-30T22:51:43Z
- **Completed:** 2026-04-30T22:57:57Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `sam_api` fixture now branches on worker ID: gw0/master starts container + pre-warms; gw1+ polls shared state and yields URL
- gw0 writes `sam_api_endpoint` to shared state after container starts and pre-warm succeeds — gw1+ benefits from warm containers automatically
- gw0 writes `error` key on any failure (container or pre-warm), triggering `pytest.fail()` on all gw1+ workers
- master path (plain pytest) preserves existing behavior unchanged — container lifecycle is identical to before
- 7 unit tests covering all 3 worker paths (master, gw0, gw1+) and error cases

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests** - `2204440` (test): 7 failing tests for master, gw0, gw1+ paths
2. **Task 1 (GREEN): Implement xdist branching** - `045ace9` (feat): fixture implementation + test fixes — all 7 pass

_Note: Task 2 (test file creation) was completed during Task 1's TDD cycle — the full 7-test suite was written and committed as part of the RED/GREEN phases._

## Files Created/Modified
- `src/samstack/fixtures/sam_api.py` - Added xdist branching to `sam_api` fixture: gw0/gw1+ split, state file coordination, error handling
- `tests/unit/test_xdist_sam_api.py` - 7 unit tests across 3 classes (TestSamApiMaster, TestSamApiGw0, TestSamApiGw1Plus)

## Decisions Made
- No proxy class needed for `sam_api` — fixture already yields `str` (endpoint URL), so gw1+ simply does `wait_for_state_key("sam_api_endpoint")` and yields the string (per D-02)
- Followed `sam_build` Phase 9 pattern exactly: `if not is_controller()` → wait + yield + return; `else:` → try/with/except with `write_state_file`
- 120s timeout on gw1+ endpoint wait — consistent with `localstack_endpoint` timeout (per D-04)
- Preserved all existing helpers unchanged: `_filter_warm_routes`, `_pre_warm_api_routes`, `warm_api_routes` fixture, `sam_api_extra_args` fixture

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mock lambdas missing `**kwargs` parameter**
- **Found during:** Task 1 (GREEN phase — implementing to pass tests)
- **Issue:** Test mocks for `_run_sam_service` used `lambda *a:` but the real function receives keyword arguments (`settings=...`, `docker_network=...`, etc.), causing `TypeError: got an unexpected keyword argument 'settings'`
- **Fix:** Changed all mock lambdas from `lambda *a:` to `lambda *a, **kw:` in 4 test locations
- **Files modified:** `tests/unit/test_xdist_sam_api.py`
- **Verification:** All 7 tests pass after fix; 5 previously failing tests now pass
- **Committed in:** `045ace9` (GREEN commit — included alongside implementation)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test mock signature fix — essential for tests to exercise the fixture correctly. No scope creep.

## Issues Encountered
- None beyond the mock signature fix documented above.

## Verification

```bash
# Unit tests (all pass)
uv run pytest tests/unit/test_xdist_sam_api.py -v
# Result: 7 passed

# Existing integration tests (backward compatibility verified)
uv run pytest tests/test_sam_api.py -v --timeout=300
# Result: 2 passed (test_get_hello, test_unknown_path_returns_4xx)

# Lint + type check (clean)
uv run ruff check src/samstack/fixtures/sam_api.py tests/unit/test_xdist_sam_api.py
# Result: All checks passed!
uv run ty check src/samstack/fixtures/sam_api.py
# Result: All checks passed!
```

## User Setup Required
None — no external service configuration required. All xdist behavior is automatic via worker ID detection.

## Next Phase Readiness
- `sam_api` xdist support complete — next: `sam_lambda_endpoint` xdist awareness (Plan 10-02)
- `lambda_client` fixture (depends on `sam_lambda_endpoint`) will work transparently once 10-02 completes
- Warm container coordination is handled: gw0 pre-warms before writing endpoint, gw1+ benefits automatically

---
*Phase: 10-sam-api-lambda-xdist-awareness*
*Completed: 2026-04-30*

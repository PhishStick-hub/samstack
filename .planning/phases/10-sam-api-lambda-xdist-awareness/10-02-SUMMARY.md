---
phase: 10-sam-api-lambda-xdist-awareness
plan: 02
subsystem: infra
tags: [pytest-xdist, sam-local, start-lambda, shared-state, gw0-gw1]

# Dependency graph
requires:
  - phase: 08-xdist-shared-state
    provides: get_worker_id, is_controller, write_state_file, wait_for_state_key
  - phase: 09-docker-infra-xdist-awareness
    provides: sam_build xdist pattern (gw0-create/gw1+-wait), docker_network xdist-aware
provides:
  - xdist-aware sam_lambda_endpoint fixture with gw0/gw1+ branching
  - gw0 writes sam_lambda_endpoint URL to shared state after pre-warm
  - gw1+ polls shared state and yields endpoint without Docker calls
  - lambda_client works transparently on all workers via pytest DI
affects: [10-04-samstack-mock-xdist, 10-05-e2e-xdist-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "gw0-create/gw1+-wait pattern for SAM service containers (identical to Plan 01 sam_api)"
    - "Iterator[str] fixture yielding endpoint URL string (no proxy class needed)"
    - "Pre-warm failure writes error key + re-raises SamStartupError"

key-files:
  created:
    - tests/unit/test_xdist_sam_lambda.py (8 tests, 3 test classes, no Docker needed)
  modified:
    - src/samstack/fixtures/sam_lambda.py (xdist branching added, lambda_client unchanged)

key-decisions:
  - "Followed Plan 01 sam_api pattern exactly — same gw0/gw1+ split, same state key naming convention, same error handling"
  - "lambda_client fixture requires zero code changes — works automatically via pytest DI when sam_lambda_endpoint resolves on gw1+"
  - "Master path (plain pytest) preserves existing behavior unchanged — no state file writes"

patterns-established:
  - "sam_lambda_endpoint xdist pattern: gw0 starts SAM container + pre-warms + writes endpoint; gw1+ waits + yields"
  - "Unit test pattern: __wrapped__ access + MagicMock + monkeypatch for testing xdist fixture branching without Docker"

requirements-completed: [SERV-02, SERV-03, SERV-04]

# Metrics
duration: 12min
completed: 2026-05-01
---

# Phase 10 Plan 02: sam_lambda_endpoint xdist-aware summary

**SAM Lambda endpoint shared across xdist workers — gw0 starts container + pre-warms Lambda functions, writes URL to shared state; gw1+ yields URL without Docker calls**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-01T00:10:00Z
- **Completed:** 2026-05-01T00:22:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- sam_lambda_endpoint fixture now splits on is_controller(worker_id): gw0/master starts container + pre-warms, gw1+ polls shared state with 120s timeout
- gw0 writes sam_lambda_endpoint URL to shared state after container start + pre-warm success
- gw0 writes error key on container or pre-warm failure, re-raises SamStartupError
- lambda_client fixture unchanged — works transparently on all workers via pytest dependency injection
- 8 unit tests covering master (3), gw0 (3), gw1+ (2) — all pass without Docker
- Existing integration tests (tests/test_sam_lambda.py) still pass — backward compatibility verified

## Task Commits

Each task was committed atomically:

1. **Task 1: Add xdist branching to sam_lambda_endpoint fixture** (TDD)
   - `c86d772` (test): add failing test for sam_lambda_endpoint xdist branching (RED)
   - `1460d6c` (feat): implement xdist branching for sam_lambda_endpoint fixture (GREEN)
2. **Task 2: Create unit tests for sam_lambda_endpoint xdist branching** — tests created in Task 1's RED phase, all 8 pass, no additional changes needed

## Files Created/Modified
- `tests/unit/test_xdist_sam_lambda.py` — 8 unit tests across 3 classes (TestSamLambdaEndpointMaster, TestSamLambdaEndpointGw0, TestSamLambdaEndpointGw1Plus)
- `src/samstack/fixtures/sam_lambda.py` — xdist imports added, sam_lambda_endpoint fixture body replaced with gw0/gw1+ branching; lambda_client, _warm_containers_mode, _pre_warm_functions, sam_lambda_extra_args preserved as-is

## Decisions Made
- Followed Plan 01 sam_api pattern exactly — same try/except structure, same error key convention, same 120s timeout for gw1+ wait
- Did not extract shared SAM container xdist logic into a helper — each fixture (sam_api, sam_lambda_endpoint) has nearly identical branching code, but refactoring was not in plan scope
- lambda_client fixture confirmed to work unchanged — depends on sam_lambda_endpoint via pytest DI; gw1+ resolution of sam_lambda_endpoint automatically makes lambda_client work

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered
- Mock context manager setup required wrapper function (`_service_wrapper`) because `@contextmanager`-decorated functions return `ContextDecorator` instances that don't accept keyword arguments when called as instances. Resolved by wrapping in a lambda/closure that accepts kwargs and returns a fresh context manager. Normal TDD iteration during test development.

## Threat Flags

None — all security surface already documented in Phase 8 (shared state file) and Plan 10-02 threat model (T-10-05 through T-10-08).

## Known Stubs

None — fixture is complete, no TODO/FIXME/placeholder values.

## User Setup Required

None — fixture works automatically via pytest plugin registration. Users benefit from xdist awareness without any configuration changes.

## Next Plan Readiness
- Plan 10-03 (warm container coordination) can use sam_lambda_endpoint from this plan — gw0 pre-warms before writing endpoint, gw1+ gets warm containers
- samstack.mock xdist compatibility (future plan) can rely on lambda_client working on all workers
- E2E xdist integration tests (future plan) can verify multi-worker Lambda invoke flow

---
*Phase: 10-sam-api-lambda-xdist-awareness*
*Completed: 2026-05-01*

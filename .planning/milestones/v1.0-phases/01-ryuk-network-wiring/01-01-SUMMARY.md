---
phase: 01-ryuk-network-wiring
plan: "01"
subsystem: infra
tags: [testcontainers, ryuk, docker, pytest-fixture]

# Dependency graph
requires: []
provides:
  - "docker_network fixture labels networks with LABEL_SESSION_ID/SESSION_ID for Ryuk reaper"
  - "Ryuk TCP socket registration of bridge network via network=name=<name> filter"
  - "ryuk_disabled guard (testcontainers_config) for CI environments"
  - "Unit tests for Ryuk-enabled and Ryuk-disabled paths (TEST-01, TEST-02)"
affects: [01-02-ryuk-crash-test]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Ryuk registration via Reaper.get_instance() + Reaper._socket.send() before yield"
    - "testcontainers_config.ryuk_disabled gate for CI-safe fixture code"
    - "None-guard on Reaper._socket before send (ty-enforced correctness)"
    - "pytest fixture unit-tested via __wrapped__ for direct generator invocation"

key-files:
  created:
    - tests/unit/test_docker_network.py
  modified:
    - src/samstack/fixtures/localstack.py

key-decisions:
  - "Added if Reaper._socket is not None guard before .send() — ty flagged _socket as Optional[socket]; guard is a correctness requirement, not a workaround"
  - "Followed D-01 through D-07 execution order exactly as specified in CONTEXT.md"
  - "stacklevel=2 on warnings.warn for Ryuk socket failure — matches established project baseline"

patterns-established:
  - "Ryuk registration pattern: get_instance() then None-guarded _socket.send() in try/except with warnings.warn"
  - "Unit test fixture invocation: fixture.__wrapped__(args) for session-scoped fixtures"

requirements-completed: [RYUK-01, RYUK-02, RYUK-03, RYUK-04, RYUK-05, TEST-01, TEST-02]

# Metrics
duration: 2min
completed: "2026-04-23"
---

# Phase 1 Plan 01: Ryuk Network Wiring Summary

**Docker bridge network labeled with testcontainers session-id and registered with Ryuk TCP socket, gated behind ryuk_disabled, with 5 unit tests covering enabled/disabled paths.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-23T17:57:03Z
- **Completed:** 2026-04-23T17:59:17Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Modified `docker_network` fixture to label networks with `LABEL_SESSION_ID: SESSION_ID` at creation
- Added Ryuk TCP socket registration (`network=name=<name>\r\n` filter) gated by `testcontainers_config.ryuk_disabled`
- Created 5 unit tests covering label injection, socket send, warn-not-raise on failure, and ryuk_disabled bypass
- All 86 existing unit tests continue to pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire Ryuk into docker_network fixture** - `6b68e79` (feat)
2. **Task 2: Unit tests for Ryuk-enabled and Ryuk-disabled paths** - `66ab52e` (test)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified

- `src/samstack/fixtures/localstack.py` - Added 3 imports + Ryuk wiring block inside `docker_network`; labels, socket send, None guard, warn-on-failure, ryuk_disabled gate
- `tests/unit/test_docker_network.py` - 5 unit tests: `TestDockerNetworkRyukEnabled` (3 tests) and `TestDockerNetworkRyukDisabled` (2 tests)

## Decisions Made

- Added `if Reaper._socket is not None:` guard before `.send()` — `ty` correctly flagged `Reaper._socket` as `Optional[socket]`; calling `.send()` on `None` would raise `AttributeError` at runtime, so this is a Rule 2 correctness fix, not an escape hatch
- All decisions D-01 through D-07 from CONTEXT.md followed exactly as specified

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added None guard on Reaper._socket before .send()**
- **Found during:** Task 1 (Wire Ryuk into docker_network fixture)
- **Issue:** `ty` type checker flagged `Reaper._socket` as `Optional[socket]`. The plan's target shape called `.send()` directly on `Reaper._socket` without a None check. After `Reaper.get_instance()` completes successfully it sets `_socket`, but a failed connection leaves it as `None`. Calling `.send()` on `None` raises `AttributeError` uncaught by the outer `except Exception`.
- **Fix:** Added `if Reaper._socket is not None:` guard around `Reaper._socket.send(...)`. The existing `except Exception` still catches any `OSError` from the send itself.
- **Files modified:** `src/samstack/fixtures/localstack.py`
- **Verification:** `uv run ty check` passes; unit test `test_ryuk_socket_send_called` verifies send is called when socket is non-None; `test_socket_failure_warns_not_raises` verifies OSError path still warns
- **Committed in:** `6b68e79` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing null check)
**Impact on plan:** Correctness fix; no scope change. Unit tests adjusted to patch `_socket` as a non-None MagicMock, matching the guard's expectations.

## Issues Encountered

None — plan executed cleanly. `ruff format` required one auto-format pass after initial edit.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The Ryuk TCP socket send is existing infrastructure (same socket testcontainers uses internally). T-01-02 mitigated as planned: try/except + warnings.warn around send.

## Known Stubs

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 01-01 complete; Ryuk wiring for `docker_network` in place
- Plan 01-02 (crash test / TEST-03) can proceed: network is labeled and registered, ready for empirical SIGKILL verification
- Blocker from STATE.md still applies: SAM Lambda sub-container cascade on network removal is empirically unverified — 01-02 crash test must confirm

---
*Phase: 01-ryuk-network-wiring*
*Completed: 2026-04-23*

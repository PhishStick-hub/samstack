---
phase: 02-container-level-ryuk-verification
plan: 01
subsystem: testing
tags: [testcontainers, ryuk, docker, localstack, sam]

requires:
  - phase: 01-test-infrastructure
    provides: localstack_container, sam_api, sam_lambda_endpoint fixtures
provides:
  - Ryuk session label assertions on LocalStack container (get_wrapped_container path)
  - Ryuk session label assertions on SAM API container (Docker SDK list query)
  - Ryuk session label assertions on SAM Lambda container (Docker SDK list query)
affects: [ryuk, cleanup, docker, containers]

tech-stack:
  added: []
  patterns: ["Docker SDK containers.list() filtered by SESSION_ID label + Cmd inspection"]

key-files:
  created:
    - tests/integration/test_ryuk_container_labels.py
    - tests/test_ryuk_sam_labels.py
  modified: []

key-decisions:
  - "LocalStack label check uses get_wrapped_container() + reload() + .labels (direct container handle)"
  - "SAM container label checks use Docker SDK containers.list(filter by SESSION_ID) + Cmd inspection (no direct handle needed)"
  - "Sub-container cascade (Lambda DinD children) explicitly not asserted per D-07"
  - "No sys.platform skip on SAM label tests (label inspection works cross-platform)"

patterns-established:
  - "Ryuk label test pattern: module-level pytestmark skip on ryuk_disabled, belt-and-suspenders body skip"

requirements-completed: [PHASE-02-GOAL]

duration: 8min
completed: 2026-04-24
---

# Phase 02: Container-Level Ryuk Verification Summary

**Two test files empirically verify org.testcontainers.session-id labels on all three samstack container fixture types: LocalStack, SAM API, and SAM Lambda**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-24
- **Completed:** 2026-04-24
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- LocalStack container label assertion via `get_wrapped_container()` returning correct `SESSION_ID`
- SAM API container label assertion via Docker SDK `containers.list()` filtered by `org.testcontainers.session-id` label
- SAM Lambda container label assertion via same Docker SDK query pattern
- All tests skip cleanly when `TESTCONTAINERS_RYUK_DISABLED=true`

## Task Commits

Files created but not committed (awaiting user commit instruction).

## Files Created
- `tests/integration/test_ryuk_container_labels.py` — LocalStack Ryuk label assertion, integration session, get_wrapped_container + reload + labels
- `tests/test_ryuk_sam_labels.py` — SAM API and SAM Lambda Ryuk label assertions, top-level session, Docker SDK containers.list query

## Decisions Made
- Used `get_wrapped_container()` for LocalStack (direct handle available), Docker SDK list query for SAM (no direct handle exposed through fixtures)
- Belt-and-suspenders Ryuk-disabled skip: module-level pytestmark + body-level manual skip matching existing `test_ryuk_crash.py` pattern
- No type suppression needed — `from __future__ import annotations` + TYPE_CHECKING guard for `docker.models.containers` import

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None — all tests passed on first run.

## Next Phase Readiness

- D-01 through D-07 all covered by test assertions
- No blockers for subsequent phases

---
*Phase: 02-container-level-ryuk-verification*
*Completed: 2026-04-24*

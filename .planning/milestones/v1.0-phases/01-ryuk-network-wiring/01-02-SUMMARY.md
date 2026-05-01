---
phase: 01-ryuk-network-wiring
plan: "02"
subsystem: infra
tags: [testcontainers, ryuk, docker, pytest-integration, crash-test]

# Dependency graph
requires:
  - "01-01: docker_network labeled with LABEL_SESSION_ID/SESSION_ID for Ryuk"
provides:
  - "Automated crash test (TEST-03): SIGKILL subprocess, poll Docker for NotFound on labeled network"
  - "CI-safe skip via pytestmark when TESTCONTAINERS_RYUK_DISABLED=true"
  - "Sub-container cascade behavior documented in test output"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "subprocess.Popen + os.kill(pid, SIGKILL) + proc.wait() for subprocess crash simulation"
    - "docker.from_env().networks.list(filters={'label': '...'}) to find Ryuk-labeled network"
    - "Poll loop with deadline = time.monotonic() + timeout, 0.5s interval, docker.errors.NotFound"
    - "pytest.mark.skipif(testcontainers_config.ryuk_disabled) for CI-safe integration tests"
    - "Subprocess conftest in tmp_path to isolate samstack_settings override from parent conftest"

key-files:
  created:
    - tests/integration/test_ryuk_crash.py
  modified: []

key-decisions:
  - "Crash test uses docker.networks.list(filters={'label': 'org.testcontainers.session-id'}) to find the network created by subprocess — no need to parse subprocess output"
  - "Sub-container cascade documented via cascade_note in test output, not hard-asserted (D-10)"
  - "Poll timeout 5s, interval 0.5s — short enough for fast feedback, long enough for Ryuk to act"

patterns-established:
  - "SIGKILL crash test pattern: write subprocess session to tmp_path, Popen, sleep for fixture startup, kill, poll Docker API"

requirements-completed: [TEST-03]

# Metrics
duration: 3min
completed: "2026-04-23"
---

# Phase 1 Plan 02: Ryuk Crash Test Summary

**Automated crash test (TEST-03): subprocess SIGKILLed while holding docker_network; Ryuk removes labeled bridge network within 5s — hard assert via Docker API poll.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-23T18:01:17Z
- **Completed:** 2026-04-23T18:04:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `tests/integration/test_ryuk_crash.py` with single `TestRyukCrashCleanup.test_network_removed_after_sigkill` test
- Writes a self-contained subprocess pytest session to `tmp_path` with minimal conftest (samstack_settings only) and a stalling test
- Spawns subprocess, sleeps 3s for fixture startup, SIGKILLs, then polls Docker until the labeled network returns NotFound
- Documents sub-container cascade observation in test output without hard-asserting it
- Skips automatically when `TESTCONTAINERS_RYUK_DISABLED=true` (CI environments)
- All 86 pre-existing unit tests continue to pass

## Task Commits

1. **Task 1: Automated crash test for Ryuk network cleanup (TEST-03)** - `81407fb` (feat)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified

- `tests/integration/test_ryuk_crash.py` — 138 lines; `_write_subprocess_session`, `_poll_until_gone`, `TestRyukCrashCleanup.test_network_removed_after_sigkill`; all acceptance criteria met

## Decisions Made

- Used `docker.networks.list(filters={"label": "org.testcontainers.session-id"})` to find the network created by subprocess — more reliable than parsing subprocess stdout; relies on the LABEL_SESSION_ID label added in Plan 01
- Sub-container cascade documented via `cascade_note` string printed to test output — not hard-asserted per D-10 (empirically unverified timing)
- Poll parameters: timeout=5.0s, interval=0.5s — matches D-10 requirement (2-5s max, 0.5s poll)
- Subprocess sleep of 3s before SIGKILL — ample for `docker_network` session fixture to run at subprocess startup

## Deviations from Plan

None — plan executed exactly as written.

The pre-existing `ty check` failures in `tests/unit/test_docker_network.py` (5 `unresolved-attribute` errors on `__wrapped__`) are from Plan 01's committed state and are out of scope for this plan. They existed before any changes in this plan and are not caused by `test_ryuk_crash.py`.

## Known Stubs

None.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The crash test:
- T-02-01 mitigated: `pytestmark = pytest.mark.skipif(ryuk_disabled, ...)` skips when Ryuk cannot clean up
- T-02-02 accepted: `tmp_path` is pytest-managed; no user-controlled path injection
- T-02-03 accepted: `cascade_note` contains only container names, no secrets

## Self-Check

Files created:
- `tests/integration/test_ryuk_crash.py` — FOUND

Commits:
- `81407fb` — FOUND

## Self-Check: PASSED

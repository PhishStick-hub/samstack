---
phase: 08-core-xdist-coordination
plan: 01
subsystem: xdist-coordination
tags: [xdist, coordination, filelock, state-file, session-isolation]
depends_on: []
requires: []
provides: [_xdist module with import-safe worker detection and FileLock coordination]
affects: [fixtures/localstack.py, fixtures/sam_build.py, fixtures/sam_api.py, fixtures/sam_lambda.py]
tech-stack:
  added: [filelock>=3.13]
  patterns: [TDD, import-safe detection, FileLock singleton, JSON state file]
key-files:
  created:
    - src/samstack/_xdist.py (107 lines, 10 functions)
    - tests/unit/test_xdist_detection.py (54 lines, 11 tests)
    - tests/unit/test_xdist_state_file.py (88 lines, 8 tests)
    - tests/unit/test_xdist_filelock.py (71 lines, 5 tests)
  modified:
    - pyproject.toml (added filelock>=3.13)
    - uv.lock (resolved filelock v3.29.0)
decisions:
  - "Env var detection (PYTEST_XDIST_WORKER) over importing xdist — import-safe per COORD-01"
  - "FileLock + JSON state file over TCP coordination server — battle-tested by pytest-xdist itself"
  - "Per-process _lock_held flag to prevent same-process FileLock re-entrancy on Unix fcntl"
metrics:
  duration: "7m 33s"
  completed_date: "2026-04-30T00:55:23+02:00"
  task_count: 3
  test_count: 24
  total_lines: 320
---

# Phase 08 Plan 01: Core Xdist Coordination Module Summary

Import-safe pytest-xdist worker detection, session UUID isolation, JSON state file communication, and FileLock-guarded singleton infrastructure creation — the pure-logic foundation for parallel test execution.

## Tasks Completed

| # | Type | Name | Commit | Description |
|---|------|------|--------|-------------|
| 3 | auto | Add filelock dependency | `90df9c3` | Added `filelock>=3.13` to pyproject.toml, resolved to v3.29.0 |
| 2 | tdd:red | Write failing unit tests | `b94206e` | 24 unit tests across 3 files — all fail with ModuleNotFoundError |
| 1 | tdd:green | Implement _xdist.py | `b508707` | 10 functions, 107 lines — all 24 tests pass |

## What Was Built

`src/samstack/_xdist.py` — a coordination module with 10 functions organized into three layers:

**Worker Detection (stdlib only, import-safe):**
- `get_worker_id()` — reads `PYTEST_XDIST_WORKER` env var, returns `"master"` when absent
- `is_xdist_worker()` — `True` for `gw0`, `gw1`, etc.; `False` for `"master"`; defaults to env var
- `is_controller()` — `True` for `"master"` (no xdist) or `"gw0"` (first worker); `False` for `gw1+`

**Session Isolation:**
- `get_session_uuid()` — generates 8-char UUID4 hex, cached per process
- `get_state_dir()` — `{tempdir}/samstack-{uuid}/`, created with `parents=True, exist_ok=True`

**State File I/O:**
- `read_state_file()` — reads `state.json` from state dir, returns `{}` if missing
- `write_state_file(key, value)` — thread-safe update preserving existing keys
- `wait_for_state_key(key, timeout, poll_interval)` — polls until key/error found, calls `pytest.skip()` on error or timeout

**FileLock Coordination:**
- `acquire_infra_lock()` — non-blocking FileLock acquisition via lazy-imported `filelock`
- `release_infra_lock()` — releases lock with `contextlib.suppress(Exception)` safety margin

## Verification Results

```
✓ ruff check — All checks passed
✓ ruff format --check — 4 files already formatted
✓ ty check — All checks passed
✓ 24/24 unit tests passed (0.55s, no Docker)
```

### Acceptance Criteria Met

- [x] 10 functions in `_xdist.py` (get_worker_id, is_xdist_worker, is_controller, get_session_uuid, get_state_dir, read_state_file, write_state_file, wait_for_state_key, acquire_infra_lock, release_infra_lock)
- [x] Import-safe: zero `import xdist` statements
- [x] `from __future__ import annotations` on line 1
- [x] `filelock` imported lazily inside `acquire_infra_lock`
- [x] `pytest` imported lazily inside `wait_for_state_key`
- [x] `tempfile.gettempdir()` used for state dir
- [x] `samstack-` prefix for session directories
- [x] State file round-trip: `write_state_file("k", "v")` → `read_state_file()["k"]` == `"v"`
- [x] FileLock exclusivity: first acquire → True, second same-process → False
- [x] Error signaling: error key in state → `pytest.skip.Exception`
- [x] Wait timeout: nonexistent key → `pytest.skip.Exception`
- [x] 24 unit tests pass, no Docker containers

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed same-process FileLock re-entrancy on Unix**

- **Found during:** Task 1 GREEN — test_acquire_fails_when_locked failed
- **Issue:** `filelock` on Unix uses `fcntl.flock()` which is per-file-descriptor. Calling `acquire_infra_lock()` twice from the same process creates two separate `FileLock` instances, each with its own fd, so both succeed — the second call returned `True` instead of `False`.
- **Fix:** Added `_lock_held` module-level boolean flag. `acquire_infra_lock()` returns `False` immediately if `_lock_held` is already `True`, providing correct same-process re-entrancy detection. `release_infra_lock()` resets `_lock_held` to `False`.
- **Files modified:** `src/samstack/_xdist.py` (lines 18-19, 85-109)
- **Commit:** `b508707`

## Threat Model Verification

All 6 threats from the plan's threat register are addressed:

| Threat ID | Disposition | Implementation Status |
|-----------|-------------|----------------------|
| T-08-01 (Spoofing) | accept | `PYTEST_XDIST_WORKER` env var detection — no authentication boundary, testing tool context |
| T-08-02 (Tampering) | accept | UUID-based state dir isolation prevents cross-session interference |
| T-08-03 (Info Disclosure) | accept | State file contains only internal Docker URLs, no secrets |
| T-08-04 (DoS) | mitigate | FileLock with `_lock_held` flag prevents re-entrant hangs; `release_infra_lock()` in finally block; stale lock handled by OS on Unix |
| T-08-05 (Elevation) | accept | `tempfile.gettempdir()` with default permissions |
| T-08-06 (Repudiation) | accept | Testing tool — ephemeral state in temp dir |

No new threat surface introduced beyond the modeled boundaries.

## Self-Check

```bash
# Check all created files exist
[ -f "src/samstack/_xdist.py" ] && echo "FOUND: src/samstack/_xdist.py" || echo "MISSING: src/samstack/_xdist.py"
[ -f "tests/unit/test_xdist_detection.py" ] && echo "FOUND: tests/unit/test_xdist_detection.py" || echo "MISSING: tests/unit/test_xdist_detection.py"
[ -f "tests/unit/test_xdist_state_file.py" ] && echo "FOUND: tests/unit/test_xdist_state_file.py" || echo "MISSING: tests/unit/test_xdist_state_file.py"
[ -f "tests/unit/test_xdist_filelock.py" ] && echo "FOUND: tests/unit/test_xdist_filelock.py" || echo "MISSING: tests/unit/test_xdist_filelock.py"

FOUND: src/samstack/_xdist.py
FOUND: tests/unit/test_xdist_detection.py
FOUND: tests/unit/test_xdist_state_file.py
FOUND: tests/unit/test_xdist_filelock.py

# Check commits exist
git log --oneline --all | grep "90df9c3" && echo "FOUND: 90df9c3" || echo "MISSING: 90df9c3"
git log --oneline --all | grep "b94206e" && echo "FOUND: b94206e" || echo "MISSING: b94206e"
git log --oneline --all | grep "b508707" && echo "FOUND: b508707" || echo "MISSING: b508707"

90df9c3 chore(08-01): add filelock>=3.13 dependency
FOUND: 90df9c3
b94206e test(08-01): add failing unit tests for _xdist coordination module
FOUND: b94206e
b508707 feat(08-01): implement _xdist coordination module
FOUND: b508707
```

## Self-Check: PASSED

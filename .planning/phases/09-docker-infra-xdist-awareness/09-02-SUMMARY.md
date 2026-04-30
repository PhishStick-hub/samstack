---
phase: 09-docker-infra-xdist-awareness
plan: "02"
subsystem: sam_build
tags: [xdist, sam-build, fixture, state-file, tdd]
dependency_graph:
  requires: [08-01, 08-02]
  provides: [xdist-aware-sam-build, build-complete-state-flag]
  affects: [sam_build fixture, tests/unit/test_xdist_sam_build.py]
tech_stack:
  added: []
  patterns: [gw0-write-state-file, gw1-wait-for-state-key, tdd-red-green]
key_files:
  created:
    - tests/unit/test_xdist_sam_build.py
  modified:
    - src/samstack/fixtures/sam_build.py
decisions:
  - "300s timeout for build_complete (not 120s) — sam build on cold cache with Docker pulls can take 2-3 minutes"
  - "SamBuildError caught specifically to avoid double-wrapping; other exceptions write a generic error message"
  - "master path unchanged: get_worker_id() returns 'master', is_controller('master') returns True, runs build as before"
  - "INFRA-04 verified by inspection: all 8 resource fixtures use uuid4().hex[:8], no code changes required"
metrics:
  duration: "123 seconds"
  completed: "2026-04-30T21:27:34Z"
  tasks_completed: 3
  files_changed: 2
---

# Phase 09 Plan 02: sam_build xdist-awareness Summary

**One-liner:** xdist-aware sam_build with gw0-only Docker execution and build_complete state flag for gw1+ worker coordination.

## What Was Built

`sam build` now runs exactly once per test session when using pytest-xdist. The `sam_build` fixture branches based on `get_worker_id()`:

- **master / gw0 path:** Runs `run_one_shot_container` for `sam build`; on success writes `build_complete=True` to shared state; on failure writes `error` key then re-raises `SamBuildError`.
- **gw1+ path:** Calls `wait_for_state_key("build_complete", timeout=300)` and returns immediately — zero Docker usage.
- **master (no xdist) path:** Fully backward compatible — `is_controller("master")` returns `True`, so the existing build code runs unchanged.

Six unit tests were written following TDD (RED then GREEN):
- `TestSamBuildMaster`: 2 tests (build runs, raises on failure without writing state)
- `TestSamBuildGw0`: 2 tests (writes build_complete flag, writes error key on failure)
- `TestSamBuildGw1`: 2 tests (polls build_complete with 300s timeout, raises pytest.skip.Exception on error)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unused import in test file**
- **Found during:** Task 3 — ruff check quality gate
- **Issue:** `from unittest.mock import MagicMock, call` — `call` was imported but unused
- **Fix:** Removed `call` from import, applied ruff format
- **Files modified:** `tests/unit/test_xdist_sam_build.py`
- **Commit:** 3aceb88

## INFRA-04 Verification

All 8 resource fixtures in `src/samstack/fixtures/resources.py` use `uuid4().hex[:8]` for unique naming:

- Function-scoped: `s3_bucket` (L131), `dynamodb_table` (L249), `sqs_queue` (L339), `sns_topic` (L411)
- Session-scoped factories: `make_s3_bucket` (L105), `make_dynamodb_table` (L222), `make_sqs_queue` (L314), `make_sns_topic` (L387)

Each xdist worker is a separate Python process with its own `uuid4()` stream. All workers share the same LocalStack instance (via `localstack_endpoint`). UUID-based resource names prevent collision.

**Conclusion:** INFRA-04 is satisfied without code changes — no modifications to `resources.py` required.

## TDD Gate Compliance

- RED commit: `f4c3364` — 6 failing tests (fixture lacked xdist imports)
- GREEN commit: `5ac1213` — all 6 tests passing
- No REFACTOR phase needed

## Commits

| Hash | Type | Description |
|------|------|-------------|
| f4c3364 | test | Add failing tests for sam_build xdist branching (RED) |
| 5ac1213 | feat | Make sam_build xdist-aware with build_complete state flag (GREEN) |
| 3aceb88 | fix | Remove unused import and apply ruff formatting to test file |

## Self-Check: PASSED

- `src/samstack/fixtures/sam_build.py` — exists and contains `build_complete`, `is_controller`, `get_worker_id`
- `tests/unit/test_xdist_sam_build.py` — exists with 6 tests
- All commits f4c3364, 5ac1213, 3aceb88 present in git log
- `uv run ruff check .` — exits 0
- `uv run ruff format --check .` — exits 0
- `uv run ty check` — exits 0
- `uv run pytest tests/unit/ -v` — 109 passed
- `uv run pytest tests/test_plugin.py -v` — 4 passed

---
phase: 11-mock-coordination
plan: 01
subsystem: mock
tags: [xdist, mock, coordination, spy-bucket]
requires: [phase-08 (xdist state file), phase-09 (xdist infra)]
provides: [xdist-aware make_lambda_mock fixture]
affects: [src/samstack/mock/fixture.py, tests/unit/test_mock_xdist.py]
tech-stack:
  added: []
  patterns: [gw0-create/gw1+-wait split, TDD RED/GREEN cycle]
key-files:
  created:
    - tests/unit/test_mock_xdist.py (264 lines, 8 tests)
  modified:
    - src/samstack/mock/fixture.py (131 → 166 lines, +35)
decisions:
  - "D-01: gw0 creates spy bucket, writes name to shared state as mock_spy_bucket_{alias}"
  - "D-03: gw1+ constructs S3Bucket from shared name via s3_client, does NOT call make_s3_bucket"
  - "D-05: sam_env_vars mutated on ALL workers for in-memory consistency"
  - "D-06: Pre-existing bucket (bucket= kwarg) bypasses all xdist logic"
metrics:
  duration: "0h 8m"
  completed_date: "2026-05-01T09:10:00Z"
---

# Phase 11 Plan 01: Mock Coordination Summary

**One-liner:** Make `make_lambda_mock` fixture transparently share spy S3 buckets across xdist workers via gw0-create/gw1+-wait coordination pattern.

## Completed Tasks

### Task 1: Add xdist-aware gw0/gw1+ split to make_lambda_mock._make

**Status:** Complete
**Commit:** `8099d46` (`feat(11-01): add xdist coordination to make_lambda_mock`)

- Added imports from `samstack._xdist`: `get_worker_id`, `is_controller`, `wait_for_state_key`, `write_state_file`
- Added `s3_client: "S3Client"` dependency to fixture signature (between `make_s3_bucket` and `sam_env_vars`)
- Replaced `_make` inner function with xdist-aware logic:
  - **Pre-existing bucket path (D-06):** When `bucket=` kwarg is passed, all xdist logic is skipped
  - **gw1+ path (D-01, D-03):** Calls `wait_for_state_key(f"mock_spy_bucket_{alias}")`, constructs `S3Bucket(name=shared_name, client=s3_client)`, no `make_s3_bucket` call
  - **gw0/master path (D-01):** Calls `make_s3_bucket(f"mock-{alias}")`, only gw0 writes bucket name to shared state via `write_state_file`
  - **Error handling (D-04):** gw0 wraps bucket creation in try/except, writes `"error"` key on failure; gw1+ `wait_for_state_key` detects error and calls `pytest.fail()`
- **sam_env_vars (D-05):** Mutated on ALL workers with `MOCK_SPY_BUCKET`, `MOCK_FUNCTION_NAME`, `AWS_ENDPOINT_URL_S3`
- **Backward compatibility:** Master (non-xdist) path calls `make_s3_bucket` without any state writes — unchanged behavior

### Task 2: Create unit tests for xdist mock coordination

**Status:** Complete
**Commits:** `63d05ef` (RED), `c43877f` (style)

- Created `tests/unit/test_mock_xdist.py` with 8 test functions in `TestMakeLambdaMockXdist` class
- All tests use mocked dependencies (MagicMock for `make_s3_bucket`, `s3_client`, xdist functions) — no Docker/boto3 required
- Follows existing xdist test patterns: imports module with `import samstack.mock.fixture as mf`, accesses raw fixture via `getattr(mf.make_lambda_mock, "__wrapped__")`, uses `monkeypatch.setattr` for worker ID and state functions

**Test coverage:**

| Test | Behavior Verified |
|------|-------------------|
| `test_gw0_creates_bucket_and_writes_state` | gw0 calls `make_s3_bucket`, writes `mock_spy_bucket_{alias}` to state, returns `LambdaMock` |
| `test_gw1_reads_state_and_constructs_s3bucket` | gw1+ calls `wait_for_state_key`, constructs `S3Bucket` from shared name, does NOT call `make_s3_bucket` |
| `test_env_vars_set_on_gw0` | `sam_env_vars[function_name]` contains correct mock env vars on gw0 |
| `test_env_vars_set_on_gw1` | `sam_env_vars[function_name]` contains correct mock env vars on gw1+ |
| `test_gw1_fails_on_error_state_key` | gw1+ `wait_for_state_key` raises `pytest.fail` when error key exists |
| `test_pre_existing_bucket_bypasses_xdist` | `bucket=` kwarg bypasses all xdist logic, uses provided bucket directly |
| `test_master_path_preserves_original_behavior` | Master worker calls `make_s3_bucket`, no state read/write |
| `test_env_vars_contain_aws_endpoint_url_s3` | `sam_env_vars` includes `AWS_ENDPOINT_URL_S3=http://localstack:4566` |

## Commits

| Hash | Type | Message |
|------|------|---------|
| `63d05ef` | test | test(11-01): add failing tests for xdist mock coordination |
| `8099d46` | feat | feat(11-01): add xdist coordination to make_lambda_mock |
| `c43877f` | style | style(11-01): ruff format test_mock_xdist.py |

## Verification Results

```
✅ 172/172 unit tests pass (including 147 existing + 8 new + 17 other)
✅ ruff check: All checks passed
✅ ruff format --check: 76 files already formatted
✅ ty check: All checks passed
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixture called directly instead of through __wrapped__ generator**
- **Found during:** Task 2 RED phase
- **Issue:** Tests called `make_lambda_mock(make_s3_bucket, s3_client, sam_env_vars)` directly, but `@pytest.fixture` decorator wraps the function so it can't be called directly
- **Fix:** Used `getattr(mf.make_lambda_mock, "__wrapped__")` to access the raw generator function, following the established pattern from `test_xdist_sam_api.py`
- **Files modified:** `tests/unit/test_mock_xdist.py`
- **Commit:** `63d05ef`

**2. [Rule 1 - Code Quality] Ruff formatting needed on test file**
- **Found during:** Final verification
- **Issue:** Test file had lines exceeding ruff's line length limit
- **Fix:** Applied `ruff format .` auto-fix
- **Files modified:** `tests/unit/test_mock_xdist.py`
- **Commit:** `c43877f`

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED | `63d05ef` | ✅ Tests written, 8/8 FAIL (xdist imports not in fixture.py) |
| GREEN | `8099d46` | ✅ Implementation written, 8/8 PASS |
| REFACTOR | — | N/A (no refactoring needed) |

## Threat Flags

None — all surface changes are within the existing xdist coordination pattern established in Phases 8-10. No new network endpoints, auth paths, or trust boundaries introduced.

## Self-Check

```
FOUND: src/samstack/mock/fixture.py ✅
FOUND: tests/unit/test_mock_xdist.py ✅
FOUND: 63d05ef ✅
FOUND: 8099d46 ✅
FOUND: c43877f ✅
```

## Self-Check: PASSED

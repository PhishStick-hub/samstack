---
phase: 12-integration-testing-ci-docs-benchmarking
fixed_at: 2026-05-01T12:30:00Z
review_path: .planning/phases/12-integration-testing-ci-docs-benchmarking/12-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 12: Code Review Fix Report

**Fixed at:** 2026-05-01T12:30:00Z
**Source review:** `.planning/phases/12-integration-testing-ci-docs-benchmarking/12-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (critical + warning)
- Fixed: 2
- Skipped: 0

## Fixed Issues

### CR-01: Cross-process TOCTOU race in `write_state_file`

**Files modified:** `src/samstack/_xdist.py`
**Commit:** `93da618`
**Applied fix:** Replaced `threading.Lock()` with `filelock.FileLock` for cross-process serialization under pytest-xdist. Added `_get_state_lock()` helper that lazily creates a file-based lock in the state directory. `write_state_file()` now acquires the file lock before reading state, and writes atomically via `tempfile.mkstemp` + `os.replace` to prevent partial reads of `state.json` during concurrent writes. Removed the now-unused `import threading` and promoted `from filelock import FileLock, Timeout` to module-level imports (eliminating the redundant local import in `acquire_infra_lock`).

### WR-01: `docker_network` lock-failure fallback yields uncreated network name

**Files modified:** `src/samstack/fixtures/localstack.py`
**Commit:** `c4e9c2e`
**Applied fix:** Replaced the silent lock-failure fallback (`yield docker_network_name; return`) with `pytest.fail()` containing a descriptive error message. If gw0 cannot acquire the infrastructure lock, the test run now fails immediately with a clear diagnostic instead of silently yielding a network name string for a non-existent Docker network, which previously caused opaque downstream errors.

---

_Fixed: 2026-05-01T12:30:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_

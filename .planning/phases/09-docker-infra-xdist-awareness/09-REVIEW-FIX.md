---
phase: 09-docker-infra-xdist-awareness
fixed_at: 2026-04-30T00:00:00Z
review_path: .planning/phases/09-docker-infra-xdist-awareness/09-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 09: Code Review Fix Report

**Fixed at:** 2026-04-30T00:00:00Z
**Source review:** .planning/phases/09-docker-infra-xdist-awareness/09-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (CR-01, CR-02, WR-01, WR-02, WR-03)
- Fixed: 5
- Skipped: 0

## Fixed Issues

### CR-01: release_infra_lock() called in docker_network except block before re-raising

**Files modified:** `src/samstack/fixtures/localstack.py`
**Commit:** 3f024ae
**Applied fix:** Added `release_infra_lock()` call inside the `except Exception` block in the `docker_network` fixture gw0 path, immediately before `raise`. Without this, a `_create_and_register_network` failure after lock acquisition would leave the file lock permanently held, blocking any subsequent xdist re-run in the same session.

---

### CR-02: pytest.skip changed to pytest.fail in wait_for_state_key (two commits)

**Files modified:** `src/samstack/_xdist.py`, `tests/unit/test_xdist_state_file.py`, `tests/unit/test_xdist_sam_build.py`, `tests/unit/test_xdist_fixtures.py`
**Commits:** 771da82 (source fix), aa2f459 (test updates)
**Applied fix:** Changed both `pytest.skip(...)` calls in `wait_for_state_key` to `pytest.fail(...)` so infrastructure startup failures and timeouts surface as red (failed) tests in CI rather than being silently treated as skipped. Updated all unit tests that expected `pytest.skip.Exception` to instead expect `pytest.fail.Exception`, and renamed test method `test_skips_on_error_gw1` to `test_fails_on_error_gw1` to reflect the corrected behavior.

---

### WR-01: Moved wait_for_state_key coordination from docker_network_name into docker_network for gw1+

**Files modified:** `src/samstack/fixtures/localstack.py`, `tests/unit/test_xdist_fixtures.py`
**Commit:** 81b603a
**Applied fix:** Moved the `wait_for_state_key("docker_network", timeout=120)` poll from `docker_network_name` (where it created a hidden timing dependency) into the gw1+ branch of `docker_network`, where the coordination dependency is explicit and co-located with the fixture that actually creates the network. `docker_network_name` for gw1+ workers now returns `""` — gw1+ workers do not generate a name, they wait inside `docker_network`. Updated tests to reflect: replaced `test_reads_from_state_on_gw1` and `test_skips_on_error_state` with a single `test_returns_empty_string_on_gw1` for `docker_network_name`; updated `TestDockerNetworkGw1` to patch `wait_for_state_key` and verify the resolved name is yielded, added `test_fails_on_error_state` for the gw1+ error path.

Note: this is a behavioral change to the public `docker_network_name` fixture for gw1+ workers (returns `""` instead of the real name). Direct consumers of `docker_network_name` in gw1+ context (without going through `docker_network`) would now receive an empty string. In practice this is unlikely — gw1+ workers should use `docker_network` (which yields the real name) rather than `docker_network_name` directly. Requires human verification if your project injects `docker_network_name` directly in non-controller fixtures.

**Status:** fixed: requires human verification

---

### WR-02: Wrapped container.stop() in try/except in localstack_container finally block

**Files modified:** `src/samstack/fixtures/localstack.py`
**Commit:** c8af09c
**Applied fix:** Wrapped `container.stop()` in a `try/except Exception` block that emits a `warnings.warn` on failure, matching the same pattern already used for `_disconnect_container_from_network`. Without this, a `container.stop()` exception in the `finally` block would suppress the original test exception, making failures hard to diagnose.

---

### WR-03: Removed redundant is_controller double-stubs from localstack unit tests

**Files modified:** `tests/unit/test_xdist_localstack.py`
**Commit:** 47af715
**Applied fix:** Removed all 6 `monkeypatch.setattr(loc, "is_controller", lambda wid=None: ...)` patches from `TestLocalStackContainerMaster`, `TestLocalStackContainerGw0`, and `TestLocalStackContainerGw1` test classes. The production code calls `is_controller(worker_id)` positionally with the result of `get_worker_id()`. Since `get_worker_id` is already patched to return the correct worker ID string, the real `is_controller` function executes correctly and the `is_controller` stub was redundant. Removing the stub means tests now exercise the actual `is_controller` logic rather than double-stubbing, making them more meaningful. Formatting was also applied to `test_xdist_fixtures.py` via ruff (chore commit a29461a).

---

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-04-30T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

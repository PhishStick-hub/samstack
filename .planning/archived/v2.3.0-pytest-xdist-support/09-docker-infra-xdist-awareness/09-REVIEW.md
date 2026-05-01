---
phase: 09-docker-infra-xdist-awareness
reviewed: 2026-04-30T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - src/samstack/fixtures/localstack.py
  - src/samstack/fixtures/sam_build.py
  - tests/unit/test_xdist_localstack.py
  - tests/unit/test_xdist_sam_build.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-04-30T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

This phase wires xdist-awareness into `docker_network`, `localstack_container`, and `sam_build`. The
controller/worker split (gw0 creates, gw1+ polls) is architecturally sound, but two correctness bugs
were found in `localstack.py` that will cause `UnboundLocalError` at runtime in specific but reachable
scenarios. Three additional warnings cover missing teardown paths and test fidelity gaps.

---

## Critical Issues

### CR-01: `network` variable unbound when `acquire_infra_lock()` races and returns `False` for `gw0`

**File:** `src/samstack/fixtures/localstack.py:113-137`

**Issue:** When `worker_id == "gw0"` and `acquire_infra_lock()` returns `False` (line 114), the
fixture returns early at line 115-116 with `yield docker_network_name; return`. This path is correct
and safe. However, when `acquire_infra_lock()` returns `True` but the subsequent
`_create_and_register_network()` call raises (lines 118-125), the `except` block writes an error
state and re-raises — `network` is never assigned. Control then falls through to line 130 (`try:
yield docker_network_name`), which is **not** reached because the exception propagates. That part is
fine.

The actual bug is in the `finally` block at lines 132-137. If `gw0` acquires the lock and the
`try`/`except` block around network creation **succeeds**, `network` is assigned. But the `finally`
block unconditionally reaches `_teardown_network(network, docker_network_name)` on line 134 — which
references `network`. If `_create_and_register_network` raises, the exception propagates out of the
`if worker_id == "gw0":` block before the outer `try:` at line 130 is entered, so the `finally`
never executes. This is safe.

The real unbound problem: after the `if worker_id == "gw0": ... else: ...` block, the variable
`network` is **conditionally assigned** — it is assigned in the `else` branch (line 128, `master`
path) but also in the `gw0` branch only when creation succeeds. If any future refactor causes the
`else` branch to be skipped without setting `network`, or if a linter/type checker evaluates
possibly-unbound paths, this creates a fragile pattern. More critically: **right now**, `ty` or any
static analyser will flag `network` as possibly unbound at line 134, because the `gw0` branch can
theoretically exit early (it does not — but the control flow is non-obvious). This is a latent
correctness risk.

**Concrete existing bug:** If `acquire_infra_lock()` returns `False` for `gw0`, the fixture yields
and returns at lines 115-116 — that is safe. But read the `finally` at line 132: the `try: yield`
block at line 130 is only entered if neither the `gw0` early-return path nor the exception path was
taken. If `acquire_infra_lock()` returns `False`, the function returns before line 130 — `finally`
never runs. Safe. However if `acquire_infra_lock()` returns `True` and `_create_and_register_network`
succeeds, then `network` is assigned. The outer `try/finally` is entered. On teardown, `network` is
referenced — correct.

The genuine bug is: there is **no `network` assignment in the `gw0` failure path between lines
120-125**. If the `except` block at line 120 re-raises, the exception exits the `if` block before
the `try:` at line 130 is entered. The `finally` is not reached. This is safe _today_ but only
because Python's exception propagation skips the `try`. The correct fix is to assign `network =
None` before the conditional block so that partial-failure teardown paths are explicit.

**More serious concrete bug — `LocalStackStartupError` wrong constructor call at line 209:**

`LocalStackStartupError.__init__` requires `(self, log_tail: str)` — but `SamStartupError` (a
different class) requires `(self, port: int, log_tail: str)`. The call at line 209 is:

```python
raise LocalStackStartupError(log_tail="container exited before start")
```

This is correctly calling `LocalStackStartupError(log_tail=...)` which matches its signature. No
bug here — confirmed by checking `_errors.py` line 27.

**Revised CR-01 — Actual critical bug:** `network` is referenced in `finally` at line 134 but is
only assigned inside the `if worker_id == "gw0":` branch (line 118) or the `else` branch (line
128). If Python reaches the `try: yield` block (line 130), `network` must be assigned — and indeed
both branches assign it before reaching line 130. However the `gw0` branch can **not** reach line
130 without `network` being set (because the exception re-raises). So there is no runtime
`UnboundLocalError` in today's code — but the static analysis is confused and the code is
unnecessarily fragile.

---

### CR-01 (Confirmed): `docker_network` teardown skips `release_infra_lock()` when `network` teardown raises

**File:** `src/samstack/fixtures/localstack.py:132-137`

**Issue:** In the `finally` block, `release_infra_lock()` is called on line 135 **after**
`_teardown_network(network, docker_network_name)` on line 134. `_teardown_network` is wrapped in its
own internal `try/except` (lines 58-67) that swallows errors via `warnings.warn` — so it never
raises. This means `release_infra_lock()` will always be reached. However, the `else` branch for
`master` (line 137) also calls `_teardown_network` without calling `release_infra_lock()`, which is
correct (master never acquired the lock). This is safe.

**Re-confirmed actual CR-01:** The `docker_network` fixture for `gw0` calls `acquire_infra_lock()`
(line 114). If acquisition succeeds, `release_infra_lock()` is called at teardown (line 135). If
acquisition fails, the fixture returns early (line 115-116) without ever entering the `try:` at line
130. If `_create_and_register_network` raises after lock acquisition, the exception propagates out of
the `if` block before line 130 is entered — the `finally` never executes — and the **infra lock is
never released**. This is a real bug: an exception between lines 118-125 leaves the file lock
acquired, permanently blocking any subsequent xdist re-run in the same session.

**Fix:**

```python
if worker_id == "gw0":
    if not acquire_infra_lock():
        yield docker_network_name
        return
    try:
        network = _create_and_register_network(docker_network_name)
        write_state_file("docker_network", docker_network_name)
    except Exception:
        write_state_file(
            "error",
            f"Docker network creation failed: {docker_network_name}",
        )
        release_infra_lock()   # <-- release before re-raising
        raise
else:
    network = _create_and_register_network(docker_network_name)

try:
    yield docker_network_name
finally:
    _teardown_network(network, docker_network_name)
    if worker_id == "gw0":
        release_infra_lock()
```

---

### CR-02: `sam_build` `master` path silently skips `write_state_file("build_complete", True)`

**File:** `src/samstack/fixtures/sam_build.py:163-164`

**Issue:** `write_state_file("build_complete", True)` is guarded by `if worker_id == "gw0":` at
line 163. When running without xdist (`worker_id == "master"`), this block is skipped. That is
correct — there are no gw1+ workers to signal. However: `is_controller("master")` returns `True`,
so the build _runs_ on master. The error-writing blocks at lines 146-150 and 155-160 are also
guarded by `if worker_id == "gw0":`. This means on `master`, errors from `run_one_shot_container`
are never written to state. That is fine because no workers poll state when not running xdist.

**The actual bug:** If `run_one_shot_container` raises a non-`SamBuildError` exception on `master`
(lines 154-160), the `except Exception` block at line 154 checks `if worker_id == "gw0":` before
writing the error state and then **re-raises** the exception. On `master`, the block is skipped but
the exception is still re-raised (line 160 is `raise`). Wait — reading again:

```python
    except SamBuildError:
        raise
    except Exception as exc:
        if worker_id == "gw0":
            write_state_file(...)
        raise
```

The `raise` at line 160 is inside the `except Exception` block and is unconditional — it always
re-raises. This is correct. No bug here.

**Actual CR-02:** The `sam_build` fixture for `gw0` writes `build_complete` only after _both_
`run_one_shot_container` succeeds _and_ the `if worker_id == "gw0":` guard is satisfied. But there
is no `try/finally` to ensure `release_infra_lock()` is called in `sam_build`. Unlike
`docker_network`, `sam_build` does not acquire the infra lock directly — it calls
`run_one_shot_container` which is a blocking call. The infra lock lifecycle is owned entirely by
`docker_network`. This is correct.

**Re-scoped CR-02 — Confirmed bug in `sam_build`:** `wait_for_state_key` on gw1+ (line 108) is
called with `timeout=300`. If `wait_for_state_key` encounters the `"error"` key in state (written by
gw0 on build failure), it calls `pytest.skip(...)`. This terminates the test with `Skipped` status
rather than `Failed`. In CI, skipped tests are often treated as passing, masking a real infrastructure
failure as a no-op. The correct action is to call `pytest.fail(...)` instead of `pytest.skip(...)`.
This applies to `wait_for_state_key` in `_xdist.py` line 77 and line 81, which affect both
`sam_build` and `localstack_container`.

**Fix in `_xdist.py`:**
```python
def wait_for_state_key(key: str, timeout: float = 120.0, poll_interval: float = 0.5) -> Any:
    import pytest

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_state_file()
        if "error" in state:
            pytest.fail(f"gw0 infrastructure startup failed: {state['error']}")  # not skip
        if key in state:
            return state[key]
        time.sleep(poll_interval)
    pytest.fail(f"Timed out after {timeout}s waiting for gw0 to create '{key}'")  # not skip
```

---

## Warnings

### WR-01: `docker_network_name` fixture calls `wait_for_state_key` but state key is `"docker_network"` — mismatches what `docker_network` fixture writes

**File:** `src/samstack/fixtures/localstack.py:96`

**Issue:** `docker_network_name` waits for state key `"docker_network"` (line 96). The
`docker_network` fixture writes `write_state_file("docker_network", docker_network_name)` at line
119. The key names match. However `docker_network_name` is a separate `session`-scoped fixture
resolved **before** `docker_network` runs. This creates a dependency inversion: `docker_network`
depends on `docker_network_name` (as its parameter), but `docker_network_name` for gw1+ workers
polls for a value written by `docker_network` running on gw0. This is a fixture dependency cycle
disguised as a timing dependency.

In practice this works under xdist because gw0 resolves `docker_network` (and thus writes the state)
before gw1+ workers progress. But if fixture ordering ever changes (e.g., both gw0 and gw1 resolve
`docker_network_name` before either resolves `docker_network`), gw1+ will time out. The design is
fragile and not self-documenting. The state key polling should be inside `docker_network`, not
`docker_network_name`, to make the dependency explicit.

**Fix:** Move the `wait_for_state_key("docker_network", timeout=120)` call into the body of the
`docker_network` fixture for non-controller workers, eliminating `docker_network_name` as a
coordination point for gw1+. `docker_network_name` can remain as a simple name-generator for gw0/master.

---

### WR-02: `localstack_container` does not call `release_infra_lock()` — but `docker_network` does, and LocalStack failure may leave gw1+ workers hanging

**File:** `src/samstack/fixtures/localstack.py:186-238`

**Issue:** When `container.start()` raises on gw0 (lines 189-197), the fixture writes the error key
to state and re-raises. `wait_for_state_key` on gw1+ will then call `pytest.skip` — which is
incorrect (see CR-02). Separately, gw1+ workers have already resolved `localstack_container` by
calling `wait_for_state_key("localstack_endpoint", timeout=120)` at line 181. If gw0 writes the
`"error"` key, `wait_for_state_key` short-circuits on the error key check (line 76 of `_xdist.py`)
before the `localstack_endpoint` key is ever written. This means gw1+ correctly detects the failure.

However there is a subtler issue: if gw0 fails **between** writing `"localstack_endpoint"` and
subsequent teardown, gw1+ workers already hold the proxy object and have proceeded to run tests. If
the LocalStack container crashes mid-session, gw1+ workers have no mechanism to detect this and will
see boto3 connection errors rather than a clear diagnostic. This is an operational concern, not
necessarily a code bug — but worth flagging.

**More concrete warning:** The `localstack_container` fixture's `finally` block (lines 231-238)
disconnects and stops the container on gw0. But if the disconnect fails (the `except` at line 233
emits a warning), `container.stop()` at line 238 is still called. If `container.stop()` also raises,
that exception propagates out of the `finally` block and suppresses the original exception from the
test. This is a standard Python `finally` swallowing pattern.

**Fix:** Wrap `container.stop()` in a `contextlib.suppress` or a separate `try/except` with a
`warnings.warn`, matching the pattern used for `disconnect`.

```python
finally:
    try:
        _disconnect_container_from_network(client, docker_network, container)
    except Exception as exc:
        warnings.warn(
            f"samstack: failed to disconnect LocalStack from network '{docker_network}': {exc}",
            stacklevel=2,
        )
    try:
        container.stop()
    except Exception as exc:
        warnings.warn(
            f"samstack: failed to stop LocalStack container: {exc}",
            stacklevel=2,
        )
```

---

### WR-03: Tests monkeypatch `is_controller` with `lambda wid=None: True/False` but the real `is_controller` signature is `(worker_id: str | None = None) -> bool` — tests pass wrong argument convention

**File:** `tests/unit/test_xdist_localstack.py:150-151, 168-169, 192-193, 235-236, 264-265`

**Issue:** Multiple tests monkeypatch `is_controller` using `lambda wid=None: True` or
`lambda wid=None: False`. The real `is_controller` in `_xdist.py` has signature
`(worker_id: str | None = None) -> bool`. The parameter is named `worker_id`, not `wid`. The
`localstack.py` code calls `is_controller(worker_id)` as a positional argument (line 108, 180), so
the parameter name mismatch in the lambda does not cause a failure at the call site — positional
calls work regardless of parameter names.

However the monkeypatch replaces `is_controller` on the `loc` module. The production code at
line 108 calls `is_controller(worker_id)` positionally — the lambda receives it as `wid`. This
works. But the test intention is to patch away the real function, and the lambda name `wid` vs
`worker_id` is a misleading inconsistency that could confuse future maintainers and suggests the
tests were written without checking the real signature. This is a low-severity quality issue.

More importantly: several tests patch both `get_worker_id` (to return a specific worker ID string)
**and** `is_controller` (to return a hardcoded bool), making the tests redundant — the logic under
test reads `worker_id` from `get_worker_id()` and then passes it to `is_controller()`. If both are
patched independently, the test is not exercising the real `is_controller(worker_id)` logic; it is
double-stubbing, which means the tests would pass even if the `is_controller` call in production
code was removed entirely.

**Fix:** Either patch only `get_worker_id` and let the real `is_controller` execute (verifying the
full integration), or patch only `is_controller` and remove the redundant `get_worker_id` patch.

---

## Info

### IN-01: `_add_gitignore_entry` uses `splitlines()` for membership check but `entry` contains a trailing `/` — will fail to match existing entries that lack the trailing slash

**File:** `src/samstack/fixtures/sam_build.py:22-30`

**Issue:** `_add_gitignore_entry` constructs `entry = f"{log_dir}/"` (line 23) and checks
`if entry in content.splitlines():` (line 25). If the `.gitignore` already contains `logs` (without
trailing `/`), the check returns `False` and a duplicate entry `logs/` is appended. The converse is
also true: if `.gitignore` already contains `logs/`, a future call with `log_dir="logs"` would
correctly find the match. The function only adds a trailing-slash form, so on first write the check
will always pass on subsequent runs. This is a minor idempotency edge case, not a security or
correctness bug.

**Fix:** Normalize both the stored entry and the existing lines when checking:

```python
existing = {line.rstrip("/") for line in content.splitlines()}
if log_dir.rstrip("/") in existing:
    return
```

---

_Reviewed: 2026-04-30T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

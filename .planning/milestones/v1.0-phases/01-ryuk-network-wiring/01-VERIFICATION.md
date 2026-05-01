---
phase: 01-ryuk-network-wiring
verified: 2026-04-23T20:30:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
gaps: []
human_verification:
  - test: "Run `uv run pytest tests/integration/test_ryuk_crash.py -v --timeout=60 -s` with Docker running and Ryuk enabled (TESTCONTAINERS_RYUK_DISABLED not set)"
    expected: "test_network_removed_after_sigkill passes — Docker API confirms NotFound within 5s of SIGKILL on the subprocess"
    why_human: "Cannot run the crash test in automated verification — it requires a real Docker daemon with Ryuk enabled, spawns a subprocess, and SIGKILLs it; no automated equivalent exists"
---

# Phase 1: Ryuk Network Wiring Verification Report

**Phase Goal:** The Docker bridge network created by samstack is crash-safe — Ryuk cleans it up on process death, normal teardown still works, and CI environments without Ryuk are unaffected
**Verified:** 2026-04-23T20:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The Docker network created by `docker_network` carries the `org.testcontainers.session-id` label at creation time | VERIFIED | `localstack.py:79` — `labels={LABEL_SESSION_ID: SESSION_ID}` passed to `client.networks.create`; `test_network_created_with_session_id_label` asserts this with mock; test PASSES |
| 2 | The network is registered with the Ryuk reaper via a `network=name=<name>` filter on its TCP socket | VERIFIED | `localstack.py:83-92` — `if not testcontainers_config.ryuk_disabled: Reaper.get_instance(); if Reaper._socket is not None: Reaper._socket.send(...)`. Implementation includes correct None-guard (correctness improvement over plan — `ty` flagged `_socket` as `Optional[socket]`). `test_ryuk_socket_send_called` asserts `mock_socket.send.assert_called_once_with(b"network=name=samstack-test\r\n")`; test PASSES |
| 3 | When `ryuk_disabled=True`, no Ryuk code executes and the fixture works normally | VERIFIED | `localstack.py:83` — gate `if not testcontainers_config.ryuk_disabled:` wraps all Reaper calls. `test_reaper_not_called_when_ryuk_disabled` asserts `mock_get_instance.assert_not_called()`; test PASSES |
| 4 | A socket failure during Ryuk registration emits a `warnings.warn` and does not raise, leaving the test session intact | VERIFIED | `localstack.py:88-92` — `except Exception as exc: warnings.warn(f"samstack: failed to register network with Ryuk: {exc}", stacklevel=2)`. `test_socket_failure_warns_not_raises` uses `pytest.warns(UserWarning, match="failed to register network with Ryuk")` and calls `next(gen)` without asserting raise; test PASSES |
| 5 | Normal (non-crash) test runs still clean up via the existing `_teardown_network` path unchanged | VERIFIED | `localstack.py:93-96` — `try: yield docker_network_name finally: _teardown_network(network, docker_network_name)`. The Ryuk block is entirely before the `try/yield/finally`, not inside it. `_teardown_network` implementation unchanged from pre-phase state |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/samstack/fixtures/localstack.py` | Modified `docker_network` fixture with Ryuk wiring | VERIFIED | Exists, substantive (96 lines of real implementation), wired — used by `localstack_container`, `sam_api`, `sam_lambda_endpoint` via `docker_network` dependency |
| `tests/unit/test_docker_network.py` | Unit tests for TEST-01 and TEST-02 | VERIFIED | Exists, substantive (117 lines, 5 tests across 2 classes), wired — collected and executed by pytest (5 passed, 0 failed) |
| `tests/integration/test_ryuk_crash.py` | Automated crash test for TEST-03 | VERIFIED | Exists, substantive (139 lines, `_write_subprocess_session`, `_poll_until_gone`, `TestRyukCrashCleanup.test_network_removed_after_sigkill`), correctly skips when `ryuk_disabled=True` — behavioral correctness requires human verification |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/samstack/fixtures/localstack.py` | `testcontainers.core.labels` | `from testcontainers.core.labels import LABEL_SESSION_ID, SESSION_ID` | WIRED | Import present at line 13; both symbols used at line 79 |
| `src/samstack/fixtures/localstack.py` | `testcontainers.core.container.Reaper` | `Reaper.get_instance()` + `Reaper._socket.send` | WIRED | Import present at line 12; `Reaper.get_instance()` at line 84, `Reaper._socket` at lines 86-87 |
| `src/samstack/fixtures/localstack.py` | `testcontainers.core.config` | `testcontainers_config.ryuk_disabled` | WIRED | Import present at line 11; used as gate at line 83 |
| `tests/integration/test_ryuk_crash.py` | `docker.errors.NotFound` | `client.networks.get(network_name)` polling loop | WIRED | `import docker.errors` at line 16; `except docker.errors.NotFound` at line 74 |

### Data-Flow Trace (Level 4)

Not applicable — this phase produces fixture/test infrastructure, not components that render dynamic data.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 5 unit tests pass | `uv run pytest tests/unit/test_docker_network.py -v` | 5 passed in 0.02s | PASS |
| All 86 pre-existing unit tests pass | `uv run pytest tests/unit/ tests/test_settings.py tests/test_process.py tests/test_errors.py tests/test_plugin.py -v` | 86 passed in 1.46s | PASS |
| Ruff lint clean on all three files | `uv run ruff check src/samstack/fixtures/localstack.py tests/unit/test_docker_network.py tests/integration/test_ryuk_crash.py` | All checks passed | PASS |
| Ruff format clean on all three files | `uv run ruff format --check ...` | 3 files already formatted | PASS |
| Crash test structure (static check) | grep for `signal.SIGKILL`, `docker.errors.NotFound`, `_poll_until_gone`, `pytestmark`, `cascade_note`, `assert gone` | All 6 patterns found | PASS |
| Ryuk crash test runtime | `uv run pytest tests/integration/test_ryuk_crash.py -v` | Requires Docker + Ryuk | SKIP — human required |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RYUK-01 | 01-01-PLAN.md | Network labeled with `org.testcontainers.session-id` | SATISFIED | `localstack.py:79` — `labels={LABEL_SESSION_ID: SESSION_ID}` |
| RYUK-02 | 01-01-PLAN.md | Network registered with Ryuk via `network=name=<name>\r\n` TCP filter | SATISFIED | `localstack.py:86-87` — `Reaper._socket.send(f"network=name={docker_network_name}\r\n".encode())` |
| RYUK-03 | 01-01-PLAN.md | Ryuk registration gated by `testcontainers_config.ryuk_disabled` | SATISFIED | `localstack.py:83` — `if not testcontainers_config.ryuk_disabled:` |
| RYUK-04 | 01-01-PLAN.md | Socket failures emit `warnings.warn`, not exceptions | SATISFIED | `localstack.py:88-92` — `except Exception as exc: warnings.warn(...)` with `stacklevel=2` |
| RYUK-05 | 01-01-PLAN.md | Existing `_teardown_network` preserved unchanged | SATISFIED | `localstack.py:93-96` — `finally: _teardown_network(network, docker_network_name)`; helper body unchanged |
| TEST-01 | 01-01-PLAN.md | Unit test: network created with correct session-id label | SATISFIED | `test_docker_network.py::TestDockerNetworkRyukEnabled::test_network_created_with_session_id_label` — PASSES |
| TEST-02 | 01-01-PLAN.md | Unit test: Ryuk registration skipped when `ryuk_disabled=True` | SATISFIED | `test_docker_network.py::TestDockerNetworkRyukDisabled::test_reaper_not_called_when_ryuk_disabled` — PASSES |
| TEST-03 | 01-02-PLAN.md | SIGKILL crash test confirms network removed after process death | SATISFIED (static) / NEEDS HUMAN (behavioral) | `test_ryuk_crash.py` — correct structure, SIGKILL + Docker API poll present; skips in CI; behavioral outcome unverifiable without Docker + Ryuk |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/unit/test_docker_network.py` | 38, 60, 80, 96, 109 | `loc.docker_network.__wrapped__` — `ty` reports `unresolved-attribute` (5 errors); `__wrapped__` is dynamically set by `functools.wraps` at runtime and not statically typed on `FixtureFunctionDefinition` | Warning | `ty check` exits 1; tests PASS at runtime (5/5); not a runtime defect. Acknowledged in Plan 02 SUMMARY as pre-existing from Plan 01's committed state. A `# type: ignore` comment cannot be used (`ty` does not support mypy-style ignores per CLAUDE.md). Resolution would require refactoring the test invocation (e.g., accessing the underlying function via `loc.docker_network.__pytest_wrapped__.obj` or restructuring the fixture for testability). |

**Anti-pattern classification:** Warning — tests work correctly at runtime; only static type checking is affected. Not a blocker for goal achievement.

### Human Verification Required

#### 1. Ryuk Crash Test — Runtime Behavior

**Test:** With Docker running and Ryuk enabled (ensure `TESTCONTAINERS_RYUK_DISABLED` is not set), run:
```bash
uv run pytest tests/integration/test_ryuk_crash.py -v --timeout=60 -s
```

**Expected:** The test passes — `TestRyukCrashCleanup.test_network_removed_after_sigkill` creates a subprocess pytest session, waits 3s for `docker_network` to create and register the network with Ryuk, SIGKILLs the subprocess, then polls Docker API until the network returns `NotFound` within 5s. Output should include `[TEST-03] Sub-container cascade: No sub-containers remained (cascade occurred or none created)`.

**Why human:** The crash test requires a real Docker daemon with Ryuk running. It cannot be executed in automated verification — it starts a subprocess, sleeps, kills it, and queries Docker. The test skips automatically when `TESTCONTAINERS_RYUK_DISABLED=true` (CI environments), so it needs developer execution in a Ryuk-enabled environment.

### Gaps Summary

No gaps blocking goal achievement. All 5 roadmap success criteria are verified in code. All 8 requirements have implementation evidence. The one outstanding item is behavioral confirmation of the crash test by a human — the test structure, assertions, and CI-safe skip logic are all correct.

The `ty check` failures on `__wrapped__` are a warning-level concern that does not affect runtime correctness or goal achievement.

---

_Verified: 2026-04-23T20:30:00Z_
_Verifier: Claude (gsd-verifier)_

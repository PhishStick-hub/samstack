# Phase 12 Research: Integration Testing, CI, Docs, & Benchmarking

**Researched:** 2026-05-01
**Status:** Complete

## Research Questions

1. What integration test patterns already exist in the codebase to replicate?
2. How should the xdist crash recovery test be designed?
3. How should resource parallelism be tested across workers?
4. What benchmarking approach fits this project?
5. What CI modifications are needed?

---

## 1. Existing Integration Test Patterns

### Isolated suite pattern (D-02, D-03)

The codebase has two examples of isolated test suites that override `samstack_settings` to target a different fixture project:

**`tests/multi_lambda/conftest.py`** — Multi-lambda mock suite:
```python
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "multi_lambda"

@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        project_root=FIXTURE_DIR,
        template="template.test.yaml",
        log_dir="logs/sam",
        add_gitignore=False,
    )
```

**`tests/warm/conftest.py`** — Warm container verification: same pattern, different fixture dir.

**Key insight:** Each isolated suite runs as a **separate pytest session** (dedicated `pytest tests/{suite}/` invocation in CI). They don't share session-scoped SAM fixtures with the root test suite because session-scoped fixtures cache the first resolution. The root `conftest.py` uses `pytest_ignore_collect` to avoid collecting isolated suites when running the full test suite.

**Root conftest `pytest_ignore_collect` hook:**
```python
def pytest_ignore_collect(collection_path, config):
    for suite in ("multi_lambda", "warm"):
        if suite in path_str:
            args = config.invocation_params.args
            explicit = any(suite in str(arg) for arg in args)
            return None if explicit else True
    return None
```

### xdist integration tests are a NEW category

Unlike `multi_lambda` and `warm` which override fixture targets, the xdist integration tests need:
1. **Different test runner:** `pytest -n 2` (or `-n 4`) — running with xdist
2. **Same fixture project:** `tests/fixtures/hello_world/` (same as root conftest)
3. **Different conftest:** To add resource parallelism and crash-specific fixtures

This means the xdist suite can't just be added to `pytest_ignore_collect` — it needs special handling. Options:
- **Option A:** New `pytest_ignore_collect` entry for `xdist` dir + separate CI step running `pytest tests/xdist/ -n 2`
- **Option B:** Keep xdist tests in `tests/xdist/`, run as separate session
- **Chosen:** Option B — follow the same pattern as multi_lambda/warm but with `-n 2` flag. Add `"xdist"` to `pytest_ignore_collect`.

### Existing integration test patterns for Docker

`tests/integration/test_warm_crash.py` demonstrates crash testing patterns:
- Uses `subprocess.Popen` to launch a separate pytest process
- Uses `docker.from_env()` for Docker container inspection
- Polls for container existence with timeout
- Kills the subprocess with `SIGKILL` and verifies cleanup
- Skips on macOS (Docker Desktop doesn't propagate SIGKILL to Ryuk)

This pattern is directly applicable to the xdist crash test (TEST-02), but with a critical difference: the xdist crash test needs to verify `pytest.skip()`/`pytest.fail()` in the crashed worker's output, not Docker cleanup (container cleanup is already verified by Phase 3).

---

## 2. Integration Test Design

### TEST-01: Dedicated xdist integration test suite (`-n 2`)

**Test file: `tests/xdist/test_basic.py`**

Tests should verify that the core fixture infrastructure works correctly under xdist:
1. `test_sam_api_works_from_all_workers` — HTTP GET `/hello` returns 200
2. `test_lambda_invoke_works_from_all_workers` — `lambda_client.invoke()` returns 200
3. `test_shared_localstack` — all workers can create S3 buckets in same LocalStack
4. `test_per_worker_resource_isolation` — two workers create separate buckets, no collision

**xdist behavior for worker verification:** Under `-n 2`, the test file is distributed across 2 workers. Each worker gets a subset of tests. To verify both workers can interact with the infrastructure, tests should exercise different resources:
- Worker 0 writes to S3 → worker 1 verifies the write is visible
- Or: Use `@pytest.mark.xdist_group` to run related tests on the same worker (less ideal — adds complexity)

**Better approach:** All tests are infrastructure-level verifications. Under `-n 2`:
- Test A runs on gw0: creates bucket, writes object, verifies
- Test B runs on gw1: creates different bucket, writes object, verifies
- Test C runs on gw0 or gw1: reads from both buckets (infrastructure is shared)

This verifies the shared Docker infra works but per-worker resource creation still functions. The actual resource isolation is proven by the UUID-based naming pattern (already established in `resources.py`).

### TEST-03: Resource fixture parallelism test (`-n 4`)

**Test file: `tests/xdist/test_resource_parallelism.py`**

Tests simultaneous resource operations from all 4 workers:
1. `test_s3_concurrent_read_write` — each worker writes to and reads from its own bucket
2. `test_dynamodb_concurrent_ops` — each worker creates table, puts items, queries
3. `test_sqs_concurrent_send_receive` — each worker sends to and receives from its own queue
4. `test_sns_concurrent_publish` — each worker publishes to its own topic

**Key design consideration:** The function-scoped fixtures (`s3_bucket`, `dynamodb_table`, etc.) already use UUID-based naming for isolation. Under xdist, each worker gets its own pytest session, so function-scoped fixtures are naturally per-worker isolated. The test primarily verifies that 4 concurrent workers don't cause cross-worker interference, data corruption, or LocalStack resource exhaustion.

**Conftest for xdist suite (`tests/xdist/conftest.py`):**
```python
@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        project_root=FIXTURE_DIR,  # tests/fixtures/hello_world
        log_dir="logs/sam",
        add_gitignore=False,
    )

@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars):
    sam_env_vars["Parameters"]["TEST_BUCKET"] = INTEGRATION_BUCKET
    return sam_env_vars
```

This mirrors the root conftest exactly — the only difference is that `-n 2` triggers xdist coordination. No explicit xdist-related overrides needed because `samstack` fixtures auto-detect worker ID.

---

## 3. Crash Recovery Test Design (TEST-02)

### Architectural considerations

The crash recovery path in Phases 8-11 works as follows:
1. gw0's `acquire_infra_lock()` succeeds → gw0 starts infrastructure
2. If gw0 fails during startup: `write_state_file("error", str(e))` → re-raise
3. gw1+ calls `wait_for_state_key("localstack_endpoint")` → detects `"error"` key → `pytest.fail()`
4. All gw1+ workers exit with clear error messages

To test this, we need to force gw0's Docker infrastructure to fail. Options:

**Option A: Bad SAM image** (D-05 recommends `sam_image="nonexistent:latest"`)
- Pro: Simple configuration override
- Con: SAM container might not even start — test may be too fast or not exercise the right code path

**Option B: Bad LocalStack image** (Alternative to D-05)
- Pro: gw0 starts successfully but LocalStack container fails to start → gw0 writes error
- Con: Still depends on Docker pull behavior

**Option C: Invalid Docker network configuration**
- Pro: gw0 processes start but network creation fails
- Con: Too implementation-specific

**Recommended: Option A (bad SAM image) with separate test suite**

The crash test needs its own conftest that overrides `samstack_settings` with an invalid `sam_image`. Following D-05 and D-06:
- `tests/xdist/test_crash/conftest.py`: Override `samstack_settings` with invalid config
- `tests/xdist/test_crash/test_crash.py`: Run as `subprocess.Popen` (not in-process — needs separate pytest session)
  - Launch `pytest tests/xdist/test_crash/ -n 2 --timeout=120` as subprocess
  - Capture stderr/stdout
  - Assert subprocess exits non-zero
  - Assert output contains `pytest.fail` or `pytest.skip` indicator
  - Assert no Docker API errors in output

**Important:** D-07 says the crash test should be a CI step. The approach:
1. Test file runs as a regular unit/integration test (no xdist in its own runner)
2. It spawns a `-n 2` subprocess with the crash conftest
3. Verifies clean exit

This follows the `test_warm_crash.py` pattern closely:

```python
def test_crash_recovery(tmp_path):
    # Write crash conftest to tmp_path
    # Launch: pytest tmp_path -n 2 --timeout=120
    # Assert: proc.returncode != 0
    # Assert: stderr/stdout contains skip/fail message
    # Assert: no "DockerException" etc.
```

### Wait — crash test complexity

The D-06 specifies: "gw0's Docker container fails to start → gw0 writes 'error' key → gw1+ wait_for_state_key detects error → pytest.fail() or pytest.skip() called"

But `wait_for_state_key` calls `pytest.fail()` (not `pytest.skip()`). The output should contain the fail message. The subprocess exit code will be non-zero (as expected for a failing test).

**Clean exit verification:** The key assertion is that the subprocess exits within the timeout (no hanging), and the exit is due to the expected fail message, not a Docker API error or cryptic traceback.

### D-07 CI considerations
- Crash test in CI: same as all other CI tests — `uv run pytest tests/xdist/test_crash.py -v`
- Not run with `-n 2` at top level (the subprocess inside uses `-n 2`)
- May need `--timeout=300` to allow for Docker pull latency

### D-14: Crash test can be separate step or skipped in CI
- Given Docker-in-Docker variance in CI runners, D-14 gives us flexibility
- Recommendation: Add to CI as a separate step with `continue-on-error: true` initially
- Flag it with CI annotations but don't block the pipeline

---

## 4. Benchmark Design (TEST-05)

### Requirements from D-10, D-11, D-12

D-10 specifies: `scripts/benchmark.py` using `subprocess` + `time.time()`:
- Runs pytest sequentially (baseline)
- Runs with `-n 2`, `-n 4`, `-n auto`
- Outputs table: runner, wall-clock time, test count, speedup factor vs baseline

D-11: No new dependencies. Use stdlib only.
D-12: Script, not CI job. Manual or ad-hoc.

### Design

```python
#!/usr/bin/env python3
"""Benchmark samstack test suite with and without pytest-xdist."""

import subprocess
import time
import sys

def run_pytest(extra_args):
    start = time.time()
    result = subprocess.run(
        ["uv", "run", "pytest", "tests/", "-v", "--timeout=300",
         "--ignore=tests/unit", "--ignore=tests/xdist",
         "--ignore=tests/warm", "--ignore=tests/multi_lambda",
         *extra_args],
        capture_output=True, text=True
    )
    elapsed = time.time() - start
    return elapsed, result.returncode

def main():
    configurations = [
        ("baseline", []),
        ("-n 2", ["-n", "2"]),
        ("-n 4", ["-n", "4"]),
        ("-n auto", ["-n", "auto"]),
    ]
    
    results = {}
    for name, args in configurations:
        print(f"Running {name}...")
        elapsed, code = run_pytest(args)
        results[name] = elapsed
        print(f"  {elapsed:.1f}s (exit {code})")
    
    baseline = results["baseline"]
    print(f"\n{'Runner':<12} {'Time':>8} {'Speedup':>8}")
    print("-" * 30)
    for name, elapsed in results.items():
        speedup = baseline / elapsed if elapsed > 0 else 0
        print(f"{name:<12} {elapsed:>7.1f}s {speedup:>7.2f}x")
```

**Key decision:** What tests to benchmark?
- The existing integration tests (`tests/test_sam_api.py`, `tests/test_sam_lambda.py`, resource tests) are the natural target
- Unit tests are too fast to show meaningful speedup
- The benchmark should use the fixed test suite (not xdist tests — those are new and may have variable timing)

The benchmark PID session reuse matters: under `-n 2`, gw0 creates infra and gw1+ reuse. Under `-n 4`, more workers share the same infra. The speedup comes from test execution parallelization, not infrastructure creation (which is already session-scoped and happens once).

**Expected results:**
- `-n 2`: expected 1.3-1.8x speedup (overhead of infra + test distribution)
- `-n 4`: expected 1.5-2.5x speedup (diminishing returns with fixed test count)
- Integration tests are I/O-bound (HTTP, Docker) so speedup is modest but measurable

---

## 5. Documentation Design (TEST-04)

### README Section Structure (D-08, D-09)

Following the existing README section style:

1. **Header:** `## Parallel testing with pytest-xdist`
2. **Brief intro paragraph:** One sentence explaining what it enables
3. **How it works:** One paragraph explaining gw0 owns Docker infra, gwN shares via state file (avoid implementation details)
4. **Installation:** Code block showing `uv add --group dev pytest-xdist`
5. **Usage:** Code blocks showing `-n 2`, `-n 4`, `-n auto`
6. **Supported `--dist` modes:** Table or bullet list
7. **CI recommendations:** Example GitHub Actions step (copy-pastable)
8. **Known limitations:** Bullet list

**Known limitations content (D-08):**
- No `--dist=each` or `--dist=no` — these duplicate Docker infrastructure
- No per-worker LocalStack isolation — all workers share one LocalStack instance
- No explicit worker-to-resource grouping — file-level parallelism only
- Crash test may be unreliable on macOS (Docker Desktop TCP proxy limitation)

**Placement (Claude's Discretion):**
After the "Mocking other Lambdas" section (mock is the most advanced feature; xdist is a deployment/scaling concern). Or before it — xdist is a testing infrastructure concern that applies to all fixtures.

Recommended: After the mock section, before "SAM image versions" — xdist is a cross-cutting concern that users should learn about after they understand the individual features.

### D-09: No fixture table updates
The xdist-awareness is transparent — all fixtures work without configuration changes. The documentation focuses on usage, not implementation. This is correct — the fixture reference table stays as-is.

---

## 6. CI Integration (TEST-01, TEST-02, D-13, D-14)

### Current CI structure

`.github/workflows/_ci.yml` is a reusable workflow with 4 jobs:
1. `quality-checks` — ruff format/lint + ty
2. `unit-tests` — pytest unit tests only
3. `integration-tests` — full integration tests excluding warm, unit, and test files. Has warm step.
4. `build` — package build (optional)

### Required additions (D-13)

Add xdist integration test step to `integration-tests` job:

```yaml
- name: Run xdist integration tests
  run: uv run pytest tests/xdist/ -v -n 2 --timeout=300 --ignore=tests/xdist/test_crash.py
```

This:
- Runs `tests/xdist/` with `-n 2`
- Excludes crash test (handled separately per D-14)
- Uses same timeout as other integration tests

### Crash test in CI (D-14)

Option 1 (separate step with continue-on-error):
```yaml
- name: Run xdist crash test
  continue-on-error: true
  run: uv run pytest tests/xdist/test_crash.py -v --timeout=300
```

Option 2: Skip in CI initially, add later after validating Docker-in-Docker behavior.

**Recommendation:** Option 1 — add as non-blocking step. If it fails, pipeline continues with annotation. Once validated across multiple CI runs, promote to blocking.

### Why not run ALL xdist tests with `-n 2`?
The crash test uses `subprocess` to launch its own `-n 2` session. Running it inside an already-xdist session would cause nested xdist (undefined behavior). It must run as a separate, non-xdist step.

---

## 7. Dependency Management

### D-04: Add `pytest-xdist>=3.6` to dev dependencies

Current `[dependency-groups] dev`:
```toml
dev = [
    "pytest>=8.0.0",
    "requests>=2.32.0",
    "boto3-stubs[lambda,s3,dynamodb,sqs,sns]>=1.35.0",
    "ruff>=0.15.2",
    "ty>=0.0.18",
    "pytest-timeout>=2.4.0",
]
```

Add: `"pytest-xdist>=3.6"`

### Why not a hard dependency?
`pytest-xdist` is only needed when running tests with `-n` flag. Making it a dependency would force all downstream users to install it, even if they never use xdist. Dev dependency is correct per Claude's Discretion.

---

## 8. Validation Architecture

### Unit-testable components
- Benchmark script: pure stdlib, testable by capturing subprocess output
- Crash test: uses subprocess, verifiable by pytest assertions on exit code/stdout

### Integration-testable components
- TEST-01: xdist integration suite runs against real Docker infra
- TEST-03: resource parallelism verified with real LocalStack

### Manual verification
- TEST-04: README section reviewed during PR
- TEST-05: benchmark script run manually, output verified

---

## 9. File Inventory

### Files to create
| File | Purpose | Dependencies |
|------|---------|--------------|
| `tests/xdist/conftest.py` | xdist suite configuration | `samstack.settings.SamStackSettings` |
| `tests/xdist/test_basic.py` | TEST-01: basic xdist integration | All samstack fixtures |
| `tests/xdist/test_resource_parallelism.py` | TEST-03: resource parallelism | Resource fixtures |
| `tests/xdist/test_crash/conftest.py` | Crash suite config with invalid image | `samstack.settings.SamStackSettings` |
| `tests/xdist/test_crash/test_crash.py` | TEST-02: crash recovery verification | `subprocess`, `docker` (optional) |
| `scripts/benchmark.py` | TEST-05: performance benchmark | `subprocess`, `time` (stdlib) |

### Files to modify
| File | Change | Requirement |
|------|--------|-------------|
| `tests/conftest.py` | Add `"xdist"` to `pytest_ignore_collect` | D-02 |
| `pyproject.toml` | Add `pytest-xdist>=3.6` to dev deps | D-04 |
| `README.md` | New "xdist parallel testing" section | D-08, TEST-04 |
| `.github/workflows/_ci.yml` | Add xdist integration test step + crash test step | D-13, D-14 |

---

## 10. Implementation Order

**Wave 1 (independent):**
- Plan A: Tests (`tests/xdist/`) — requires only existing samstack fixtures
- Plan B: Benchmark script (`scripts/benchmark.py`) — requires only stdlib + existing tests

**Wave 2 (depends on Wave 1):**
- Plan C: Docs + CI + Dependencies — README section references test command output; CI workflow references test paths created in Plan A

**Rationale:** Tests validate the xdist infrastructure; docs describe the validated behavior. Creating docs before tests would describe unverified behavior.

---

## Research Sources

- `.planning/phases/08-*` through `11-*` SUMMARY.md files — xdist implementation patterns
- `tests/conftest.py` — root conftest hook pattern
- `tests/multi_lambda/conftest.py` and `tests/warm/conftest.py` — isolated suite patterns
- `tests/integration/test_warm_crash.py` — crash test subprocess pattern
- `tests/fixtures/hello_world/` — Lambda fixture reused for xdist tests
- `src/samstack/_xdist.py` — coordination primitives (worker ID detection, state file, FileLock)
- `.github/workflows/_ci.yml` — CI job structure
- `README.md` — documentation style reference
- `pyproject.toml` — dependency management

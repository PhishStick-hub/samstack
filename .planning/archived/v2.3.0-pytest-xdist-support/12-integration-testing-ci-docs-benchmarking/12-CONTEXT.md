# Phase 12: Integration Testing, CI, Docs, & Benchmarking - Context

**Gathered:** 2026-05-01
**Status:** Ready for planning

<domain>
## Phase Boundary

End-to-end validation of pytest-xdist support across all fixture types, crash recovery verification, user documentation, and performance measurement. Add `pytest-xdist` to dev dependencies, create `tests/xdist/` integration test suite running with `-n 2`, verify crash recovery produces clean skip/fail messages, update README with xdist usage guide, and add a benchmark script to measure parallel speedup.

**Requirements:** TEST-01, TEST-02, TEST-03, TEST-04, TEST-05

</domain>

<decisions>
## Implementation Decisions

### Test suite structure
- **D-01:** Reuse `tests/fixtures/hello_world/` as the Lambda fixture for xdist integration tests. Already has GET/POST `/hello` API with S3 write, direct invoke, and per-service env vars declared in template. Fast to build, well-understood behavior.
- **D-02:** Create `tests/xdist/` directory with its own `conftest.py` overriding `samstack_settings` to point at `tests/fixtures/hello_world/`. Add `"xdist"` to `pytest_ignore_collect` in root `tests/conftest.py`.
- **D-03:** Test files in `tests/xdist/` organized by concern: one file for basic API/invoke sanity (TEST-01), one for resource fixture parallelism (TEST-03), one for crash recovery (TEST-02). Tests run with `pytest -n 2` (or `-n 4` for parallelism).
- **D-04:** Add `pytest-xdist>=3.6` to `[dependency-groups] dev` in pyproject.toml.

### Crash recovery strategy
- **D-05:** Create `tests/xdist/test_crash.py` with its own `conftest.py` that overrides `samstack_settings` to use `sam_image="nonexistent:latest"` (or invalid `localstack_image`). Run as a separate pytest session (same isolated suite pattern as multi_lambda/warm).
- **D-06:** Crash test assertions: within a `-n 2` session, gw0's Docker container fails to start → gw0 writes `"error"` key → gw1+ `wait_for_state_key` detects error → `pytest.fail()` or `pytest.skip()` called. Verify clean exit (no hanging, no cryptic Docker errors in output).
- **D-07:** Add CI step for crash test: `uv run pytest tests/xdist/test_crash.py -n 2 --timeout=300` (or wherever crash test lives). Expect non-zero exit code but clean output.

### Documentation scope
- **D-08:** New README section "Parallel testing with pytest-xdist" covering:
  - Installation: `uv add --group dev pytest-xdist`
  - How coordination works: one paragraph explaining gw0 owns Docker infra, gwN shares via state file
  - Usage: `pytest -n 2`, `pytest -n 4`, `pytest -n auto`
  - Supported `--dist` modes: `load` and `worksteal` only (not `each`/`no` — those duplicate Docker)
  - CI recommendations: example GitHub Actions step
  - Known limitations: no per-worker LocalStack, no explicit worker grouping, file-level parallelism only
- **D-09:** No updates to existing fixture tables. The xdist-awareness is transparent to users — all fixtures work without configuration changes. Documentation focuses on usage, not implementation.

### Benchmark approach
- **D-10:** Create `scripts/benchmark.py` using `subprocess` + `time.time()`. Runs pytest sequentially (baseline), then with `-n 2`, `-n 4`, `-n auto`. Outputs a table: runner, wall-clock time, test count, speedup factor vs baseline.
- **D-11:** No new dependencies for benchmarking. Use only stdlib.
- **D-12:** Benchmark is a script, not a CI job. Run manually or as needed. Not integrated into CI (adds CI runtime without proportional value for this milestone).

### CI updates
- **D-13:** Add xdist integration test step to `.github/workflows/_ci.yml` integration-tests job: `uv run pytest tests/xdist/ -v -n 2 --timeout=300 --ignore=tests/xdist/test_crash.py`. Keep crash test separate.
- **D-14:** Crash test in CI can be a separate step or skipped in CI initially (crash behavior depends on Docker-in-Docker in CI runner, which may differ from local).

### Claude's Discretion
- Exact test function names and organization within `tests/xdist/`
- Whether to run crash test in CI or only locally
- Error message wording in crash test assertions
- Whether to include `pytest-xdist` as optional or hard dev dependency
- README section exact wording and placement (after warm containers? after mock section?)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §TEST-01–TEST-05 — Phase 12 requirements (integration tests, crash recovery, resource parallelism, docs, benchmark)

### Existing patterns to follow
- `tests/conftest.py` — root conftest with `pytest_ignore_collect` pattern for isolated suites
- `tests/multi_lambda/conftest.py` — isolated suite conftest pattern: override `samstack_settings`, `sam_env_vars`, autouse mock fixtures
- `tests/warm/conftest.py` — another isolated suite example
- `tests/fixtures/hello_world/` — Lambda fixture reused for xdist tests
- `tests/fixtures/hello_world/template.yaml` — template with per-service env vars declared
- `tests/fixtures/hello_world/app/hello_world/app.py` — handler: GET/POST /hello, S3 write, direct invoke
- `.github/workflows/_ci.yml` — reusable CI workflow to modify

### Source files likely modified
- `tests/conftest.py` — add `"xdist"` to `pytest_ignore_collect`
- `pyproject.toml` — add `pytest-xdist` to dev deps
- `README.md` — new "Parallel testing with pytest-xdist" section
- `.github/workflows/_ci.yml` — add xdist integration test step

### Source files likely created
- `tests/xdist/conftest.py` — xdist suite config
- `tests/xdist/test_*.py` — test files (exact names at planner's discretion)
- `tests/xdist/test_crash/conftest.py` — crash test config (invalid image override)
- `tests/xdist/test_crash/test_crash.py` — crash recovery assertions
- `scripts/benchmark.py` — performance measurement script

### No external specs
No external specs — requirements fully captured in `.planning/REQUIREMENTS.md` and decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`pytest_ignore_collect` hook**: Root conftest already ignores `multi_lambda` and `warm` directories. Add `xdist` to the list.
- **Isolated suite pattern**: Each suite has its own `conftest.py` overriding `samstack_settings` to point at its fixture directory. No shared session fixtures between suites.
- **CI workflow** (`_ci.yml`): Three-job structure (quality-checks, unit-tests, integration-tests). Integration job already has separate warm step. Add xdist step following same pattern.
- **Existing unit tests**: 11 xdist unit test files covering all coordination logic. Integration tests only need to verify the real Docker path works end-to-end.

### Established Patterns
- **Separate pytest sessions**: Multi-lambda and warm suites run in dedicated pytest invocations to avoid session-scoped fixture conflicts. Same pattern for xdist suite.
- **Conftest override pattern**: Override `samstack_settings` fixture with `scope="session"` returning a `SamStackSettings` with different `project_root` and `template`.
- **README section style**: Each section has a header, brief explanation, code examples, and sometimes a table. Follow this style for the xdist section.

### Integration Points
- **xdist suite** depends on `samstack` plugin (already installed via `pytest11` entry point), `pytest-xdist` (new dev dep), and Docker (existing requirement)
- **CI** needs `pytest-xdist` available in the CI runner. The existing CI setup installs dev deps (`uv sync`), so adding `pytest-xdist` to dev deps makes it available automatically.
- **Benchmark script** depends on `pytest-xdist` for `-n` flag support. Runs from project root.

</code_context>

<specifics>
## Specific Ideas

No specific references or "I want it like X" moments. Follow existing isolated suite patterns from multi_lambda and warm test suites.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 12-integration-testing-ci-docs-benchmarking*
*Context gathered: 2026-05-01*

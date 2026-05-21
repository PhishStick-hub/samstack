---
phase: quick
plan: 260521-vdb
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - uv.lock
  - .github/workflows/_ci.yml
autonomous: true
requirements:
  - COV-01

must_haves:
  truths:
    - "uv run pytest --cov shows coverage report in terminal"
    - "CI pipeline fails when coverage drops below 70%"
    - "Coverage measurement covers src/samstack/ only, not test files"
  artifacts:
    - path: "pyproject.toml"
      provides: "pytest-cov dependency + coverage configuration"
      contains: "[tool.coverage.run]"
    - path: ".github/workflows/_ci.yml"
      provides: "coverage-gate CI job with enforced threshold"
      contains: "coverage-gate"
  key_links:
    - from: "[tool.coverage.run] in pyproject.toml"
      to: "pytest --cov invocation in CI"
      via: "coverage reads pyproject.toml config automatically"
      pattern: "tool\\.coverage\\.run"
    - from: "coverage-gate CI job"
      to: "CI pipeline status"
      via: "job failure when coverage < 70%"
      pattern: "fail-under"
---

<objective>
Add pytest-cov to the project with coverage configuration in pyproject.toml and a CI job that enforces a 70% coverage gate. Local test runs produce coverage reports automatically; CI fails PRs that drop below the threshold.

Purpose: Catch untested code paths before they ship — coverage regressions block merges.
Output: Working local + CI coverage with enforced 70% gate.
</objective>

<execution_context>
@/Users/ivan_shcherbenko/.config/opencode/get-shit-done/workflows/execute-plan.md
@/Users/ivan_shcherbenko/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@pyproject.toml
@.github/workflows/_ci.yml

### Key interface: existing CI structure
- `_ci.yml` has 4 jobs: `quality-checks`, `unit-tests`, `integration-tests`, `build`
- `quality-checks` runs ruff format, ruff check, ty check — fast (~30s)
- `unit-tests` runs fast no-Docker tests
- `integration-tests` depends on `quality-checks`, runs Docker tests
- Python 3.13, uv as package manager

### Current dev dependencies (from pyproject.toml)
```
pytest>=8.0.0, requests>=2.32.0, boto3-stubs[lambda,s3,dynamodb,sqs,sns]>=1.35.0,
ruff>=0.15.2, ty>=0.0.18, pytest-timeout>=2.4.0
```
No pytest-cov currently.

### Coverage source scope
- `src/samstack/` — 23 Python files across fixtures, resources, mock, _docker, _process, _constants, _errors, settings, plugin
- Tests live in `tests/` — excluded from coverage measurement
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add pytest-cov dependency and configure coverage in pyproject.toml</name>
  <files>pyproject.toml, uv.lock</files>
  <action>
    1. Add pytest-cov as a dev dependency:
       ```bash
       uv add --group dev pytest-cov
       ```

    2. Add `[tool.coverage.run]` and `[tool.coverage.report]` sections to `pyproject.toml`
       (append after the existing `[dependency-groups]` section):

       ```toml
       [tool.coverage.run]
       source = ["src/samstack"]
       branch = true

       [tool.coverage.report]
       fail_under = 70
       exclude_lines = [
           "pragma: no cover",
           "if TYPE_CHECKING:",
           "raise NotImplementedError",
           "if __name__ == .__main__.:",
       ]
       ```

    3. Add pytest-cov defaults to `[tool.pytest.ini_options]` so local `uv run pytest`
       automatically collects coverage without extra flags. Insert after the existing
       `filterwarnings` block:

       ```toml
       addopts = [
           "--cov=src/samstack",
           "--cov-report=term",
       ]
       ```

    The `addopts` means every `uv run pytest` invocation now produces a terminal
    coverage report. Individual test runs can override with `-p no:cov` if needed.
    The `fail_under = 70` is enforced by `coverage report`, not by pytest-cov's
    `--cov-fail-under` — this lets CI collect coverage across separate test runs
    (via `--cov-append`) and then enforce the gate once with a final
    `coverage report` call.

    Do NOT set `--cov-fail-under` in `addopts` — that would break test suites
    that intentionally run subsets of tests.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/ tests/test_settings.py tests/test_process.py tests/test_errors.py -q --no-cov-on-fail && grep -c "pytest-cov" pyproject.toml && grep -c "tool.coverage.run" pyproject.toml && grep -c "fail_under = 70" pyproject.toml</automated>
  </verify>
  <done>
    pytest-cov installed, pyproject.toml has `[tool.coverage.run]`, `[tool.coverage.report]`,
    and `addopts` sections. `uv run pytest` produces terminal coverage report.
  </done>
</task>

<task type="auto">
  <name>Task 2: Add coverage-gate CI job to _ci.yml</name>
  <files>.github/workflows/_ci.yml</files>
  <action>
    Add a new `coverage-gate` job to `.github/workflows/_ci.yml`. This job runs
    after `quality-checks` (in parallel with unit-tests and integration-tests) and
    runs ALL tests with coverage collection, then enforces the 70% gate.

    Insert after the `quality-checks` job (before `unit-tests`). The job:

    ```yaml
      coverage-gate:
        name: Coverage Gate (≥70%)
        runs-on: ubuntu-latest
        needs: [quality-checks]
        timeout-minutes: 25
        steps:
          - name: Checkout code
            uses: actions/checkout@v4
            with:
              ref: ${{ inputs.ref || github.ref }}

          - name: Install uv
            uses: astral-sh/setup-uv@v4
            with:
              enable-cache: true

          - name: Set up Python
            uses: actions/setup-python@v5
            with:
              python-version: "3.13"

          - name: Install dependencies
            run: uv sync --all-groups

          - name: Run unit tests (collect coverage)
            run: |
              uv run pytest tests/unit/ tests/test_settings.py \
                tests/test_process.py tests/test_errors.py \
                --cov=src/samstack --cov-report= \
                --cov-branch -v

          - name: Run integration tests (append coverage)
            run: |
              uv run pytest tests/ -v --timeout=300 \
                --ignore=tests/unit \
                --ignore=tests/test_settings.py \
                --ignore=tests/test_process.py \
                --ignore=tests/test_errors.py \
                --ignore=tests/warm \
                --ignore=tests/integration/test_warm_crash.py \
                --cov=src/samstack --cov-append --cov-report= \
                --cov-branch

          - name: Run warm integration tests (append coverage)
            run: |
              uv run pytest tests/warm/ -v --timeout=300 \
                --cov=src/samstack --cov-append --cov-report= \
                --cov-branch

          - name: Enforce coverage gate
            run: coverage report --fail-under=70
    ```

    **Design decisions:**
    - `--cov-report=` (empty) suppresses intermediate reports; only the final
      `coverage report` produces output, keeping CI logs clean.
    - `--cov-branch` enables branch coverage for stricter measurement.
    - `--cov-append` on integration + warm test steps accumulates into the same
      `.coverage` file so the final `coverage report` sees combined data.
    - 25-minute timeout covers cold-cache Docker pulls on first run.
    - The new job runs in PARALLEL with `unit-tests` and `integration-tests`
      jobs — it does NOT replace them. The existing jobs remain for fast
      feedback; coverage-gate is the authoritative enforcement step.
  </action>
  <verify>
    <automated>grep -c "coverage-gate:" .github/workflows/_ci.yml && grep -c "Enforce coverage gate" .github/workflows/_ci.yml && grep -c "fail-under=70" .github/workflows/_ci.yml</automated>
  </verify>
  <done>
    `_ci.yml` has a `coverage-gate` job that runs all tests with combined coverage
    and fails the pipeline if coverage drops below 70%.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

No new trust boundaries introduced. Coverage tooling is local dev + CI only;
no external services, no user data exposure.

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Tampering | `.coverage` file | accept | Local CI artifact; low-value target, ephemeral |
| T-quick-02 | Information Disclosure | coverage XML report | accept | No XML artifact uploaded in this plan; terminal-only output |
</threat_model>

<verification>
1. **Local coverage:** `uv run pytest tests/unit/ -q` produces terminal coverage report showing `src/samstack/` files
2. **Gate enforcement:** `uv run coverage report --fail-under=100` exits non-zero (proves gate works); `uv run coverage report --fail-under=50` exits zero
3. **CI config:** `grep -c "coverage-gate" .github/workflows/_ci.yml` returns ≥ 1
</verification>

<success_criteria>
- [ ] `pytest-cov` in `[dependency-groups].dev` in pyproject.toml
- [ ] `[tool.coverage.run]` with `source = ["src/samstack"]` and `branch = true`
- [ ] `[tool.coverage.report]` with `fail_under = 70`
- [ ] `addopts` in `[tool.pytest.ini_options]` with `--cov=src/samstack --cov-report=term`
- [ ] `coverage-gate` job in `_ci.yml` runs after `quality-checks`
- [ ] Coverage gate job runs unit → integration → warm tests in sequence with `--cov-append`
- [ ] Final step enforces `coverage report --fail-under=70`
</success_criteria>

<output>
After completion, create `.planning/quick/260521-vdb-add-pytest-cov-coverage-tracking-with-en/260521-vdb-SUMMARY.md`
</output>

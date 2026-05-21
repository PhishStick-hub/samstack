---
phase: quick
plan: 260521-vdb
tags: [coverage, ci, pytest-cov, dev-tooling]
type: execute
status: complete
completion_date: "2026-05-21"
key-decisions:
  - "use --cov-append across CI test runs for combined coverage"
  - "coverage gate enforcement via `coverage report --fail-under=70` not pytest-cov's --cov-fail-under"
  - "addopts in pyproject.toml for automatic coverage on every local pytest run"
tech-stack:
  added: ["pytest-cov >=7.1.0", "coverage >=7.14.0"]
  patterns:
    - "CI coverage accumulation with --cov-append across parallel test suites"
    - "pyproject.toml-based coverage configuration (tool.coverage.run/report)"
key-files:
  created: []
  modified:
    - pyproject.toml
    - uv.lock
    - .github/workflows/_ci.yml
    - .gitignore
duration: 3 min
requires: []
provides: ["coverage-tracking"]
affects: ["CI pipeline"]
---

# Quick Task 260521-vdb: Add pytest-cov Coverage Tracking with Enforced 70% Gate

**One-liner:** Added pytest-cov dependency, pyproject.toml coverage configuration, and CI coverage-gate job that fails PRs below 70% branch coverage.

## Summary

This quick task adds coverage measurement to the samstack project. pytest-cov is installed as a dev dependency, coverage is configured via `[tool.coverage.run]` and `[tool.coverage.report]` sections in pyproject.toml, and a new `coverage-gate` CI job runs all test suites with combined coverage accumulation, failing the pipeline if branch coverage drops below 70%.

## Tasks Executed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Add pytest-cov dependency and configure coverage | `f114fc2` | `pyproject.toml`, `uv.lock` |
| 2 | Add coverage-gate CI job | `25001d9` | `.github/workflows/_ci.yml` |
| — | Auto-fix: add .coverage to gitignore | `2a1790d` | `.gitignore` |

## Commits

| Hash | Type | Message |
|------|------|---------|
| `f114fc2` | feat | feat(quick-260521-vdb): add pytest-cov dependency and coverage config |
| `25001d9` | feat | feat(quick-260521-vdb): add coverage-gate CI job with 70% threshold |
| `2a1790d` | chore | chore(quick-260521-vdb): add .coverage and htmlcov/ to gitignore |

## Decisions Made

1. **Coverage accumulation strategy:** Each CI test suite (unit, integration, warm) runs with `--cov-append` into a shared `.coverage` file. The final `coverage report --fail-under=70` enforces the gate on combined data.

2. **Gate enforcement location:** The 70% threshold is enforced via `coverage report --fail-under=70` in CI (not pytest-cov's `--cov-fail-under`). This allows local test subsets to run without false gate failures, while CI accumulates full coverage before enforcement.

3. **Automatic local coverage:** `addopts` in `[tool.pytest.ini_options]` adds `--cov=src/samstack --cov-report=term` to every `uv run pytest` invocation. Individual runs can opt out with `-p no:cov`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `.coverage` and `htmlcov/` to .gitignore**
- **Found during:** Post-Task 2 cleanup
- **Issue:** Running tests with coverage generates a `.coverage` data file that was not gitignored
- **Fix:** Added `.coverage` and `htmlcov/` entries to `.gitignore`
- **Files modified:** `.gitignore`
- **Commit:** `2a1790d`

## Verification

- [x] pytest-cov in `[dependency-groups].dev` in pyproject.toml
- [x] `[tool.coverage.run]` with `source = ["src/samstack"]` and `branch = true`
- [x] `[tool.coverage.report]` with `fail_under = 70`
- [x] `addopts` in `[tool.pytest.ini_options]` with `--cov=src/samstack --cov-report=term`
- [x] `coverage-gate` job in `_ci.yml` runs after `quality-checks`
- [x] Coverage gate job runs unit → integration → warm tests in sequence with `--cov-append`
- [x] Final step enforces `coverage report --fail-under=70`

## Known Stubs

None — all changes are configuration-only (pyproject.toml, CI workflow, .gitignore); no application code stubs introduced.

## Threat Flags

None — no new trust boundaries, network endpoints, auth paths, or file access patterns. Changes are local dev tooling and CI configuration only.

## Self-Check: PASSED

- [x] `pyproject.toml` exists and contains pytest-cov, tool.coverage.run, tool.coverage.report, addopts
- [x] `.github/workflows/_ci.yml` exists and contains coverage-gate job
- [x] `.gitignore` exists and contains `.coverage` entry
- [x] Commit `f114fc2` exists in git log
- [x] Commit `25001d9` exists in git log
- [x] Commit `2a1790d` exists in git log

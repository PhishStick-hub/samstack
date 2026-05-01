---
phase: 12-integration-testing-ci-docs-benchmarking
plan: 02
subsystem: "docs, ci, benchmarking"
tags: ["benchmark", "xdist", "docs", "ci", "parallel-testing"]
depends_on: []
requires: ["12-01"]
provides: ["benchmark-script", "xdist-readme-docs", "xdist-ci-steps"]
affects: ["README.md", ".github/workflows/_ci.yml", "pyproject.toml"]
tech-stack:
  added: []
  patterns: ["stdlib-only-benchmark", "README-section-insertion"]
key-files:
  created:
    - "scripts/benchmark.py (100 lines) — stdlib-only benchmark comparing baseline vs -n 2/4/auto"
  modified:
    - "README.md (+67 lines) — new 'Parallel testing with pytest-xdist' section"
    - ".github/workflows/_ci.yml (+7 lines) — xdist integration + crash test CI steps"
    - "uv.lock (synced after dependency resolution)"
decisions:
  - "Benchmark uses time.perf_counter() for precision; targets integration test files only"
  - "CI crash test uses continue-on-error: true per D-14 — Docker-in-Docker behavior varies"
  - "README section placed after Mocking other Lambdas, before SAM image versions"
metrics:
  duration: "8m 55s"
  completed_date: "2026-05-01T10:33:42Z"
---

# Phase 12 Plan 02: User-Facing xdist Deliverables Summary

**One-liner:** Added performance benchmark script (stdlib-only), complete xdist README documentation section, and CI workflow steps for xdist integration and crash tests.

## Completed Tasks

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Create benchmark script | `e7bfe18` | `scripts/benchmark.py` |
| 2 | Add xdist parallel testing section to README | `4022bb6` | `README.md` |
| 3 | Add pytest-xdist dev dependency and update CI workflow | `04f96c5` | `.github/workflows/_ci.yml`, `uv.lock` |

## What Was Built

### Task 1: Benchmark Script
`scripts/benchmark.py` — Uses stdlib only (`subprocess`, `time`, `sys`). Runs the integration test suite under baseline (sequential), `-n 2`, `-n 4`, and `-n auto` configurations. Measures wall-clock time via `time.perf_counter()`, outputs a formatted speedup table. Handles subprocess timeouts and errors gracefully.

### Task 2: README Documentation
New `## Parallel testing with pytest-xdist` section inserted after "Mocking other Lambdas" and before "SAM image versions". Covers:
- Installation (`uv add --group dev pytest-xdist`)
- Usage examples (`-n 2`, `-n 4`, `-n auto`)
- How it works (gw0 manages Docker, gwN+ shares via state file)
- Supported `--dist` modes table (load/worksteal ✅, each/no ❌)
- CI setup with copy-pastable GitHub Actions YAML
- Known limitations (no per-worker LocalStack, file-level parallelism, macOS crash caveat)

### Task 3: CI Integration
Added two new steps to the `integration-tests` job in `.github/workflows/_ci.yml`:
- **xdist integration tests:** `pytest tests/xdist/ -n 2 --timeout=300 --ignore=tests/xdist/test_crash.py`
- **xdist crash test:** `pytest tests/xdist/test_crash/ --timeout=300` with `continue-on-error: true`

`pytest-xdist>=3.8.0` was already present in `[dependency-groups] dev` from plan 12-01. Lockfile synced with `uv lock`.

## Verification Results

### Automated Checks
- `ruff check` / `ruff format --check`: ✅ All passed
- `ty check`: ✅ All passed
- `uv lock --check`: ✅ Lockfile in sync
- Benchmark script runs and outputs speedup table with correct headers

### Acceptance Criteria
| Criterion | Status |
|-----------|--------|
| Benchmark script uses only stdlib | ✅ |
| Benchmark outputs Configuration/Time/Speedup table | ✅ |
| README section appears exactly once, after Mocking section | ✅ |
| README includes installation, usage, dist modes, CI setup, limitations | ✅ |
| CI has xdist integration step with `-n 2` | ✅ |
| CI crash test step has `continue-on-error: true` | ✅ |
| Lockfile in sync | ✅ |

## Deviations from Plan

### Pre-existing dependency superset

**1. [Minor] pytest-xdist version already ≥3.8.0 from plan 12-01**
- **Found during:** Task 3
- **Issue:** Plan specified `pytest-xdist>=3.6`, but plan 12-01 already installed `>=3.8.0`. The acceptance criterion `grep "pytest-xdist>=3.6"` does not match the literal string `>=3.8.0`.
- **Fix:** No change needed — `>=3.8.0` satisfies `>=3.6`. Dependency is present and correct.
- **Files:** `pyproject.toml` (unchanged — already correct)

### Acceptance criteria precision

**2. [Minor] `grep "pytest -n 2"` doesn't match due to test path between `pytest` and `-n`**
- **Found during:** Task 2 verification
- **Issue:** README usage examples use `uv run pytest tests/ -n 2` format. The acceptance criterion's grep pattern `"pytest -n 2"` expects `pytest` immediately followed by ` -n 2`, but `tests/` appears between them. The plan's own `must_haves.key_links` uses the correct pattern `pytest.*-n`.
- **Fix:** No code change needed — the documentation is correct and the `key_links` pattern `pytest.*-n` matches correctly (4 occurrences). The acceptance criterion is slightly imprecise but the intent is fully satisfied.

## Self-Check: PASSED

- [x] `scripts/benchmark.py` exists and is executable
- [x] README.md contains `## Parallel testing with pytest-xdist` section
- [x] `.github/workflows/_ci.yml` contains xdist integration and crash test steps
- [x] `uv.lock` is in sync with `pyproject.toml`
- [x] All 3 commits verified: `e7bfe18`, `4022bb6`, `04f96c5`

All files exist and all commits are present in git history.

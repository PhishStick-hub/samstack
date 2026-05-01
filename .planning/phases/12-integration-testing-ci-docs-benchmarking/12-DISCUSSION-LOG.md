# Phase 12: Integration Testing, CI, Docs, & Benchmarking - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-01
**Phase:** 12-integration-testing-ci-docs-benchmarking
**Areas discussed:** Test suite structure, Crash recovery strategy, Documentation scope, Benchmark approach

---

## Test suite structure

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse hello_world | Use existing hello_world fixture for xdist integration tests. Already has API, S3, invoke. Fast to build. Env vars declared. | ✓ |
| New xdist-specific fixture | Create purpose-built fixture exercising all 4 resource types from one Lambda. | |
| Split fixtures | hello_world for API/invoke, dedicated fixture for resources. | |

**User's choice:** Reuse `tests/fixtures/hello_world/` — simplest, already well-understood, covers both API and invoke patterns.

**Notes:** New `tests/xdist/` directory with own conftest, added to root `pytest_ignore_collect`. `pytest-xdist>=3.6` added to dev deps.

---

## Crash recovery strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Invalid image via conftest | Separate conftest overrides sam_image to "nonexistent:latest". Docker fails on start, gw0 writes error, gw1+ exits cleanly. | ✓ |
| Monkeypatch inside test | Change image after collection. Breaks because session fixtures already resolved. | |
| Subprocess invocation | Shell out to pytest -n 2, parse exit code and output. | |

**User's choice:** Invalid image via conftest — clean, reproducible, follows isolated suite pattern.

**Notes:** Crash test runs as a separate pytest session (like multi_lambda/warm). CI step may be separate or local-only initially.

---

## Documentation scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full README section | Installation, coordination explanation, usage examples, --dist modes, CI snippet, known limitations. | ✓ |
| Full README + fixture table updates | Full section plus badges/notes on xdist-aware fixtures in existing tables. | |
| Minimal paragraph | Short paragraph linking to pytest-xdist docs. | |

**User's choice:** Full README section covering all usage aspects. Follows existing section style.

**Notes:** No fixture table updates — xdist-awareness is transparent to users. Documentation focuses on how to use, not how it works internally.

---

## Benchmark approach

| Option | Description | Selected |
|--------|-------------|----------|
| Simple script | `scripts/benchmark.py` using subprocess + time. Table output: runner, time, tests, speedup. | ✓ |
| pytest-benchmark library | Add dependency, use benchmark markers. More statistical rigor but adds dep. | |
| CI-integrated job | Non-blocking CI job with artifact storage and trend tracking. | |

**User's choice:** Simple script — no new dependencies, easy to run manually.

**Notes:** Benchmark is a manual tool, not CI-integrated. Uses only stdlib.

---

## Claude's Discretion

- Exact test function names and file organization within `tests/xdist/`
- Whether to run crash test in CI or only locally
- Error message wording in crash test assertions
- Whether pytest-xdist is optional or hard dev dependency
- README section placement and exact wording

## Deferred Ideas

None — discussion stayed within phase scope.

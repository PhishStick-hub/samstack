# samstack

## What This Is

`samstack` is a pytest plugin that runs AWS SAM + LocalStack entirely inside Docker. All samstack-managed infrastructure — Docker bridge network, main container fixtures (LocalStack, SAM API, SAM Lambda), and SAM-spawned Lambda runtime sub-containers — is crash-safe via testcontainers Ryuk reaper integration. A SIGKILL mid-run leaves nothing behind. Per-function warm container control allows testers to selectively pre-warm specific Lambda functions for predictable test performance.

## Core Value

No leftover Docker containers or networks after a crashed pytest session.

## Current State

v2.3.0 — "pytest-xdist Support" — complete. All 5 phases (8-12), 9 plans shipped. Full details in MILESTONES.md.

## Current Milestone: v2.3.0 pytest-xdist Support

**Goal:** Enable downstream projects to run tests in parallel via pytest-xdist, with a single shared set of Docker infrastructure across all workers.

**Target features:**
- Worker 0 manages shared Docker infra (LocalStack + SAM + network)
- Worker ID auto-detection — no user-level fixture wiring
- SAM build + warm containers run once on worker 0
- Per-worker function-scoped AWS resources preserved as-is
- Shared spy buckets for samstack.mock
- Fail-fast with skip cascade on infra failure

## Requirements

### Validated

- ✓ Session-scoped SAM and LocalStack containers via Docker — existing
- ✓ Docker network isolation (`samstack-{uuid8}`) with teardown cleanup — existing
- ✓ AWS resource fixtures (S3, DynamoDB, SQS, SNS) via LocalStack — existing
- ✓ Lambda mock spy for Lambda-to-Lambda testing — existing
- ✓ `docker_network` fixture stops and removes containers on normal teardown — existing
- ✓ Docker network labeled with `org.testcontainers.session-id` and registered with Ryuk — v2.0.0 Phase 1
- ✓ Ryuk network cleanup verified via automated SIGKILL crash test — v2.0.0 Phase 1
- ✓ CI-safe Ryuk bypass when `ryuk_disabled=True` — v2.0.0 Phase 1
- ✓ LocalStack and SAM containers verified to carry Ryuk session label after `.start()` — v2.0.0 Phase 2
- ✓ SAM Lambda runtime sub-container cascade cleanup empirically verified on both crash and normal teardown paths — v2.0.0 Phase 3
- ✓ Per-function warm container configuration via fixtures or `SamStackSettings` — v2.2.0 Phase 4
- ✓ Lazy vs eager warm strategy selectable per function — v2.2.0 Phases 5-6
- ✓ Fixture/API for pre-warming specific functions before test execution — v2.2.0 Phases 5-6
- ✓ start-api pre-warm via warm_api_routes fixture and HTTP GET requests — v2.2.0 Phase 6
- ✓ Integration tests verify pre-warmed containers stay warm across multiple invocations — v2.2.0 Phase 7
- ✓ Crash test verifies warm sub-containers cleaned up on SIGKILL via Ryuk cascade — v2.2.0 Phase 7
- ✓ Public documentation covers configuration, fixtures, and known limitations — v2.2.0 Phase 7
- ✓ Import-safe xdist worker detection and FileLock-guarded singleton creation — v2.3.0 Phase 8
- ✓ Shared JSON state file for cross-worker endpoint + build coordination — v2.3.0 Phase 8
- ✓ Xdist-aware docker_network with gw0-create/gw1+-wait pattern — v2.3.0 Phase 8
- ✓ Shared LocalStack container serving all xdist workers via _LocalStackContainerProxy — v2.3.0 Phase 9
- ✓ sam_build runs once on gw0 with build_complete state flag for gw1+ — v2.3.0 Phase 9
- ✓ Resource fixture per-worker isolation preserved via UUID4 naming — v2.3.0 Phase 9
- ✓ SAM API container shared across xdist workers (gw0 creates, gw1+ reads URL) — v2.3.0 Phase 10
- ✓ SAM Lambda container shared across xdist workers — v2.3.0 Phase 10
- ✓ Warm container coordination across xdist workers — v2.3.0 Phase 11
- ✓ samstack.mock spy buckets compatible with xdist — v2.3.0 Phase 11
- ✓ End-to-end xdist integration test suite — v2.3.0 Phase 12
- ✓ Crash recovery test for xdist workers — v2.3.0 Phase 12
- ✓ xdist usage documentation and README updates — v2.3.0 Phase 12
- ✓ Performance benchmark (plain vs xdist suite times) — v2.3.0 Phase 12

### Active

### Out of Scope

- Migrate `docker_network` to `testcontainers.core.network.Network` — breaking API change for consumers who override the fixture; deferred to v3
- Pre-session stale container scan — user chose Ryuk-first approach; v2.0.0 satisfies immediate need
- Ryuk tracking of containers in child/consumer projects — only samstack's own infra
- Rootless Docker / Podman support — documented limitation, separate concern

## Context

Shipped v2.0.0 with 3 phases, 5 plans (Ryuk crash-safe infrastructure). Shipped v2.2.0 with 4 phases, 6 plans (per-function warm containers). Shipped v2.3.0 with 5 phases, 9 plans (pytest-xdist support). Total: 20 plans across 12 phases.

v2.2.0 features: per-function warm container configuration via `warm_functions` in settings/fixtures, selective pre-warming for start-lambda (boto3 invoke) and start-api (HTTP GET), init-marker UUID pattern for deterministic warm container verification, warm sub-container Ryuk cascade crash test, and complete README documentation.

v2.3.0 features: pytest-xdist worker detection and gw0-only Docker infrastructure management, shared LocalStack/SAM containers across all workers via JSON state files with FileLock coordination, per-worker AWS resource isolation via UUID4 naming, samstack.mock spy bucket sharing, fail-fast with skip cascade on gw0 failure, xdist integration test suite with resource parallelism and crash recovery tests, performance benchmark, and user documentation.

Key files: `src/samstack/_xdist.py` (worker coordination, state file, infra lock), `src/samstack/fixtures/localstack.py` (gw0-only LocalStack, gw1+ proxy), `src/samstack/fixtures/sam_build.py` (gw0-only build), `src/samstack/fixtures/sam_api.py` (gw0-only API start, gw1+ URL read), `src/samstack/fixtures/sam_lambda.py` (gw0-only lambda start), `src/samstack/fixtures/resources.py` (UUID4 per-worker naming), `tests/xdist/` (integration + crash test suites), `scripts/benchmark.py` (performance measurement).

## Constraints

- **Tech**: testcontainers-python Ryuk API must be used without bypassing the existing `DockerContainer` abstraction
- **Compatibility**: Must not break the existing `docker_network` teardown path (normal runs must still clean up)
- **Platform**: Crash test skips on macOS (Docker Desktop TCP proxy limitation); all other tests run everywhere

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Ryuk integration over pre-session cleanup | Ryuk fires immediately on process death vs. only at next run start | ✓ Good — v2.0.0 shipped, crash test verifies cleanup |
| All samstack containers targeted via network-level cleanup | Simplest complete solution; SAM sub-containers attach to network | ✓ Good — network removal cascades to attached containers |
| None guard on `Reaper._socket` before `.send()` | ty flagged `Optional[socket]`; correctness fix per Rule 2 | ✓ Good — prevents `AttributeError` on failed connection |
| Crash test uses Docker API label filter | More reliable than parsing subprocess stdout | ✓ Good — clean test, no fragile string matching |
| Sub-container cascade hard-asserted with 30s timeout | D-10 previously deferred to Phase 3; now empirically verified | ✓ Good — crash test asserts `sam_` containers gone |
| Dual-path verification (crash + normal teardown) | Crash for Ryuk cascade, normal for `_teardown_network` | ✓ Good — both paths verified |
| Label inspection for container fixtures (no crash test) | Containers use testcontainers `.start()` — known registered | ✓ Good — 3/3 container types verified |
| `warm_functions` as `list[str]` with overridable fixture | Simple config model; TOML + conftest.py override works cleanly | ✓ Good — 3 requirements resolved in Phase 4 |
| LAZY when warm_functions non-empty, EAGER when empty | Backward compatible default; opt-in to per-function control | ✓ Good — migrations require no config changes |
| Sequential pre-warm with single-attempt hard-fail | Avoids race conditions; surfaces issues immediately at session start | ✓ Good — both path tests pass |
| Init-marker UUID pattern for warm container verification | Deterministic, immune to timing jitter; proves container reuse | ✓ Good — both start-lambda and start-api paths verified |
| Warm container crash test as separate file | Distinct prerequisites (full SAM + pre-warm) from network-only crash test | ✓ Good — skips correctly on macOS |
| `_LocalStackContainerProxy` with `get_url()` return the endpoint | Transparent to all downstream fixtures — zero code changes to resources.py, plugin.py, or any boto3 client fixture | ✓ Good — 13 unit tests pass |
| 300s `build_complete` timeout on gw1+ wait | Cold-cache SAM builds with Docker pulls can take 2-3 minutes; 120s default insufficient | ✓ Good — 6 unit tests pass |
| UUID4 per-call naming preserves per-worker isolation | Each xdist worker has independent UUID4 stream; no code changes to resources.py required | ✓ Good — INFRA-04 satisfied, 10 validation tests pass |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-05-01 after Phase 12 (integration-testing-ci-docs-benchmarking) — v2.3.0 complete*

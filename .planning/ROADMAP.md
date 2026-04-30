# Roadmap: samstack

## Overview

samstack is a pytest plugin that runs AWS SAM CLI + LocalStack entirely inside Docker. The journey from v2.0.0 crash-safe infrastructure through v2.2.0 per-function warm containers to v2.3.0 pytest-xdist parallel test support.

## Milestones

- ✅ **v2.0.0 Orphan Container Cleanup** — Phases 1-3 (shipped 2026-04-25)
- ✅ **v2.2.0 Per-Function Warm Containers** — Phases 4-7 (shipped 2026-04-25)
- 🚧 **v2.3.0 pytest-xdist Support** — Phases 8-12 (in progress)

## Phases

<details>
<summary>✅ v2.0.0 Orphan Container Cleanup (Phases 1-3) — SHIPPED 2026-04-25</summary>

### Phase 1: Ryuk Network Wiring
**Goal**: Docker network registered with Ryuk for crash-safe cleanup
**Plans**: 2 plans
**Requirements**: NET-01, NET-02, NET-03

### Phase 2: Container Label Verification
**Goal**: All three main container fixtures carry Ryuk session labels
**Plans**: 1 plan
**Requirements**: LABEL-01, LABEL-02

### Phase 3: Sub-Container Cascade & Crash Testing
**Goal**: SAM Lambda runtime sub-containers cleaned up via network cascade on crash
**Plans**: 2 plans
**Requirements**: CASCADE-01, CASCADE-02, CASCADE-03

</details>

<details>
<summary>✅ v2.2.0 Per-Function Warm Containers (Phases 4-7) — SHIPPED 2026-04-25</summary>

### Phase 4: Warm Container Configuration
**Goal**: Per-function warm container configuration via settings and fixtures
**Plans**: 2 plans
**Requirements**: WARM-01, WARM-02, WARM-03

### Phase 5: start-lambda Pre-Warming
**Goal**: Direct Lambda invocation pre-warms selected functions in start-lambda mode
**Plans**: 1 plan
**Requirements**: WARM-04, WARM-05

### Phase 6: start-api Pre-Warming
**Goal**: HTTP-based pre-warming for selected functions in start-api mode
**Plans**: 1 plan
**Requirements**: WARM-06, WARM-07

### Phase 7: Warm Container Verification & Docs
**Goal**: Integration tests prove warm container reuse; crash test verifies cleanup; docs complete
**Plans**: 2 plans
**Requirements**: WARM-08, WARM-09, WARM-10, WARM-11, WARM-12

</details>

### 🚧 v2.3.0 pytest-xdist Support (In Progress)

**Milestone Goal:** Enable downstream projects to run tests in parallel via pytest-xdist, with a single shared set of Docker infrastructure across all workers. Worker 0 manages all Docker lifecycle; workers 1+ read endpoint URLs from a shared JSON state file. Non-xdist backward compatibility is preserved with zero user-facing changes.

#### Phase 8: Core Xdist Coordination
**Goal**: Downstream projects detect xdist worker context automatically and coordinate singleton infrastructure creation via FileLock and shared state file
**Depends on**: Nothing (first phase of v2.3.0)
**Requirements**: COORD-01, COORD-02, COORD-03, COORD-04, COORD-05
**Success Criteria** (what must be TRUE):
  1. A downstream project running `pytest -n 4` with samstack installed sees gw0 auto-detected as the infrastructure owner without any conftest.py configuration
  2. A developer running plain `pytest` (no xdist) sees all existing fixture behavior preserved with zero changes to their test suite
  3. When gw0 fails during infrastructure startup, gw1+ workers receive a clear `pytest.skip()` message within 120 seconds instead of hanging indefinitely
  4. Concurrent pytest sessions on the same host use separate state files and do not interfere with each other
  5. Unit tests verify FileLock acquisition, state file read/write, and worker role detection without Docker dependencies
**Plans**: 2 plans

Plans:
- [x] 08-01-PLAN.md — Coordination core: `_xdist.py` module (worker detection, state file I/O, FileLock) + unit tests
- [x] 08-02-PLAN.md — Fixture integration: xdist-aware `docker_network` with skip cascade + backward compat verification

#### Phase 9: Docker Infra Xdist-Awareness
**Goal**: Shared LocalStack container, Docker network, and sam build output serve all xdist workers while preserving per-worker AWS resource isolation
**Depends on**: Phase 8
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05
**Success Criteria** (what must be TRUE):
  1. A downstream project running `pytest -n 4` with S3/DynamoDB/SQS/SNS resource fixtures sees a single LocalStack container serving all four workers
  2. Tests in different workers create and use uniquely-named S3 buckets, DynamoDB tables, SQS queues, and SNS topics without cross-worker data collisions
  3. Only gw0's session teardown stops the Docker containers and removes the network; gw1+ workers exit without Docker API errors
  4. `sam build` executes exactly once (on gw0); gw1+ workers wait for the build completion flag and proceed when the build output directory is ready
**Plans**: 2 plans

Plans:
- [x] 09-01-PLAN.md — localstack_container + localstack_endpoint xdist-awareness (gw1+ proxy, shared endpoint)
- [x] 09-02-PLAN.md — sam_build xdist-awareness (build_complete flag, gw1+ wait) + resource fixture verification (INFRA-04)

#### Phase 10: SAM API + Lambda Xdist-Awareness
**Goal**: Shared SAM API and Lambda containers serve all workers for both HTTP and boto3 invocation patterns, including warm container reuse
**Depends on**: Phase 9
**Requirements**: SERV-01, SERV-02, SERV-03, SERV-04
**Success Criteria** (what must be TRUE):
  1. A downstream project running `pytest -n 3` with HTTP API tests sees all three workers sending requests to a single SAM start-api container
  2. A downstream project running `pytest -n 3` with Lambda invocation tests sees `lambda_client.invoke()` working from all three workers against a single SAM start-lambda container
  3. Pre-warmed Lambda containers (configured via `warm_functions`) are created once by gw0 and serve warm invocation requests from all workers
**Plans**: 2 plans

Plans:
- [x] 10-01-PLAN.md — `sam_api` fixture xdist-awareness (gw0 create + pre-warm, gw1+ wait, SERV-01 + SERV-04)
- [x] 10-02-PLAN.md — `sam_lambda_endpoint` fixture xdist-awareness (gw0 create + pre-warm, gw1+ wait, lambda_client unchanged, SERV-02 + SERV-03 + SERV-04)

#### Phase 11: Mock Coordination
**Goal**: Lambda mock spy buckets and env-var wiring work transparently across all xdist workers
**Depends on**: Phase 10
**Requirements**: MOCK-01, MOCK-02, MOCK-03
**Success Criteria** (what must be TRUE):
  1. A downstream project running `pytest -n 2` with the multi_lambda mock pattern sees gw1+ worker tests reading spy events written by Lambda invocations originating from any worker
  2. Mock env vars (`MOCK_SPY_BUCKET`, `MOCK_FUNCTION_NAME`) are correctly injected into SAM containers so that Lambda code running inside SAM receives the right mock configuration regardless of which worker triggered the build
  3. Multiple workers simultaneously writing spy events to the shared bucket do not experience key collisions or data corruption
**Plans**: TBD

#### Phase 12: Integration Testing, CI, Docs, & Benchmarking
**Goal**: End-to-end validation of xdist support across all fixture types, crash recovery verification, documented usage, and measured performance
**Depends on**: Phase 11
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05
**Success Criteria** (what must be TRUE):
  1. A dedicated `-n 2` integration test suite passes: workers share Docker infra, resource fixtures are per-worker isolated, mock spy buckets are shared, and crashes produce clean skip messages
  2. A crash recovery test kills gw0 mid-startup and verifies gw1+ exits with `pytest.skip()` within the timeout window without error spew or dangling Docker containers
  3. A resource parallelism test runs `-n 4` with simultaneous S3/DynamoDB/SQS/SNS read/write operations from all workers and passes without cross-worker interference
  4. The README contains an "xdist parallel testing" section with configuration instructions, `-n` flag usage, supported `--dist` modes, CI recommendations, and documented known limitations
  5. A benchmark reports baseline (plain `pytest`) vs. xdist (`-n 2/4/auto`) execution times with a measurable speedup factor
**Plans**: TBD

## Progress

Execution order: 8 → 9 → 10 → 11 → 12

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 8. Core Xdist Coordination | 2/2 | Complete | 2026-04-30 |
| 9. Docker Infra Xdist-Awareness | 2/2 | Complete | 2026-05-01 |
| 10. SAM API + Lambda Xdist-Awareness | 2/2 | Complete   | 2026-04-30 |
| 11. Mock Coordination | 0/TBD | Not started | - |
| 12. Integration Testing, CI, Docs | 0/TBD | Not started | - |

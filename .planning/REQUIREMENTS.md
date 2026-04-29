# Requirements: samstack v2.3.0 — pytest-xdist Support

**Defined:** 2026-04-30
**Core Value:** No leftover Docker containers or networks after a crashed pytest session

## v2.3.0 Requirements

### Coordination (COORD)

- [ ] **COORD-01**: Import-safe detection of active xdist worker — `worker_id` fixture and `is_xdist_worker()` helper identify gw0, gwN, or master (no xdist). Works without xdist installed.
- [ ] **COORD-02**: FileLock-guarded singleton initialization — `filelock.FileLock` ensures only gw0 starts Docker infra; gw1+ wait for state file.
- [ ] **COORD-03**: Shared JSON state file — gw0 writes endpoint URLs + build flags to temp-path state file; gw1+ reads with configurable timeout (default 120s).
- [ ] **COORD-04**: Fail-fast skip cascade — gw0 writes `"error"` key on failure; gw1+ detects and calls `pytest.skip()` instead of hanging indefinitely.
- [ ] **COORD-05**: Non-xdist backward compatibility — `worker_id == "master"` path preserves all existing fixture behavior unchanged.

### Infrastructure (INFRA)

- [ ] **INFRA-01**: `docker_network` conditional — only gw0 creates the bridge network; network name stored in shared state for gw1+.
- [ ] **INFRA-02**: `localstack_endpoint` passthrough — gw0 returns endpoint from container URL, gw1+ returns from shared state. All downstream boto3 client fixtures work automatically.
- [ ] **INFRA-03**: `sam_build` single execution — gw0 runs `sam build` with `build_complete` flag in state; gw1+ polls for completion (timeout 300s).
- [ ] **INFRA-04**: Function-scoped AWS resources preserved — `s3_bucket`, `dynamodb_table`, `sqs_queue`, `sns_topic` remain per-worker isolated via UUID-named resources in shared LocalStack.
- [ ] **INFRA-05**: gw0-only teardown — only gw0 stops Docker containers and removes network; gw1+ yields without any teardown calls.

### Services (SERV)

- [ ] **SERV-01**: `sam_api` conditional — gw0 starts SAM start-api container with endpoint in shared state; gw1+ resolves URL from state.
- [ ] **SERV-02**: `sam_lambda_endpoint` conditional — gw0 starts SAM start-lambda container with endpoint in shared state; gw1+ resolves URL from state.
- [ ] **SERV-03**: `lambda_client` works on all workers — gw1+ resolves `lambda_client` to shared SAM Lambda endpoint without starting its own SAM container.
- [ ] **SERV-04**: Warm container coordination — gw0 pre-warms containers via existing mechanism; gw1+ benefits from already-warm containers automatically.

### Mock (MOCK)

- [ ] **MOCK-01**: `make_lambda_mock` creates shared spy bucket — gw0 creates spy S3 bucket, gw1+ receives bucket name via shared state.
- [ ] **MOCK-02**: `sam_env_vars` propagation — gw0 serializes mock-wired env vars to shared state; gw1+ replays mutations to its `sam_env_vars` dict before `sam_build`.
- [ ] **MOCK-03**: Spy bucket operations safe across workers — unique key naming (timestamps, UUIDs) prevents inter-worker write collisions.

### Testing & Documentation (TEST)

- [ ] **TEST-01**: Dedicated xdist integration test suite — separate pytest session with `-n 2` using isolated fixtures (no conflict with root conftest.py).
- [ ] **TEST-02**: Crash recovery test — force gw0 Docker startup failure, assert gw1+ exits with clean `pytest.skip()` not hang or cryptic error.
- [ ] **TEST-03**: Resource fixture parallelism test — `-n 4` with S3/DynamoDB/SQS/SNS reads/writes from multiple workers simultaneously.
- [ ] **TEST-04**: User documentation — xdist usage guide in README with configuration, `-n` flag usage, supported `--dist` modes, CI recommendations, and known limitations.
- [ ] **TEST-05**: Performance benchmark — measure suite execution time with plain `pytest` (baseline, no xdist) vs `pytest -n 2/4/auto` (xdist). Report speedup factor. Track across development iterations to catch regressions.

## Deferred

Explicitly acknowledged but not in v2.3.0 scope:

| Item | Reason |
|------|--------|
| `--dist=each` and `--dist=no` support | Each worker would duplicate Docker infra — defeats parallel purpose |
| Per-worker LocalStack/SAM instances | Resource explosion; shared infra is the whole point |
| Custom TCP coordination server | Over-engineered; filesystem-sharing via FileLock is sufficient |
| xdist support for samstack's own test suite | Downstream-only scope; samstack tests are sequential by design |
| Worker pool LocalStack sharding (16+ workers) | Out of scope; current architecture handles 0-16 workers |
| Configurable timeout env var (`PYTEST_SAMSTACK_XDIST_TIMEOUT`) | Deferred until integration testing validates default 120s value |

## Out of Scope

Explicitly excluded from samstack entirely:

| Feature | Reason |
|---------|--------|
| Rewriting pytest-xdist fixture scoping (GH #271) | pytest-xdist design decision; samstack works within it |
| xdist_group marks on samstack fixtures | Users who need test grouping add `@pytest.mark.xdist_group` themselves |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| COORD-01 | Phase 8 | Pending |
| COORD-02 | Phase 8 | Pending |
| COORD-03 | Phase 8 | Pending |
| COORD-04 | Phase 8 | Pending |
| COORD-05 | Phase 8 | Pending |
| INFRA-01 | Phase 9 | Pending |
| INFRA-02 | Phase 9 | Pending |
| INFRA-03 | Phase 9 | Pending |
| INFRA-04 | Phase 9 | Pending |
| INFRA-05 | Phase 9 | Pending |
| SERV-01 | Phase 10 | Pending |
| SERV-02 | Phase 10 | Pending |
| SERV-03 | Phase 10 | Pending |
| SERV-04 | Phase 10 | Pending |
| MOCK-01 | Phase 11 | Pending |
| MOCK-02 | Phase 11 | Pending |
| MOCK-03 | Phase 11 | Pending |
| TEST-01 | Phase 12 | Pending |
| TEST-02 | Phase 12 | Pending |
| TEST-03 | Phase 12 | Pending |
| TEST-04 | Phase 12 | Pending |
| TEST-05 | Phase 12 | Pending |

**Coverage:**
- v2.3.0 requirements: 22 total
- Mapped to phases: 22 ✓
- Unmapped: 0

---
*Requirements defined: 2026-04-30*
*Last updated: 2026-04-30 after roadmap creation*

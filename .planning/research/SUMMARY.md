# Project Research Summary

**Project:** samstack v2.3.0 — pytest-xdist parallel test support
**Domain:** pytest plugin — Docker-based test fixture parallelization
**Researched:** 2026-04-30
**Confidence:** HIGH

## Executive Summary

samstack is a pytest plugin that runs AWS SAM CLI and LocalStack entirely inside Docker, providing session-scoped fixtures for local Lambda testing. The v2.3.0 milestone adds `pytest-xdist` support, enabling parallel test execution across multiple worker processes while sharing a single set of Docker infrastructure (LocalStack, SAM API/lambda containers, Docker network). This eliminates the N× resource explosion that would occur if each xdist worker spawned its own containers.

The recommended approach follows the pytest-xdist canonical pattern: `filelock.FileLock`-guarded singleton initialization, where worker 0 (gw0) owns all Docker container lifecycle and writes serialized endpoint URLs to a JSON state file on the shared filesystem. Workers 1+ read from this state file, yielding without any container teardown. This is battle-tested by pytest-django and explicitly documented in pytest-xdist's how-to guide. The only new dependency is `filelock` (pure Python, no system dependencies).

The key risks are all race-condition based: gw0 crashing leaves gw1+ hanging (mitigated by timeout + error-key in state file), `sam_env_vars` mutations from `make_lambda_mock` not propagating to gw1+ (mitigated by serializing mock wiring to shared state), and gw1+ trying to read `sam build` output before gw0 finishes (mitigated by a `build_complete` flag). All are solvable with the same FileLock + state file pattern, and all have clear integration test strategies.

## Key Findings

### Recommended Stack

The stack change is minimal — only one new dependency. pytest-xdist is an optional peer (downstream projects install it themselves). The coordination mechanism is pure Python with no external services.

**Core technologies:**
- **pytest-xdist (≥3.0)**: Provides `worker_id` fixture (`"master"`, `"gw0"`, `"gw1"`, etc.) and `PYTEST_XDIST_WORKER` env var. Optional peer dependency — samstack works without it installed.
- **filelock (≥3.13)**: Cross-process file locking for singleton initialization. Pure Python, zero system deps. The pytest-xdist official documentation uses it in the canonical session-fixture-once example. Consumers get it transitively.
- **Existing stack unchanged**: testcontainers-python, Docker SDK, LocalStack container image, SAM CLI container image. Only gw0 runs Docker lifecycle; gw1+ skips it entirely.

**Alternatives considered and rejected:** `fasteners` (solid but less ecosystem alignment), TCP coordination server (over-engineered for filesystem-sharing workers), `multiprocessing.Manager` (CPython-internal coupling), environment variables (can't convey dynamic Docker-mapped ports).

### Expected Features

**Must have (table stakes):**
- Single LocalStack shared across all workers — the entire point of xdist integration; avoids N× resource explosion and port conflicts
- Single SAM start-api/start-lambda per session — SAM containers are heavy; Lambda sub-containers multiply the cost
- Single `sam build` execution — build output is filesystem-shared; running N times is pure waste
- Per-worker function-scoped AWS resources preserved — `s3_bucket`, `dynamodb_table` etc. remain per-test-isolated via uniquely-named resources in shared LocalStack
- Non-xdist backward compatibility — `pytest` without `-n` must work exactly as before; `worker_id == "master"` path is the existing code path
- Auto-detection — no conftest.py wiring needed; install xdist, add `-n 4`, it works

**Should have (differentiators):**
- Fail-fast with skip cascade on gw0 infra failure — clear `pytest.skip("Worker 0 infrastructure failed: ...")` instead of cryptic connection errors
- Shared mock spy buckets — `make_lambda_mock` creates a spy S3 bucket visible to all workers; Lambda A writes spy events, any worker's test reads `mock.calls`
- Configurable startup timeout via `PYTEST_SAMSTACK_XDIST_TIMEOUT` — accommodates slow CI and first-run Docker pulls
- Warm container coordination — gw0 warms containers once; gw1+ benefit from already-warm containers automatically

**Defer (v2+):**
- Configurable timeout env var — default 120s works for most; add override later
- Worker pool LocalStack sharding for 16+ workers — out of scope; current architecture handles 0-16 workers well

**Anti-features (explicitly NOT built):**
- Per-worker LocalStack/SAM instances — defeats the purpose; resource explosion
- Custom TCP coordination server — over-engineered; filesystem sharing is sufficient
- Teardown on gw1+ workers — would cause Docker API error races
- `xdist_group` marks on samstack fixtures — would serialize all tests; users who need grouping add it themselves

### Architecture Approach

The architecture follows four patterns from pytest-xdist's documented approach. A new `_xdist.py` coordination module centralizes all xdist logic: FileLock helpers, state read/write (`_xdist_state_path`, `_read_state`, `_write_state`), worker ID detection, and the timeout/retry mechanism. Existing fixture modules gain conditional branches based on `worker_id` — gw0 creates and manages Docker lifecycle, gw1+ reads from shared state and yields without teardown.

The critical insight enabling minimal code changes: `localstack_endpoint` already returns a plain string URL. By making it read from shared state on gw1+ (instead of from a container object), every downstream boto3 client fixture (`s3_client`, `dynamodb_client`, etc.) works automatically — they only depend on the endpoint URL, not the container object.

**Major components:**
1. **`_xdist.py` (NEW)**: Coordination primitives — FileLock acquisition, shared state read/write via JSON file in `tmp_path_factory.getbasetemp().parent`, worker ID detection, timeout/retry with error-key skip cascade, SAM build completion flag
2. **`docker_network` + `localstack_endpoint` (MODIFIED)**: Network creation only on gw0; gw1+ reads network name from shared state. `localstack_endpoint` reads from container on gw0, from shared state on gw1+. This single change unblocks all resource fixtures automatically.
3. **`sam_build` + `sam_api` + `sam_lambda_endpoint` (MODIFIED)**: Build runs only on gw0 with a `build_complete` flag in shared state; gw1+ polls for it. SAM container lifecycle only on gw0; gw1+ reads endpoint URLs from shared state.
4. **`make_lambda_mock` (MODIFIED)**: Spy bucket created by gw0, shared bucket name via state. `sam_env_vars` mutations (mock wiring) serialized to state and replayed on gw1+ before `sam_build` runs.
5. **`resources.py` (LARGELY UNCHANGED)**: Client fixtures already accept `localstack_endpoint: str` — they work naturally when the endpoint comes from shared state. Function-scoped resource fixtures remain per-worker.

**Shared state file format:**
```json
{
  "network_name": "samstack-a1b2c3d4",
  "localstack_endpoint": "http://127.0.0.1:4566",
  "sam_api_endpoint": "http://127.0.0.1:3000",
  "sam_lambda_endpoint": "http://127.0.0.1:3001",
  "build_complete": true,
  "mock_env_vars": {"MOCK_SPY_BUCKET": "...", "MOCK_FUNCTION_NAME": "..."},
  "worker0_pid": 12345,
  "error": null
}
```

Written incrementally by gw0 as each Docker resource starts. gw1+ workers wait for specific keys they need (not the whole file).

### Critical Pitfalls

1. **gw1+ Docker teardown races**: Every worker gets its own session-fixture copy. If gw1+ runs teardown, workers race to stop shared containers — one succeeds, others get Docker API errors. **Prevent by**: Only gw0 runs teardown. gw1+ fixtures yield without cleanup. Integration test must assert clean exit with `-n 2`.

2. **gw0 crash leaves gw1+ hanging**: If gw0 crashes before writing state file, gw1+ `_read_state()` polls forever. **Prevent by**: Configurable timeout (default 120s) on `_read_state()`. gw0 writes `"error"` key on failure so gw1+ calls `pytest.skip()` instead of timing out. Integration test: force gw0 failure, assert gw1 exits with clear skip.

3. **`sam_env_vars` mutations not propagated**: `make_lambda_mock` mutates `sam_env_vars` to inject mock wiring. Each worker has its own dict copy. If gw1+ doesn't apply the same mutations, Lambda code in SAM won't receive mock config. **Prevent by**: gw0 serializes mock-wired env vars to shared state; gw1+ applies same mutations to its `sam_env_vars` dict before `sam_build` runs. Integration test with multi_lambda fixture under `-n 2`.

4. **SAM build race condition**: gw1+ may read `.aws-sam/` build output before gw0 finishes building. **Prevent by**: gw0 writes `"build_complete": true` to state after build finishes; gw1+ polls for this flag with timeout (300s for slow builds).

5. **`localstack_container` object unavailable on gw1+**: Fixtures that directly use the container object (not just its URL) fail on gw1+. **Prevent by**: All internal consumers use `localstack_endpoint` (string), not `localstack_container` (object). Document that downstream projects should depend only on endpoint URL fixtures in xdist mode.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Core Xdist Coordination (`_xdist.py`)
**Rationale:** Every other xdist feature depends on the coordination primitives. This phase establishes the FileLock pattern, shared state read/write, worker ID detection, and timeout/retry with error-key cascade. It has no Docker dependencies, so it can be unit-tested in isolation. Getting this right first eliminates coordination bugs from later phases.
**Delivers:** `samstack/fixtures/_xdist.py` with `_xdist_state_path()`, `_read_state()`, `_write_state()`, `is_xdist_worker()`, `get_worker_role()`, `worker_id` fixture re-export. Unit tests for all coordination primitives (no Docker needed).
**Addresses:** Table stakes: auto-detection of xdist mode. Differentiators: fail-fast skip cascade foundation, timeout infrastructure.
**Avoids:** Pitfall 2 (gw0 crash hang) — timeout + error-key in state file from day one.

### Phase 2: Docker Infra Xdist-Awareness (Network + LocalStack + Build)
**Rationale:** Making `docker_network`, `localstack_endpoint`, and `sam_build` xdist-aware unblocks ALL resource fixtures automatically (S3, DynamoDB, SQS, SNS) because they only depend on the endpoint URL string. This is the highest-leverage change — modifying three fixtures enables parallel testing for every resource type. `sam_build` coordination is included here because build output is a prerequisite for all SAM services.
**Delivers:** `docker_network` conditional create, `localstack_endpoint` passthrough from shared state, `sam_build` with `build_complete` flag. All `*_client` fixtures work on gw1+. Integration test: `pytest -n 2` with S3/DynamoDB/SQS/SNS resource tests.
**Addresses:** Table stakes: single LocalStack, single build execution, per-worker function-scoped resources. Differentiators: configurable timeout infrastructure (state file timeout mechanism ready for env var).
**Avoids:** Pitfall 1 (gw1+ teardown races) — conditional teardown pattern. Pitfall 4 (build race) — `build_complete` flag. Pitfall 5 (container object unavailable) — endpoint-only pattern for gw1+.

### Phase 3: SAM API + Lambda Xdist-Awareness
**Rationale:** SAM containers are the heaviest Docker resources. This phase extends the Phase 2 pattern to `sam_api` and `sam_lambda_endpoint`, enabling parallel HTTP and boto3 Lambda invocation tests. Depends on Phase 2 because SAM containers join the Docker network created by gw0 and need `sam_build` to have completed.
**Delivers:** `sam_api` and `sam_lambda_endpoint` conditional on gw0. Endpoint URLs in shared state. `lambda_client` works on all workers. Integration test: `pytest -n 2` with hello_world and warm_check fixtures.
**Addresses:** Table stakes: single SAM containers per session.
**Avoids:** Pitfall 1 (gw1+ SAM teardown). Pitfall 3 (env var propagation — mock wiring not yet in scope).

### Phase 4: Mock Coordination (Shared Spy Buckets)
**Rationale:** `make_lambda_mock` is the riskiest feature — it requires `sam_env_vars` propagation across workers, which is Pitfall 3. Delaying it until Phase 4 means core infra is stable and tested before adding the complex state serialization. This phase also delivers the shared spy bucket differentiator. Depends on Phase 3 (SAM Lambda endpoint must work for workers to invoke mocked Lambdas).
**Delivers:** `make_lambda_mock` creates spy bucket on gw0, shares bucket name via state. `sam_env_vars` mutations serialized to state and replayed on gw1+. `LambdaMock.calls` readable from any worker. Integration test: `pytest -n 2` with multi_lambda fixture.
**Addresses:** Differentiators: shared mock spy buckets. Warm container coordination (documentation only — already works).
**Avoids:** Pitfall 3 (sam_env_vars not propagated) — explicit serialization and replay pattern.

### Phase 5: Integration Testing, CI, Docs
**Rationale:** xdist testing has unique challenges — samstack's own test suite needs to run under xdist without circular dependency issues (xdist tests must use dedicated test fixtures that don't conflict with the root `conftest.py`). CI configuration and user-facing documentation are table stakes for a plugin feature. This phase validates everything end-to-end.
**Delivers:** Dedicated xdist integration test suite (separate pytest session from existing tests). CI job matrix for `-n auto`, `-n 2`, `-n 4`. xdist usage guide in README. Platform matrix: Linux + macOS + Windows (if CI supports Docker). Smoke test for crash recovery (gw0 kill → gw1 clean skip).
**Addresses:** Table stakes: backward compatibility (Phase 1-4 verified with and without `-n`). Differentiators: configurable timeout env var (add `PYTEST_SAMSTACK_XDIST_TIMEOUT` as final feature).
**Avoids:** All pitfalls — end-to-end validation catches coordination bugs.

### Phase Ordering Rationale

- **Coordination first**: Every fixture change depends on `_xdist.py`. Getting FileLock + state file semantics right in isolation prevents subtle bugs from leaking into Docker fixture code. Unit-testable without Docker.
- **Infrastructure before services**: Network → LocalStack → SAM. Each layer depends on the previous. LocalStack needs the network; SAM needs both the network and LocalStack (for the Lambda-to-LocalStack path). `sam_build` must complete before either SAM service starts.
- **Resources unlock automatically**: Making `localstack_endpoint` read from shared state makes all boto3 client fixtures work on gw1+ with zero additional changes. This is the highest-leverage architecture decision.
- **Mock last among features**: Mock coordination is the highest-risk feature (Pitfall 3). Deferring it until Phase 4 means three phases of stable infra before tackling env var serialization.
- **Integration validation gates**: Phase 5 validates all previous phases together. Catching coordination bugs (like Pitfall 2's timeout, Pitfall 4's build race) requires multi-worker execution that individual phases can't fully test.

### Research Flags

**Phases likely needing deeper research during planning:**
- **Phase 4 (Mock Coordination):** `sam_env_vars` serialization and replay across workers is the most complex coordination pattern. The SAM `--env-vars` JSON format has a documented gotcha (undeclared `Environment.Variables` keys are silently dropped). Needs careful design of what gets serialized and how gw1+ replays mutations.
- **Phase 5 (Integration Testing):** Testing xdist under xdist requires careful fixture isolation. The existing multi_lambda and warm_check test suites already run in separate pytest sessions due to `samstack_settings` conflicts — xdist integration tests must follow the same pattern but with `-n 2` distribution. The `--dist loadfile` strategy is likely needed to keep related tests co-located.
- **Phase 5 (CI/Platform):** Windows support for `filelock` is theoretically fine (pure Python), but Docker-in-Docker on Windows CI runners has known issues. May need to document Windows as "best effort" or require Docker Desktop.

**Phases with well-documented patterns (skip research-phase):**
- **Phase 1 (Core Coordination):** The FileLock + JSON state file pattern is directly from pytest-xdist official documentation with working code examples. No novel research needed.
- **Phase 2 (Docker Infra):** The endpoint passthrough pattern is simple — it's the same `localstack_endpoint` string, just from a different source. The conditional fixture pattern is straightforward branching.
- **Phase 3 (SAM Services):** Same pattern as Phase 2 applied to different fixtures. No novel coordination challenges beyond what Phase 2 solves.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | `filelock` is the only new dependency; recommended directly by pytest-xdist official docs; pure Python, cross-platform, well-maintained. Alternative evaluation is thorough. |
| Features | HIGH | Table stakes derived from pytest-xdist user expectations and samstack's existing fixture architecture. Differentiators are realistic extensions of existing capabilities. Anti-features are well-reasoned. |
| Architecture | HIGH | All four patterns are from pytest-xdist's documented approach. The endpoint passthrough insight (making resource fixtures work automatically) is particularly high-confidence because it leverages existing architecture. Component boundaries and data flows are mapped in detail. |
| Pitfalls | HIGH | Pitfalls identified from pytest-xdist docs, pytest-django real-world integration, and samstack's own CLAUDE.md fixture chain. Each pitfall has a specific prevention strategy and detection test. Phase-specific warnings cross-reference specific phases. |

**Overall confidence:** HIGH

All research sources are HIGH confidence: pytest-xdist official documentation, pytest-django source code (battle-tested real-world example), Context7 API documentation, and samstack's own architecture docs (CLAUDE.md, PROJECT.md). No MEDIUM or LOW confidence sources — every architectural decision and pitfall is grounded in documented best practices and existing code.

### Gaps to Address

- **`filelock` version pinning vs. floor**: Research recommends ≥3.13 but doesn't test which minimum version is actually needed. During Phase 1 implementation, pin to the lowest version that supports the required API (context manager + timeout).
- **Windows CI Docker availability**: Research acknowledges Docker-in-Docker on Windows is problematic but doesn't provide a solution. During Phase 5, either configure Windows CI with Docker Desktop or document Windows as requiring Docker Desktop with xdist caveats.
- **`--dist` strategy recommendation for users**: Research references `loadfile`, `loadscope`, `each` distribution strategies but doesn't recommend one for samstack users. During Phase 5 docs, test each strategy and document which works best for Lambda test suites (likely `loadscope` to keep related mock tests together).
- **SAM container port collision with concurrent sessions**: Pitfall 7 notes port 3000/3001 conflicts between hosts but not between multiple pytest sessions. If two CI jobs run on the same host simultaneously, port 3000 conflicts. This is pre-existing (not xdist-specific) but worth documenting.
- **Worker count upper bound**: Architecture research estimates 0-4 workers as typical, 5-16 as supported with no changes, 16+ as potential bottleneck. No empirical LocalStack concurrency testing was done. During Phase 5, run a stress test with `-n 16` against LocalStack to validate throughput assumptions.

## Sources

### Primary (HIGH confidence)
- [pytest-xdist How-to: Making session-scoped fixtures execute only once](https://pytest-xdist.readthedocs.io/en/latest/how-to.html#making-session-scoped-fixtures-execute-only-once) — FileLock pattern, race condition awareness, worker ID semantics
- [pytest-xdist Identifying workers](https://pytest-xdist.readthedocs.io/en/latest/how-to.html#identifying-the-worker-process-during-a-test) — `worker_id` fixture, `PYTEST_XDIST_WORKER` env var, process title
- [filelock PyPI](https://pypi.org/project/filelock/) — API surface, cross-platform support, timeout feature
- [Context7: pytest-xdist API](https://context7.com/pytest-dev/pytest-xdist/llms.txt) — `is_xdist_worker()`, `get_xdist_worker_id()`, `workerinput`
- [pytest-django fixtures.py](https://github.com/pytest-dev/pytest-django/blob/main/pytest_django/fixtures.py) — Real-world xdist database suffixing pattern using `workerinput["workerid"]`
- [samstack CLAUDE.md](https://github.com/ivan-shcherbenko/samstack/CLAUDE.md) — Existing fixture chain, Ryuk integration, SAM container lifecycle, architectural gotchas
- [samstack PROJECT.md](https://github.com/ivan-shcherbenko/samstack/.planning/PROJECT.md) — Active requirements, out-of-scope decisions for v2.3.0

### Secondary (MEDIUM confidence)
- [pytest-xdist Distribution docs](https://pytest-xdist.readthedocs.io/en/latest/distribution.html) — `--dist loadscope`, `xdist_group` mark, `pytest_xdist_auto_num_workers` hook (confirmed anti-feature decisions)

### Tertiary (LOW confidence)
- None — all findings are backed by official documentation, source code, or existing project architecture.

---
*Research completed: 2026-04-30*
*Ready for roadmap: yes*

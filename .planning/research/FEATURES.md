# Feature Landscape: pytest-xdist Integration

**Domain:** pytest plugin — Docker-based test fixture parallelization
**Researched:** 2026-04-30

## Table Stakes

Features users expect. Missing = xdist integration feels incomplete or broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Single LocalStack shared across all workers | Without this, N workers = N LocalStacks = resource explosion + port conflicts. This is the whole point. | Medium | gw0 creates; gw1+ connect via shared endpoint URL |
| Single SAM start-api/start-lambda per session | Same rationale as LocalStack — SAM containers are heavy, and Lambda sub-containers multiply the cost | Medium | gw0 owns SAM container lifecycle; gw1+ get endpoint URL |
| Single `sam build` execution | Build output is filesystem-shared. Running N times is pure waste. | Low | gw0 runs build; gw1+ skip. Trivial conditional. |
| Per-worker function-scoped AWS resources preserved | Users expect `s3_bucket`, `dynamodb_table` etc. to be isolated per test (and per worker). Must still work. | Low | Already works — each worker creates uniquely-named resources in shared LocalStack |
| Non-xdist backward compatibility | `pytest` (without `-n`) must work exactly as before. No regressions. | Low | `worker_id == "master"` path is the existing code path |
| Auto-detection of xdist mode | Users shouldn't need conftest.py wiring just to use xdist. Install xdist, add `-n 4`, it works. | Low | `worker_id` fixture auto-detects; no user config needed |

## Differentiators

Features that set samstack apart from raw xdist + Docker setups.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Fail-fast with skip cascade on gw0 infra failure | If worker 0 can't start Docker, other workers skip cleanly with "Worker 0 infrastructure failed: ..." instead of cryptic connection errors | Medium | `_write_state(tmpdir, "error", msg)` on gw0 failure; gw1+ reads and calls `pytest.skip()` |
| Shared mock spy buckets | `make_lambda_mock` creates a spy S3 bucket that ALL workers can read. Lambda A (running in SAM) writes spy events, and any worker's test can inspect `mock.calls`. | Medium | gw0 creates the bucket; gw1+ reuse same bucket name via shared state |
| Configurable startup timeout | Users in slow environments (CI, first Docker pull) can set `PYTEST_SAMSTACK_XDIST_TIMEOUT` to avoid false timeouts | Low | Environment variable read in `_read_state()` |
| Warm container coordination | `warm_functions` pre-warming runs once on gw0. gw1+ benefit from already-warm containers. | Low | Warm logic already in gw0's `sam_lambda_endpoint`/`sam_api`. gw1+ don't need to re-warm. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Per-worker LocalStack instances | Resource explosion, port conflicts, no shared spy buckets. Defeats the purpose of xdist integration. | Single LocalStack on gw0. If users need isolated LocalStacks, they should use separate pytest sessions. |
| Per-worker SAM containers | Same as above — multiple SAM instances fight over ports and Lambda container lifecycle. | Single SAM per session. SAM can handle concurrent Lambda invocations from multiple workers. |
| `pytest_xdist_auto_num_workers` hook in samstack | This hook belongs to the downstream project, not samstack. samstack should not dictate worker count. | Users implement this in their own conftest.py if they want custom worker counts. |
| Custom TCP coordination server | Over-engineered. Adds port negotiation, connection handling, serialization. Workers share a filesystem — use it. | FileLock + JSON state file in tmpdir. |
| Teardown on gw1+ workers | Workers race to stop/remove shared Docker containers. Error noise, potential data corruption. | Only gw0 runs teardown. gw1+ fixtures yield without cleanup. |
| `xdist_group` marks on samstack fixtures | Forces all tests using samstack into a single worker. Defeats parallelization. | Users who need this can add `@pytest.mark.xdist_group("samstack")` in their own conftest. |

## Feature Dependencies

```
filelock dependency
    ↓
_xdist.py (coordination primitives: _read_state, _write_state, _xdist_state_path)
    ↓
┌───────────────────────┬──────────────────────┬──────────────────────┐
│ docker_network        │ localstack_container │ sam_build            │
│ (conditional create)  │ (conditional create) │ (conditional exec)   │
└───────┬───────────────┴──────────┬───────────┴──────────┬───────────┘
        │                          │                      │
        ▼                          ▼                      ▼
localstack_endpoint           sam_api              sam_lambda_endpoint
(conditional URL source)   (conditional create)    (conditional create)
        │                          │                      │
        ▼                          ▼                      ▼
   s3_client,                warm_api_routes          lambda_client
   dynamodb_client,                                   (all workers)
   sqs_client, sns_client
   (all workers)

        └──────────────────────┬──────────────────────┘
                               │
                               ▼
                    make_lambda_mock
                    (shared spy bucket)
```

## MVP Recommendation

Prioritize:

1. **`_xdist.py` coordination module** — FileLock, shared state read/write, worker ID detection, timeout/retry. Every other feature depends on this.
2. **`docker_network` + `localstack_endpoint` xdist-awareness** — This unblocks ALL resource fixtures (S3, DynamoDB, SQS, SNS) automatically since they only depend on endpoint URL strings.
3. **`sam_build` + `sam_api` + `sam_lambda_endpoint` xdist-awareness** — This enables parallel Lambda testing.
4. **One differentiator: fail-fast skip cascade** — High UX value, relatively simple to implement once state file error-key pattern is in place.

Defer:
- **`make_lambda_mock` shared spy buckets**: Can be added after core Docker infra works. Downstream tests using mocks can run single-worker until this is done.
- **Configurable timeout**: Nice-to-have. Default 120s works for most environments. Add env var override later.
- **Warm container coordination**: Already works correctly — gw0 warms containers, gw1+ benefit from it. No explicit code needed, but document it.

## Sources

- [pytest-xdist documentation](https://pytest-xdist.readthedocs.io/en/latest/) — HIGH confidence: feature expectations from xdist perspective
- [pytest-django xdist integration](https://github.com/pytest-dev/pytest-django) — HIGH confidence: real-world feature set for database fixtures under xdist
- [samstack v2.3.0 PROJECT.md requirements](https://github.com/ivan-shcherbenko/samstack/.planning/PROJECT.md) — HIGH confidence: validated and active requirements

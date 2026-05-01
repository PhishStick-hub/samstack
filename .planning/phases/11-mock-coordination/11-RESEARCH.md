# Phase 11: Mock Coordination — Research

**Researched:** 2026-05-01
**Status:** Complete

## Research Summary

This phase is entirely pattern-application work. The gw0-create/gw1+-wait split pattern is already established across all infrastructure fixtures (Phases 8-10). `make_lambda_mock` is the last fixture that needs xdist-awareness. No new libraries, APIs, or architectural decisions are required.

## Pattern Reference: Established xdist Fixture Split

All Phase 8-10 fixtures follow an identical pattern. The `sam_api` fixture (Phase 10) is the most recent and cleanest example:

```python
# Pattern (from sam_api.py):
worker_id = get_worker_id()

# gw1+ path: wait, yield, return (no Docker)
if not is_controller(worker_id):
    endpoint = wait_for_state_key("sam_api_endpoint", timeout=120)
    yield endpoint
    return

# gw0/master path: create, write state, yield, teardown
try:
    with _run_sam_service(...) as endpoint:
        if worker_id == "gw0":
            write_state_file("sam_api_endpoint", endpoint)
        yield endpoint
except Exception as exc:
    if worker_id == "gw0":
        write_state_file("error", f"...")
    raise
```

## Required Changes: `make_lambda_mock`

The fixture lives in `src/samstack/mock/fixture.py:78-131`. The inner `_make` function (line 112-126) is where the xdist split must be applied.

### Current code (non-xdist):

```python
def _make(function_name, *, alias, bucket=None):
    spy_bucket = bucket if bucket is not None else make_s3_bucket(f"mock-{alias}")
    sam_env_vars[function_name] = {
        "MOCK_SPY_BUCKET": spy_bucket.name,
        "MOCK_FUNCTION_NAME": alias,
        "AWS_ENDPOINT_URL_S3": "http://localstack:4566",
    }
    mock = LambdaMock(name=alias, bucket=spy_bucket)
    created.append(mock)
    return mock
```

### Required xdist-aware code:

**gw0 path:**
1. Call `make_s3_bucket(f"mock-{alias}")` to create the shared spy bucket
2. Write bucket name to shared state as `mock_spy_bucket_{alias}` (D-02)
3. Mutate `sam_env_vars[function_name]` with mock env vars (needed for `sam_build` → `env_vars.json`)
4. Construct `LambdaMock(name=alias, bucket=spy_bucket)` and return it
5. On teardown: the bucket is cleaned up by `make_s3_bucket` (D-07)

**gw1+ path:**
1. Call `wait_for_state_key(f"mock_spy_bucket_{alias}", timeout=120)` to get shared bucket name (D-01)
2. Construct `S3Bucket(name=shared_bucket_name, client=s3_client)` — uses `s3_client` (already pointing at shared LocalStack via xdist-aware `localstack_endpoint`)
3. Does NOT call `make_s3_bucket` (D-03)
4. Mutate `sam_env_vars[function_name]` with mock env vars using shared bucket name (D-05)
5. Construct `LambdaMock(name=alias, bucket=shared_s3_bucket)` and return it
6. No teardown — yield and return (D-07)

**Error handling:**
- If gw0 fails, `write_state_file("error", ...)` — existing fail-fast pattern; gw1+ `wait_for_state_key` will detect the error key and `pytest.fail()` (D-04)

### Dependency injection change

The fixture signature currently depends on `make_s3_bucket` and `sam_env_vars`. The xdist-aware version also needs:
- `s3_client` — gw1+ uses this to construct `S3Bucket` wrapping the shared bucket
- `s3_resource` — potentially useful for constructing bucket reference objects

These are already session-scoped and xdist-aware.

### State key naming

Per D-02: `mock_spy_bucket_{alias}` where `{alias}` is the user-controlled alias parameter. This avoids collisions between different mocks in the same test session.

### LambdaMock class — ZERO changes

`LambdaMock.__init__(self, name: str, bucket: S3Bucket)` already accepts any `S3Bucket` — it doesn't care whether the bucket was created via `make_s3_bucket` or constructed from a shared name. All operations (`calls`, `clear`, `next_response`, `response_queue`) work through `bucket.client` which on gw1+ points at the shared LocalStack.

### spy_handler — ZERO changes

`spy_handler` reads `MOCK_SPY_BUCKET` and `MOCK_FUNCTION_NAME` from env vars. Since `sam_env_vars` is mutated with the correct values on both gw0 and gw1+, and `sam_build` only runs on gw0 (writing `env_vars.json` once), all Lambda containers receive the correct env vars regardless of which worker triggers the invocation.

### sam_env_vars propagation

Per D-05/D-06:
- gw0 mutates `sam_env_vars` → `sam_build` writes `env_vars.json` → SAM containers receive mock env vars
- gw1+ mutates `sam_env_vars` for in-memory consistency (any test code reading `sam_env_vars` directly sees correct values)
- gw1+ does NOT need to re-write `env_vars.json` since `sam_build` on gw1+ is a no-op

### Concurrent write safety (MOCK-03)

`spy_handler._spy_key()` generates keys as `spy/{name}/{timestamp}-{uuid}.json` where the timestamp has microsecond precision and the UUID is random. Even with two workers triggering Lambda invocations simultaneously, key collisions are statistically impossible:
- Independent uuid4 calls from different Lambda containers
- Microsecond timestamps from different invocations

The `queue.json` (response queue) is read-modify-write by `_pop_response`, but this is NOT a concern for two reasons:
1. In practice, one test-worker controls response queueing; the Lambda just reads/pops
2. If concurrent modification occurs, S3's strong read-after-write consistency ensures the latest version is read

## No Research Debt

No external libraries, APIs, or patterns to investigate. The implementation is a direct application of the established pattern with domain-specific state keys and bucket construction.

## Files to Modify

| File | Change |
|------|--------|
| `src/samstack/mock/fixture.py` | Add xdist split to `_make` inner function; add `s3_client` dependency |
| `src/samstack/mock/__init__.py` | No changes expected (verify) |

## Files to Create

| File | Purpose |
|------|---------|
| `tests/unit/test_mock_xdist.py` | Unit tests for gw0/gw1+ split without Docker |

## Validation Architecture

### Nyquist Dimension Coverage

| Dimension | Strategy |
|-----------|----------|
| **Unit tests** | Test `_make` on gw0 creates bucket + writes state; test `_make` on gw1+ reads state + constructs S3Bucket; test error state propagation; test mock env vars set correctly on both workers |
| **Integration tests** | The existing `tests/multi_lambda/` suite already validates mock behavior. A new xdist-enabled integration test in `tests/multi_lambda/` with `-n 2` proves cross-worker spy bucket sharing |
| **Backward compat** | Non-xdist (master) path is unchanged in behavior — existing tests must pass |
| **Observability** | grep-verifiable state key writes and reads |

### Per-Requirement Coverage

| Requirement | Verification Strategy |
|-------------|----------------------|
| MOCK-01 | Unit test: gw0 writes `mock_spy_bucket_{alias}` to state, gw1+ reads it and constructs LambdaMock |
| MOCK-02 | Unit test: `sam_env_vars[function_name]` contains correct values on both workers |
| MOCK-03 | Integration test: `-n 2` with simultaneous spy writes from different workers, verify no key collisions |

## Reusable Assets

All primitives already exist in `samstack._xdist`:
- `is_controller(worker_id)` — detects gw0/master
- `write_state_file(key, value)` — writes shared state
- `wait_for_state_key(key, timeout)` — polls shared state with error detection
- `get_worker_id()` — returns worker identifier

All resource fixtures already exist and are xdist-aware:
- `s3_client` — session-scoped, points at shared LocalStack
- `s3_resource` — session-scoped, points at shared LocalStack
- `make_s3_bucket` — creates uniquely-named buckets (used on gw0 only)
- `sam_env_vars` — mutable dict, already consumed by `sam_build`

## Edge Cases to Handle

1. **Multiple mocks in same session:** Each mock gets its own state key (`mock_spy_bucket_{alias}`) and its own spy bucket. State keys won't collide.
2. **Pre-existing bucket passed via `bucket=` param:** If user passes a pre-existing bucket, skip all xdist logic — use the provided bucket directly. This matches D-01 spec ("bucket name to shared state" not needed when user provides bucket).
3. **Error on gw0 during bucket creation:** gw0 writes `"error"` key → gw1+ `wait_for_state_key` detects it → `pytest.fail()`
4. **gw1+ timeout waiting for state:** `wait_for_state_key` already handles this with `pytest.fail(f"Timed out after {timeout}s...")`

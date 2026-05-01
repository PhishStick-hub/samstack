# Phase 11: Mock Coordination - Context

**Gathered:** 2026-05-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Make `make_lambda_mock` work transparently across xdist workers. gw0 creates a single shared spy S3 bucket and writes its name to shared state; gw1+ reads the bucket name and constructs `LambdaMock` pointing at the same bucket. `sam_env_vars` is mutated on all workers for in-memory consistency. Only gw0 tears down the shared bucket at session end. `spy_handler` (Lambda-side code) requires zero changes — it writes to whatever bucket its env vars point to.

**Requirements:** MOCK-01, MOCK-02, MOCK-03

</domain>

<decisions>
## Implementation Decisions

### Spy bucket coordination
- **D-01:** gw0 creates the spy S3 bucket via `make_s3_bucket(f"mock-{alias}")` and writes the bucket name to shared state as `mock_spy_bucket_{alias}`. gw1+ reads the name via `wait_for_state_key("mock_spy_bucket_{alias}", timeout=120)` and constructs `LambdaMock` using the shared bucket (obtained via `s3_resource` / `s3_client`, not a new `make_s3_bucket` call).
- **D-02:** State key naming: `mock_spy_bucket_{alias}` where `{alias}` is the alias passed to `make_lambda_mock`. The alias is user-controlled and unique per mock function.
- **D-03:** gw1+ does NOT call `make_s3_bucket` for the spy bucket — it uses the shared bucket name from state directly. This avoids creating unused buckets on gw1+.
- **D-04:** If gw0 fails to create the bucket, it writes `"error"` key to shared state (existing fail-fast pattern). gw1+ `wait_for_state_key` detects the error and calls `pytest.fail()`.

### sam_env_vars propagation
- **D-05:** Both gw0 and gw1+ mutate `sam_env_vars[function_name]` with the correct `MOCK_SPY_BUCKET`, `MOCK_FUNCTION_NAME`, and `AWS_ENDPOINT_URL_S3`. On gw0, this feeds into `sam_build` → `env_vars.json` → SAM container. On gw1+, this is for in-memory consistency (any test/plugin code that reads `sam_env_vars` directly sees correct values).
- **D-06:** The actual `env_vars.json` file written by gw0's `sam_build` already contains the correct mock env vars. gw1+ does not need to re-write `env_vars.json` since `sam_build` on gw1+ is a no-op (waits for `build_complete` and returns). SAM containers were already started by gw0 with correct env vars.

### Teardown responsibility
- **D-07:** Only gw0 deletes the shared spy bucket on session teardown. gw1+ yields and returns with no teardown. Matches INFRA-05 and D-05 from Phase 10.
- **D-08:** `LambdaMock.clear()` (deletes S3 objects, not the bucket) is safe to call on any worker — it operates on S3 objects only. The bucket itself is only deleted by gw0.

### Claude's Discretion
- Exact code structure of the xdist split inside `make_lambda_mock`'s inner `_make` function
- Whether to add an `acquire_infra_lock()` call for bucket creation (it depends on `s3_client` → `localstack_endpoint`, which is already locked on gw0)
- Error message wording in `pytest.fail()` for gw1+ timeout
- Whether to expose the shared bucket name as a separate state key or bundle mock state into a single JSON key

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §MOCK-01–MOCK-03 — Phase 11 requirements (shared spy bucket, env-var propagation, safe concurrent writes)

### Phase 8-10 patterns (the established xdist approach)
- `src/samstack/_xdist.py` — `wait_for_state_key()`, `write_state_file()`, `get_worker_id()`, `is_controller()`, `acquire_infra_lock()`
- `src/samstack/fixtures/sam_api.py` — `sam_api` xdist pattern: gw0 creates + writes state key, gw1+ waits + yields (Phase 10 reference)
- `src/samstack/fixtures/localstack.py` — `localstack_container` xdist pattern: gw0 creates container + writes endpoint, gw1+ gets proxy (Phase 9 reference)
- `src/samstack/fixtures/sam_build.py` — `sam_build` xdist pattern: gw0 runs build + writes `build_complete`, gw1+ waits (Phase 9 reference)

### Source files to modify
- `src/samstack/mock/fixture.py` — `make_lambda_mock` fixture: add gw0/gw1+ split for shared spy bucket, env-var mutation on all workers
- `src/samstack/mock/__init__.py` — public exports (verify no changes needed, but read to confirm)

### Source files to read (no changes expected)
- `src/samstack/mock/handler.py` — `spy_handler`: Lambda-side code, writes to S3 using env vars, xdist-agnostic
- `src/samstack/mock/types.py` — `Call`, `CallList`: frozen dataclasses, no xdist concerns
- `src/samstack/fixtures/resources.py` — `s3_client`, `s3_resource`, `make_s3_bucket` fixtures
- `src/samstack/plugin.py` — fixture registration, `make_lambda_mock` export

### Test fixtures to understand
- `tests/multi_lambda/conftest.py` — how `make_lambda_mock` is used: autouse `_mock_b_session`, `sam_env_vars` mutation pattern
- `tests/multi_lambda/test_multi_lambda.py` — mock test patterns: `.clear()`, `.calls.one`, `.next_response()`, `.matching()`

### No external specs
No external specs — requirements fully captured in `.planning/REQUIREMENTS.md` and decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_xdist` module**: `wait_for_state_key()`, `write_state_file()`, `is_controller()`, `get_worker_id()` — used directly in `make_lambda_mock` for the gw0/gw1+ split
- **`make_s3_bucket`** (`resources.py:87`): Session-scoped factory — gw0 calls it to create the spy bucket with UUID suffix, gw1+ skips it and uses shared name
- **`s3_resource` / `s3_client`** (`resources.py`): Session-scoped boto3 clients — gw1+ uses these to construct `S3Bucket` wrapper pointed at the shared bucket
- **`LambdaMock`** (`mock/fixture.py:16`): Test-side handle — already takes `name: str, bucket: S3Bucket` constructor; gw1+ constructs it with shared bucket, no changes to LambdaMock class itself
- **`spy_handler`** (`mock/handler.py:147`): Lambda-side — writes to whatever `MOCK_SPY_BUCKET` env var points to; xdist-agnostic, zero changes needed
- **`sam_env_vars`** (`sam_build.py:33`): Mutable dict — `make_lambda_mock` already mutates it; gw1+ mutates with shared bucket name for in-memory consistency

### Established Patterns
- **gw0-create / gw1+-wait**: Phase 8-10 established this for every infrastructure fixture. Phase 11 applies it to mock spy buckets.
- **gw1+ no-teardown**: gw1+ paths yield and return without any Docker or resource lifecycle calls. Only gw0 tears down.
- **State file coordination**: gw0 writes keys to JSON state file; gw1+ polls with `wait_for_state_key()`. FileLock prevents concurrent state writes.
- **Fixture splitting pattern**: `if not is_controller(worker_id):` → wait + yield/return; `else:` → create + write state + yield → teardown.
- **sam_env_vars mutation**: `make_lambda_mock` already mutates `sam_env_vars[function_name]` in-place with `MOCK_SPY_BUCKET`, `MOCK_FUNCTION_NAME`, `AWS_ENDPOINT_URL_S3`. This pattern is preserved — both gw0 and gw1+ do it.

### Integration Points
- **`make_lambda_mock`** depends on `make_s3_bucket` (for bucket creation on gw0) and `sam_env_vars` (for env var injection on all workers)
- **`make_s3_bucket`** depends on `s3_client` → `localstack_endpoint` (already xdist-aware from Phase 9)
- **`sam_env_vars`** is consumed by `sam_build` (already xdist-aware from Phase 9)
- **`LambdaMock.calls`** reads from S3 spy objects — works on any worker as long as it points at the correct bucket
- **`LambdaMock.clear()`** deletes S3 objects from the spy bucket — safe on any worker, no coordination needed
- **Ordering constraint**: `make_lambda_mock` must resolve before `sam_build` so env vars are in `env_vars.json`. This ordering already exists in the fixture dependency graph.

</code_context>

<specifics>
## Specific Ideas

No specific references or "I want it like X" moments. The Phase 8-10 patterns are the reference implementation — make `make_lambda_mock` follow the same gw0-create/gw1+-wait split.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 11-mock-coordination*
*Context gathered: 2026-05-01*

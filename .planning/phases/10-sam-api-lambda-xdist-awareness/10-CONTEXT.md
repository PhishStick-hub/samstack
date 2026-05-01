# Phase 10: SAM API + Lambda Xdist-Awareness - Context

**Gathered:** 2026-05-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Make `sam_api` and `sam_lambda_endpoint` fixtures serve all xdist workers from single shared containers. gw0 starts the SAM service containers and writes endpoint URLs to shared state; gw1+ reads URLs and yields them without starting any containers. Pre-warmed Lambda containers (configured via `warm_functions`) are created once by gw0 and serve all workers. `lambda_client` works transparently on gw1+ by resolving to the shared SAM Lambda endpoint.

**Requirements:** SERV-01, SERV-02, SERV-03, SERV-04

</domain>

<decisions>
## Implementation Decisions

### SAM container xdist pattern
- **D-01:** Follow Phase 9 gw0-create / gw1+-wait pattern exactly. Each fixture (`sam_api`, `sam_lambda_endpoint`) splits on `is_controller(worker_id)`: gw0/master starts the container, gw1+ waits for state key.
- **D-02:** No proxy class needed — `sam_api` and `sam_lambda_endpoint` already yield `str` (endpoint URL). gw1+ simply does `wait_for_state_key("sam_api_endpoint")` / `wait_for_state_key("sam_lambda_endpoint")` and yields the URL string.
- **D-03:** State keys: `sam_api_endpoint` (string URL) and `sam_lambda_endpoint` (string URL). The existing `error` key serves as fail-fast signal.
- **D-04:** gw0 writes endpoint to shared state after container is started, network-attached, and ready (HTTP/port verified). gw1+ uses default 120s timeout for endpoint wait — consistent with `localstack_endpoint` timeout.
- **D-05:** gw1+ has no teardown responsibility — only gw0 stops the SAM containers and disconnects from network. gw1+ path yields and returns (matching Phase 9 `docker_network` and `localstack_container` gw1+ paths).

### Warm container coordination
- **D-06:** gw0 does all pre-warming (`_pre_warm_functions` for start-lambda, `_pre_warm_api_routes` for start-api) before writing endpoint to shared state. gw1+ benefits from warm containers automatically — just yields the URL.
- **D-07:** Pre-warm failure is a hard failure: raises `SamStartupError`, gw0 writes `"error"` key to shared state, all gw1+ workers receive `pytest.fail()`. No partial-warm or degraded mode. Consistent with existing non-xdist behavior.
- **D-08:** gw1+ trusts gw0 implicitly — no lightweight ping, health check, or verification before yielding the endpoint. Matches Phase 9 trust pattern where gw1+ reads `localstack_endpoint` and `build_complete` without verification.

### Startup ordering and integration
- **D-09:** Keep lazy/deferred startup — each SAM container fixture starts when its first dependent is requested. No forced ordering or orchestrating fixture. The existing fixture dependency graph (`sam_build` → `sam_api` / `sam_lambda_endpoint`) naturally handles ordering.
- **D-10:** `lambda_client` fixture works unchanged — it depends on `sam_lambda_endpoint`, which resolves correctly on all workers. No code changes to `lambda_client` itself.

### the agent's Discretion
- Exact structure of the gw0/gw1+ split inside `sam_api` and `sam_lambda_endpoint` fixtures
- Whether to extract shared SAM container xdist logic into a helper (analogous to `_LocalStackContainerProxy` but for string endpoints)
- Error message wording in pytest.fail() for gw1+ timeout
- Whether gw0 should use `acquire_infra_lock()` for SAM containers (they depend on `docker_network` which already acquires it)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §SERV-01–SERV-04 — Phase 10 requirements (sam_api, sam_lambda_endpoint, lambda_client, warm coordination)

### Phase 9 patterns (the established xdist approach)
- `src/samstack/fixtures/localstack.py` — `_LocalStackContainerProxy` pattern, gw0-create/gw1+-wait for `localstack_container` and `localstack_endpoint`
- `src/samstack/fixtures/sam_build.py` — `sam_build` xdist split: gw0 runs build + writes `build_complete`, gw1+ waits
- `src/samstack/_xdist.py` — `wait_for_state_key()`, `write_state_file()`, `get_worker_id()`, `is_controller()`, `acquire_infra_lock()`

### Source files to modify
- `src/samstack/fixtures/sam_api.py` — `sam_api` fixture: add gw0/gw1+ split, write/read `sam_api_endpoint` state key, skip pre-warm on gw1+
- `src/samstack/fixtures/sam_lambda.py` — `sam_lambda_endpoint` fixture: add gw0/gw1+ split, write/read `sam_lambda_endpoint` state key, skip pre-warm on gw1+
- `src/samstack/fixtures/_sam_container.py` — `_run_sam_service()` context manager (no changes expected, but read to understand container lifecycle)

### No external specs
No external specs — requirements fully captured in `.planning/REQUIREMENTS.md` and decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_run_sam_service()`** (`_sam_container.py:89`): Context manager handling full SAM container lifecycle — start, network attach, readiness wait, yield URL, disconnect, stop. Used unchanged by gw0 path.
- **`_xdist` module**: `wait_for_state_key()`, `write_state_file()`, `is_controller()`, `get_worker_id()` — used directly in both fixtures for the gw0/gw1+ split.
- **`build_sam_args()`** (`_sam_container.py:32`): Shared CLI arg builder for both start-api and start-lambda — no changes needed.

### Established Patterns
- **gw0-create / gw1+-wait**: Phase 9 established this in `localstack_container`, `sam_build`, and `docker_network`. Phase 10 applies it to SAM service containers.
- **gw1+ no-teardown**: gw1+ paths yield and return without any Docker lifecycle calls. Only gw0 stops containers.
- **State file coordination**: gw0 writes keys to JSON state file; gw1+ polls with `wait_for_state_key()`. FileLock prevents concurrent state writes.
- **Fixture splitting pattern**: `if not is_controller(worker_id):` → wait + yield + return; `else:` → create + start + yield → teardown.

### Integration Points
- **`sam_api`** depends on `sam_build` (already xdist-aware in Phase 9), `docker_network` (already xdist-aware in Phase 9), `warm_functions`, `warm_api_routes`
- **`sam_lambda_endpoint`** depends on `sam_build`, `docker_network`, `warm_functions`
- **`lambda_client`** depends on `sam_lambda_endpoint` — works automatically once that fixture resolves on gw1+
- **Warm container flow**: `_pre_warm_functions()` and `_pre_warm_api_routes()` run inside the gw0 fixture body before yielding the endpoint

</code_context>

<specifics>
## Specific Ideas

No specific references or "I want it like X" moments. The Phase 9 patterns (`localstack_container`, `sam_build`) are the reference implementation — make `sam_api` and `sam_lambda_endpoint` look like those fixtures.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 10-sam-api-lambda-xdist-awareness*
*Context gathered: 2026-05-01*

# Phase 2: Container-Level Ryuk Verification - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Empirically verify that the three samstack container fixtures — LocalStack, SAM API, and SAM Lambda — carry the Ryuk session label (`org.testcontainers.session-id`) after `.start()` is called. This phase is verification-only: no implementation changes are expected. The testcontainers library auto-labels containers in `DockerContainer.start()`, but this has never been explicitly tested. Tests use Docker SDK label queries to assert containers are Ryuk-eligible without requiring a SIGKILL crash cycle.

</domain>

<decisions>
## Implementation Decisions

### Verification Mechanism
- **D-01:** Label inspection only — assert `org.testcontainers.session-id` (`LABEL_SESSION_ID`) is present on containers after `.start()`. No crash test for containers; TEST-03 in `test_ryuk_crash.py` already covers end-to-end network crash cleanup.
- **D-02:** Use Docker SDK label query: `docker_client.containers.list(filters={"label": "org.testcontainers.session-id"})` to find all session-labeled containers. Does not require direct container handles from fixtures.

### Container Scope
- **D-03:** All three fixture types must be verified: LocalStack, SAM API, SAM Lambda. Each represents a distinct fixture code path even though all use the same `DockerContainer.start()` base.

### Test Structure
- **D-04:** New dedicated file: `tests/integration/test_ryuk_container_labels.py`. Mirrors the `test_ryuk_crash.py` file-per-concern pattern. SAM containers are verified via Docker SDK label query when available in the running session.
- **D-05:** CI gating: same `pytestmark = pytest.mark.skipif(testcontainers_config.ryuk_disabled, ...)` pattern as TEST-03 for any tests that depend on Ryuk being active. Label checks that only inspect container metadata may run everywhere (Ryuk disabled does not prevent label inspection).

### Carrying Forward from Phase 1
- **D-06:** Gate all Ryuk-aware code behind `if not testcontainers_config.ryuk_disabled:` (D-03 from Phase 1).
- **D-07:** Sub-container cascade (D-10 from Phase 1) remains deferred to Phase 3 — do NOT hard-assert Lambda sub-container cleanup in this phase.

### Claude's Discretion
- Whether to split the test class into LocalStack-only (runs in `tests/integration/`) and SAM (runs in `tests/` top-level with the hello_world conftest) or keep them in one file — let the planner choose the right placement based on fixture scope availability.
- Exact container name/image filtering to identify LocalStack vs SAM API vs SAM Lambda containers in the Docker SDK response (e.g., filter by image name or container name prefix).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 decisions (locked)
- `.planning/phases/01-ryuk-network-wiring/01-CONTEXT.md` — All Phase 1 implementation decisions; D-03 (ryuk_disabled gate), D-10 (sub-container cascade deferred) carry forward directly.

### Existing test patterns
- `tests/integration/test_ryuk_crash.py` — SIGKILL crash test (TEST-03); establishes pytestmark skip guard, subprocess session pattern, Docker SDK polling. New tests follow the same file-level skip pattern.
- `tests/integration/conftest.py` — Integration session setup: LocalStack-only, no SAM build.
- `tests/conftest.py` — Top-level session: includes hello_world SAM build + sam_api + sam_lambda_endpoint.

### Source fixtures under test
- `src/samstack/fixtures/localstack.py` — `localstack_container` fixture (yields `LocalStackContainer`); `docker_network` Ryuk wiring already in place.
- `src/samstack/fixtures/_sam_container.py` — `create_sam_container()` / `_run_sam_service()` — how SAM containers are built and started.
- `src/samstack/fixtures/sam_api.py` — `sam_api` fixture.
- `src/samstack/fixtures/sam_lambda.py` — `sam_lambda_endpoint` fixture.

### testcontainers label constants
- `testcontainers.core.labels` — `LABEL_SESSION_ID`, `SESSION_ID` — same imports used in `localstack.py`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LABEL_SESSION_ID`, `SESSION_ID` from `testcontainers.core.labels` — already imported in `localstack.py`; use the same import in the test.
- `testcontainers_config.ryuk_disabled` — already used in `localstack.py` and `test_ryuk_crash.py`; same guard for new tests.
- `docker.from_env()` — Docker SDK client; `containers.list(filters={"label": ...})` is the inspection mechanism.

### Established Patterns
- `pytestmark = pytest.mark.skipif(testcontainers_config.ryuk_disabled, reason="...")` — module-level skip guard established in `test_ryuk_crash.py`; mirror exactly.
- `localstack_container.get_wrapped_container()` — returns the raw Docker SDK container object from which `.labels` can be read directly (alternative to full SDK list query for LocalStack-specific assertions).
- Tests in `tests/integration/` use the session-scoped `localstack_container` via the integration conftest.
- Tests in `tests/` top-level use SAM fixtures (`sam_api`, `sam_lambda_endpoint`) via `tests/conftest.py`.

### Integration Points
- `tests/integration/test_ryuk_container_labels.py` will depend on `localstack_container` (from integration session).
- SAM container label assertions may need to live at `tests/` top level to access `sam_api`/`sam_lambda_endpoint` session fixtures — or use Docker SDK list query to find SAM containers running in the same Docker session.

</code_context>

<specifics>
## Specific Ideas

- For LocalStack: `container.get_wrapped_container().labels` is the direct path to check `LABEL_SESSION_ID` without a Docker SDK list call.
- For SAM containers: `docker_client.containers.list(filters={"label": f"org.testcontainers.session-id={SESSION_ID}"})` returns exactly the containers from the current testcontainers session — filter by image or name to separate SAM API from SAM Lambda.
- The Session ID value (`SESSION_ID`) from `testcontainers.core.labels` can be used to scope the query to the current test session only, avoiding false-positive matches from other running sessions.

</specifics>

<deferred>
## Deferred Ideas

- Sub-container cascade verification (SAM Lambda sub-containers spawned via DinD) — deferred to Phase 3 per ROADMAP.md. Do NOT hard-assert sub-container cleanup in Phase 2.
- Crash test for containers (SIGKILL + assert containers removed by Ryuk) — user chose label inspection only; crash test deferred if ever needed.

</deferred>

---

*Phase: 02-container-level-ryuk-verification*
*Context gathered: 2026-04-24*

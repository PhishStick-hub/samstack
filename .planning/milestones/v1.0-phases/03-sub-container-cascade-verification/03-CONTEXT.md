# Phase 3: Sub-Container Cascade Verification - Context

**Gathered:** 2026-04-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Empirically verify that SAM Lambda runtime sub-containers — spawned by SAM CLI via Docker-in-Docker — are cleaned up when the Docker bridge network is removed. Two cleanup paths are verified: normal teardown (`_teardown_network` in `localstack.py:49-54` iterates and stops containers on the network) and crash (Ryuk detects process death and removes the network, triggering Docker's cascade disconnect). Phase 2 verified main fixture containers carry Ryuk labels; Phase 3 verifies the unlabeled sub-containers those fixtures spawn.

This is a verification-only phase: no implementation changes to fixture code. The existing TEST-03 cascade observation (`test_ryuk_crash.py:136-150`) is upgraded from a print statement to a hard assertion, and a new teardown-path test is added.

</domain>

<decisions>
## Implementation Decisions

### Verification Scope
- **D-01:** Verify Lambda runtime sub-containers only — not API Gateway containers, not build/layer containers. Lambda runtimes are the ones that execute Lambda code on the network and represent the "leftover containers" concern.
- **D-02:** Verify both cleanup paths: (a) normal teardown via `_teardown_network`, (b) crash via Ryuk network removal. Normal teardown is already observable; the crash path (Ryuk) is the primary gap.

### Assertion Strategy
- **D-03:** Hard-assert sub-containers are **removed** — not just stopped/exited, not just disconnected from the network. Use `docker_client.containers.list()` with network-scoped filters to check for zero containers post-cleanup.
- **D-04:** Generous timeout with different tolerances per path: crash path 30s (Ryuk detection + Docker async cleanup), normal teardown 15s. Docker daemon cleanup is async; sub-containers may take a few seconds to transition from running → exited → removed.
- **D-05:** Same platform skip as TEST-03: crash-path assertion skips on macOS (`sys.platform == "darwin"`) — Docker Desktop's TCP proxy layer does not propagate SIGKILL connection drops to Ryuk inside the Linux VM. Normal teardown path runs on all platforms.

### Test Structure & Placement
- **D-06:** Extend the existing TEST-03 subprocess crash test (`test_ryuk_crash.py`): upgrade the subprocess session from minimal `docker_network`-only to include a full SAM session with Lambda invocation, so sub-containers exist before the SIGKILL. Replace the `cascade_note` print with a hard `assert gone` on sub-containers.
- **D-07:** Add a new dedicated test (file TBD by planner — `test_subcontainer_cascade.py` or within `test_ryuk_crash.py`) for the normal teardown path. This test runs in an existing full SAM session, triggers at least one Lambda invocation, lets the session teardown cleanly, and asserts zero sub-containers remain.
- **D-08:** Both tests must trigger Lambda invocation to create sub-containers. The hello_world fixture Lambda (`tests/fixtures/hello_world/`) is the natural candidate — GET `/hello` is a quick 200 that creates a Lambda runtime container on the network.

### Carrying Forward from Prior Phases
- **D-09:** Gate all Ryuk-aware assertions behind `if not testcontainers_config.ryuk_disabled:` (D-03 from Phase 1, D-06 from Phase 2).
- **D-10:** Sub-container cascade was documented but not hard-asserted in Phase 1 D-10 and Phase 2 D-07 — Phase 3 resolves this by turning observation into assertion.

### Clause's Discretion
- Exact timeout values (crash: 30s, normal: 15s are suggestions — planner can adjust based on CI performance data)
- Whether crash test and teardown test live in the same file (`test_ryuk_crash.py`) or separate files — let the planner choose based on fixture scope availability
- Docker SDK query mechanism: `containers.list(filters={"network": network_name})` vs `network.containers` — either works; network-scoped filter is more precise
- Whether to verify sub-container identity by name pattern (SAM spawns containers with `sam_` prefix) or rely purely on network membership — network membership is sufficient per D-03

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 decisions (locked)
- `.planning/phases/01-ryuk-network-wiring/01-CONTEXT.md` — D-03 (ryuk_disabled gate), D-10 (sub-container cascade documented but not hard-asserted — Phase 3 resolves this)

### Phase 2 decisions (locked)
- `.planning/phases/02-container-level-ryuk-verification/02-CONTEXT.md` — D-06 (ryuk_disabled gate), D-07 (sub-container cascade deferred to Phase 3)

### Existing crash test (to extend)
- `tests/integration/test_ryuk_crash.py` — TEST-03: existing crash test with `cascade_note` observation at lines 136-150. Phase 3 upgrades this observation to hard assertion and adds full SAM session to the subprocess.
- `tests/integration/conftest.py` — Integration session setup: LocalStack only, no SAM build. The extended crash test subprocess will need its own SAM conftest.

### Source fixtures
- `src/samstack/fixtures/localstack.py` — `docker_network` fixture (lines 71-96): network creation with Ryuk labels, registration, and `_teardown_network` (lines 49-59) normal exit cleanup. The teardown path iterates `network.containers`, stops each, removes the network.
- `src/samstack/fixtures/_sam_container.py` — `create_sam_container()` (lines 154-179): mounts `/var/run/docker.sock` for DinD, connects SAM container to network post-start. `_run_sam_service()` (lines 88-151): full SAM container lifecycle including disconnect+stop in `finally`.

### Test Fixture Lambda
- `tests/fixtures/hello_world/` — `src/handler.py` + `template.yaml`: GET `/hello` → 200 is the simplest Lambda invocation to trigger sub-container creation.
- `tests/conftest.py` — Top-level session conftest that overrides `samstack_settings` for hello_world and provides `sam_api`, `sam_lambda_endpoint`.

### Research (gap analysis)
- `.planning/research/SUMMARY.md` — "SAM-spawned Lambda runtime sub-containers: SAM CLI creates these internally without testcontainers labels. Docker may reject network removal if unlabeled sub-containers are still attached." — identifies the gap Phase 3 verifies.

### testcontainers constants
- `testcontainers.core.labels` — `LABEL_SESSION_ID`, `SESSION_ID` — sub-containers will NOT have these labels (SAM CLI creates them without testcontainers); the gap is verified by confirming cleanup despite missing labels.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/integration/test_ryuk_crash.py` — Full crash test template: `_write_subprocess_session()`, `_poll_until_gone()`, subprocess launch + SIGKILL + Docker poll. The crash test extension reuses this pattern with a richer subprocess session.
- `tests/fixtures/hello_world/` — Existing Lambda that returns 200 on GET `/hello`. Minimal overhead, fast startup — ideal for triggering sub-container creation.
- `tests/conftest.py` — Session conftest for hello_world SAM session (provides `sam_api`, `sam_lambda_endpoint`). The crash test subprocess needs its own self-contained conftest (same pattern as TEST-03's `_write_subprocess_session`).
- `_poll_until_gone()` at `test_ryuk_crash.py:71-85` — Docker network polling abstraction; can be reused or mirrored for container polling.

### Established Patterns
- `pytestmark = pytest.mark.skipif(testcontainers_config.ryuk_disabled or sys.platform == "darwin", ...)` — Module-level skip guard from TEST-03. Crash-path test uses this. Teardown-path test only gates on `ryuk_disabled` (runs on macOS too).
- Subprocess pytest sessions: `_write_subprocess_session()` writes conftest + test file to `tmp_path`, launches via `subprocess.Popen`, SIGKILLs, polls Docker. The Phase 3 extension adds SAM build + Lambda invocation to the subprocess session.
- Docker SDK label queries: `docker_client.containers.list(filters={"network": network_name})` to find containers on a specific network — established in TEST-03 cascade observation.
- `docker.from_env()` — Docker SDK client instantiation; used throughout test and fixture code.

### Integration Points
- Crash test subprocess needs a self-contained SAM session: conftest with `samstack_settings`, `sam_env_vars` (pointing at LocalStack), SAM build, and a test that triggers Lambda invocation before stalling.
- Teardown test runs in an existing session (e.g., `tests/` top-level with conftest that already has `sam_api`) — just needs a test function that invokes Lambda and lets the session teardown gracefully.
- The hello_world Lambda's GET `/hello` endpoint is the simplest trigger: `requests.get(f"{sam_api}/hello")` → 200, Lambda container created on network.
- LocalStack must be running in the subprocess session too — Lambda code might reference `AWS_ENDPOINT_URL_*` env vars that point to `localstack` DNS alias.

</code_context>

<specifics>
## Specific Ideas

- The crash test subprocess needs a richer conftest than TEST-03's minimal one — it needs `samstack_settings`, `sam_env_vars` pointing at LocalStack, `sam_build`, and `sam_api` or `sam_lambda_endpoint`. This follows the same `_write_subprocess_session()` pattern but with more fixture wiring.
- The teardown test can be a straightforward integration test: request a Lambda invocation, exit the test, and in a post-session hook (or a separate poll step) assert no sub-containers remain.
- For the crash test: trigger Lambda invocation, sleep briefly (to ensure sub-container exists on the network), then SIGKILL. The sub-container should still exist at SIGKILL time — LAZY warm containers keep the runtime container alive briefly.
- Consider using `requests.get(f"{sam_api}/hello")` (HTTP through API Gateway) rather than `lambda_client.invoke` — the API Gateway path exercises a more complete sub-container creation that mirrors production use.
- Sub-containers are identifiable by Docker naming convention: SAM CLI prefixes them with `sam_` — useful as a secondary filter if network-scoped queries return containers from other concurrent sessions.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-sub-container-cascade-verification*
*Context gathered: 2026-04-25*

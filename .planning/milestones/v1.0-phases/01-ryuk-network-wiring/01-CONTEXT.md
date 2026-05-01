# Phase 1: Ryuk Network Wiring - Context

**Gathered:** 2026-04-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the `docker_network` fixture to be Ryuk-aware: label the Docker bridge network at creation time, register it with the Ryuk TCP socket, guard CI environments where Ryuk is disabled, and verify with unit tests plus an automated crash test. All changes land inside `docker_network` in `src/samstack/fixtures/localstack.py`. No other files need structural modification.

</domain>

<decisions>
## Implementation Decisions

### Ryuk Wiring (locked from requirements)
- **D-01:** Label the network at creation: `labels={LABEL_SESSION_ID: SESSION_ID}` — import `SESSION_ID` and `LABEL_SESSION_ID` from `testcontainers.core.labels`
- **D-02:** Register network with Ryuk via `network=name=<name>\r\n` filter on the TCP socket (belt-and-suspenders — label alone is not sufficient for network cleanup)
- **D-03:** Gate all Ryuk code behind `if not testcontainers_config.ryuk_disabled:` — import from `testcontainers.core.config`
- **D-04:** Socket failures emit `warnings.warn`, not `raise` — test session must survive Ryuk registration failure
- **D-05:** `_teardown_network` teardown path preserved unchanged in the `finally` block — Ryuk is additive crash-safety, not a replacement for normal-exit cleanup
- **D-06:** Call `Reaper.get_instance()` explicitly before accessing `_socket` — `docker_network` runs before any `DockerContainer.start()`, so Ryuk may not be initialized yet; `get_instance()` is idempotent
- **D-07:** Access `Reaper._socket` directly (private) — testcontainers exposes no public send API; acceptable given it's guarded by try/except

### Crash Test (TEST-03)
- **D-08:** Automated pytest integration test in `tests/integration/`
- **D-09:** Fixture scope: `docker_network` in isolation — no SAM build, no LocalStack pull; spawn a minimal pytest subprocess that uses only `docker_network`, SIGKILL it, then poll Docker to assert the network is gone (404)
- **D-10:** Assert: Docker network returns 404 after SIGKILL — hard assert. Sub-container cascade behavior documented but NOT hard-asserted (empirically unverified; Docker cleanup timing varies)

### Claude's Discretion
- Stacklevel for `warnings.warn` on Ryuk socket failure — follow `warnings-stacklevel` knowledge base pattern (stacklevel=2 baseline from inside fixture helper)
- Exact poll interval and timeout for the crash test network-gone assertion — keep short (2–5 s max, 0.5 s poll)
- Whether to extract a `_register_with_ryuk(network_name)` helper or inline the logic directly — either is fine given the small size

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — All RYUK-* and TEST-* requirements; traceability table

### Research
- `.planning/research/SUMMARY.md` — Confirmed Ryuk wiring approach, exact import symbols, execution order, critical pitfalls (especially Reaper._socket initialization order and network filter syntax)

### Existing code
- `src/samstack/fixtures/localstack.py` — `docker_network` fixture (the only file being modified); `_teardown_network` helper must be preserved
- `tests/unit/` — Existing unit test pattern to follow for TEST-01 and TEST-02 placement and style
- `tests/integration/` — Target directory for automated crash test (TEST-03)

### Knowledge base patterns
- `~/.claude/projects/-Users-ivan-shcherbenko-Repo-samstack/../../../knowledge/testing/samstack-plugin.md` — Two-layer failure pattern, skip-pull-image, CI auto-detection context
- `warnings-stacklevel` pattern — stacklevel=2 for library fixture helpers

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_teardown_network(network, name)` in `localstack.py` — must remain unchanged; it is the primary cleanup path and is already robust
- `_stop_network_container` — stop/remove helper used by teardown; no changes needed
- `docker_network_name` fixture — provides the UUID-based name; `docker_network` receives it as a dependency

### Established Patterns
- `warnings.warn` with `stacklevel=2` is already used in `_stop_network_container` and `_teardown_network` — match this pattern for Ryuk socket failure warnings
- `contextlib.suppress(Exception)` used in teardown for best-effort cleanup — acceptable to mirror in crash test teardown assertions if needed
- `testcontainers.localstack.LocalStackContainer` already registered with Ryuk via `.start()` — no changes to LocalStack or SAM container fixtures

### Integration Points
- The `docker_network` fixture is session-scoped and is a dependency of `localstack_container`, `sam_api`, and `sam_lambda_endpoint` — any change must not affect the yielded value (`str` network name) or raise before yield

</code_context>

<specifics>
## Specific Ideas

- The crash test subprocess should use a throwaway conftest that overrides `samstack_settings` (or skips it entirely) — only `docker_network` needs to run; see `tests/conftest.py` for the override pattern
- Ryuk execution order in `docker_network`: (1) create network with labels, (2) `if not ryuk_disabled:`, (3) `Reaper.get_instance()`, (4) send `network=name=<name>\r\n` in try/except → `warnings.warn`, (5) `yield`, (6) `finally: _teardown_network(...)` — exactly as documented in SUMMARY.md

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-ryuk-network-wiring*
*Context gathered: 2026-04-23*

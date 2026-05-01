# Milestones

## v2.0.0 — Orphan Container Cleanup

**Shipped:** 2026-04-25
**Phases:** 3 | **Plans:** 5 | **Tasks:** 7
**Timeline:** 2026-04-03 → 2026-04-25 (22 days)

### What Shipped

All samstack-managed Docker infrastructure is crash-safe via testcontainers Ryuk reaper integration. The bridge network is labeled and registered with Ryuk. All three main container fixtures (LocalStack, SAM API, SAM Lambda) carry Ryuk session labels. SAM-spawned Lambda runtime sub-containers (without testcontainers labels) are cleaned up via network cascade on both crash and normal teardown paths. A SIGKILL mid-run leaves nothing behind.

### Key Accomplishments

1. **Ryuk network wiring** — Docker bridge network labeled with `org.testcontainers.session-id` and registered via TCP socket, gated by `ryuk_disabled`
2. **Container label verification** — LocalStack, SAM API, SAM Lambda containers all confirmed to carry Ryuk session label after `.start()`
3. **Sub-container cascade verification** — SAM Lambda runtime sub-containers (no labels) empirically verified to be cleaned up on network removal
4. **Dual-path verification** — Both crash (Ryuk) and normal teardown (`_teardown_network`) paths verified for sub-container cleanup
5. **Automated crash testing** — SIGKILL subprocess framework with Docker API polling, platform guards, and CI-safe skip logic
6. **Zero regression** — All 86 unit tests pass; ruff + format clean

### Requirements

All 8 v1 requirements shipped across 3 phases — see `.planning/milestones/v2.0.0-REQUIREMENTS.md` for full traceability.

### Deferred to v2

- Migrate `docker_network` to `testcontainers.core.network.Network` (breaking API change)
- Phase 1 HUMAN-UAT (partial) — acknowledged at milestone close
- Phase 1 VERIFICATION (human_needed) — acknowledged at milestone close

### Known Deferred Items at Close

2 items acknowledged — see `.planning/STATE.md` Deferred Items.

### Full Archive

- Roadmap: `.planning/milestones/v2.0.0-ROADMAP.md`
- Requirements: `.planning/milestones/v2.0.0-REQUIREMENTS.md`

---

## v2.2.0 — Per-Function Warm Containers

**Shipped:** 2026-04-25
**Phases:** 4 | **Plans:** 6 | **Tasks:** 16
**Timeline:** 2026-04-25 (1 day)

### What Shipped

Per-function warm container control lets testers configure which Lambda functions get pre-warmed via `pyproject.toml` or fixture overrides. `start-lambda` functions are pre-warmed via `boto3 lambda_client.invoke()`. `start-api` functions via HTTP GET. Integration tests with init-marker UUID pattern prove container reuse. Warm sub-container crash test verifies Ryuk cascade cleanup.

### Key Accomplishments

1. **Per-function config** — `warm_functions` field in `SamStackSettings` + overridable session fixture
2. **start-lambda pre-warm** — Sequential `invoke()` with hard-fail via `SamStartupError`
3. **start-api pre-warm** — `warm_api_routes` fixture with HTTP GET, intersection filter with `warm_functions`
4. **Dynamic warm containers** — LAZY when functions specified, EAGER when empty (backward compatible)
5. **Warm verification tests** — Init-marker UUID pattern proves container reuse across invocations
6. **Crash test** — Warm sub-containers cleaned up by Ryuk cascade after SIGKILL
7. **Documentation** — README with config reference, fixtures table, and known limitations

### Requirements

All 12 v2.2.0 requirements shipped across 4 phases — see `.planning/milestones/v2.2.0-REQUIREMENTS.md` for full traceability.

### Full Archive

- Roadmap: `.planning/milestones/v2.2.0-ROADMAP.md`
- Requirements: `.planning/milestones/v2.2.0-REQUIREMENTS.md`

---

*Last updated: 2026-04-25 after v2.2.0 milestone completion*

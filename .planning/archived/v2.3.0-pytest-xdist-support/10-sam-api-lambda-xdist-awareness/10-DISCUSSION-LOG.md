# Phase 10 Discussion Log

**Phase:** 10 — SAM API + Lambda Xdist-Awareness
**Mode:** Interactive discuss (no --auto, no --all)
**Gathered:** 2026-05-01

---

## Area 1: Pre-warm failure behavior

### Q: How should gw0 handle pre-warm failures for SAM containers under xdist?

**Options presented:**
- Fail all workers (Recommended) — Keep current behavior: pre-warm failure raises SamStartupError, gw0 writes 'error' to state, all workers fail. Warm containers are a hard requirement.
- Decouple: write endpoint, warn — Write SAM endpoint to state even if pre-warm fails, with a flag like 'warm_partial: true'. gw1+ proceeds but with potentially cold containers for the failed functions. Logs the warning.
- Skip pre-warm in xdist — Don't pre-warm in xdist mode at all. All containers start cold on first use across all workers. Simplest but slowest for first requests.

**Selected:** Fail all workers (Recommended)

### Outcome
D-07: Pre-warm failure is a hard failure — raises SamStartupError, gw0 writes "error" key to shared state, all gw1+ workers receive pytest.fail(). No partial-warm or degraded mode. Consistent with existing non-xdist behavior.

---

## Area 2: Warm container coordination (gw1+ verification)

### Q: Should gw1+ workers verify that the shared SAM container is actually responding, or trust gw0's startup implicitly?

**Options presented:**
- Trust gw0 implicitly (Recommended) — gw1+ reads endpoint from state, yields it immediately. No verification. Matches Phase 9 pattern.
- Lightweight ping verification — gw1+ sends a single lightweight ping (HTTP GET for API, or no-op invoke for Lambda) before yielding. Adds ~0.1s per worker startup.

**Selected:** Trust gw0 implicitly (Recommended)

### Outcome
D-08: gw1+ trusts gw0 implicitly — no lightweight ping, health check, or verification before yielding the endpoint. Matches Phase 9 trust pattern where gw1+ reads localstack_endpoint and build_complete without verification.

---

## Area 3: SAM service container startup ordering

### Q: How should gw0 coordinate SAM API and Lambda container startup under xdist?

**Options presented:**
- Keep lazy/deferred startup (Recommended) — Each SAM container starts when first requested by any worker. gw0 handling added inside each fixture. Simplest approach.
- Eager ordered startup — gw0 starts start-lambda first, then start-api, at session setup. Requires orchestrating fixture.

**Selected:** Keep lazy/deferred startup (Recommended)

### Outcome
D-09: Keep lazy/deferred startup — each SAM container fixture starts when its first dependent is requested. No forced ordering or orchestrating fixture. The existing fixture dependency graph (sam_build → sam_api / sam_lambda_endpoint) naturally handles ordering.

---

## All Areas Complete

**Total areas discussed:** 3
**Total decisions captured:** 10 (D-01 through D-10)
**Deferred ideas:** None

*Discussion completed: 2026-05-01*

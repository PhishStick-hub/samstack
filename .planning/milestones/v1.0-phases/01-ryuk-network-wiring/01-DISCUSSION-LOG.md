# Phase 1: Ryuk Network Wiring - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-23
**Phase:** 01-ryuk-network-wiring
**Areas discussed:** Crash test format

---

## Crash test format

| Option | Description | Selected |
|--------|-------------|----------|
| Automated subprocess test | A pytest integration test that spawns a pytest subprocess against a minimal fixture, SIGKILLs it, then asserts the network is gone. Runs in CI, catches regressions automatically. | ✓ |
| Manual recipe only | Document a manual verification script with steps to SIGKILL and docker inspect. Simpler, no CI coupling. | |
| Manual recipe + automated smoke check | Manual crash test for the SIGKILL scenario plus automated unit test that verifies teardown path would be invoked. | |

**User's choice:** Automated subprocess test

---

## Crash test placement

| Option | Description | Selected |
|--------|-------------|----------|
| tests/integration/ — assert network gone | Place alongside other integration tests. Assert docker network inspect returns 404 after a short poll. Sub-container cascade documented but not hard-asserted. | ✓ |
| tests/integration/ — assert network + containers gone | Same placement, but hard-assert all containers are also removed. Stricter, risks flakiness. | |
| tests/test_crash.py — isolated crash suite | Separate top-level file, same assertions. | |

**User's choice:** tests/integration/ — assert network gone

---

## Crash test scope

| Option | Description | Selected |
|--------|-------------|----------|
| docker_network in isolation | Spawn just docker_network in a subprocess session, SIGKILL it. Faster, no SAM/LocalStack required. | ✓ |
| Full samstack session | Spawn a real pytest session with LocalStack + SAM, SIGKILL it. More realistic but very slow. | |

**User's choice:** docker_network in isolation

---

## Areas not discussed (user skipped)

- **Unit test structure** — TEST-01/TEST-02 placement and mocking approach left to Claude's discretion
- **Reaper._socket access** — Direct private access left to Claude's discretion (research recommendation accepted)

## Deferred Ideas

None.

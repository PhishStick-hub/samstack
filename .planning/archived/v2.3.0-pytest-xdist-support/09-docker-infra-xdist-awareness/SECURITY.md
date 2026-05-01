# SECURITY.md — Phase 09: docker-infra-xdist-awareness

**Audit Date:** 2026-04-30
**ASVS Level:** 1
**Threats Closed:** 12/12
**Threats Open:** 0

---

## Mitigate Threats (code-verified)

| Threat ID | Category | Component | Status | Evidence |
|-----------|----------|-----------|--------|----------|
| T-09-04 | Denial of Service | gw1+ polling `wait_for_state_key` | CLOSED | `src/samstack/fixtures/localstack.py:188` — `wait_for_state_key("localstack_endpoint", timeout=120)`; `src/samstack/_xdist.py:73,77,81` — 0.5s poll interval, `error` key triggers `pytest.fail()`, deadline enforced |
| T-09-06 | Denial of Service | gw0 Docker startup failure | CLOSED | `src/samstack/fixtures/localstack.py:199-203` — `container.start()` exception writes `write_state_file("error", ...)`; lines 210-215 (container None path) and 224-229 (network connect failure) also write `error` key |
| T-09-09 | Denial of Service | gw0 build failure blocking gw1+ | CLOSED | `src/samstack/fixtures/sam_build.py:146-150` — non-zero exit code writes `write_state_file("error", ...)`; lines 154-159 — general exception also writes `error` key; both paths covered |
| T-09-10 | Denial of Service | gw1+ infinite wait on missing flag | CLOSED | `src/samstack/fixtures/sam_build.py:108` — `wait_for_state_key("build_complete", timeout=300)`; `src/samstack/_xdist.py:70,77,81` — 0.5s default poll interval, `error` key triggers early `pytest.fail()`, hard deadline enforced |

### Implementation Note — pytest.fail() vs pytest.skip()

Threat mitigations T-09-04, T-09-06, T-09-09, T-09-10 declared `pytest.skip()` in the mitigation plan. The implementation uses `pytest.fail()` (`_xdist.py:77,81`). This is a stricter disposition: worker tests are marked FAILED rather than SKIPPED on infrastructure error, which is acceptable and does not weaken the DoS mitigation. The fail-fast goal is met.

---

## Accepted Threats (no code verification required)

| Threat ID | Category | Component | Status | Accept Rationale |
|-----------|----------|-----------|--------|-----------------|
| T-09-01 | Spoofing | localstack_container gw0 role detection | ACCEPTED | `PYTEST_XDIST_WORKER` set by pytest-xdist, not user-controllable |
| T-09-02 | Tampering | Shared state file localstack_endpoint key | ACCEPTED | State file in temp dir with UUID isolation; Docker URLs are internal-only, no secrets |
| T-09-03 | Information Disclosure | localstack_endpoint in shared state | ACCEPTED | Contains only `http://127.0.0.1:PORT` — local loopback address, no sensitive data |
| T-09-05 | Elevation | _LocalStackContainerProxy on gw1+ | ACCEPTED | Proxy is a pure data wrapper with no system calls; no privilege escalation path |
| T-09-07 | Spoofing | sam_build gw0 role detection | ACCEPTED | `PYTEST_XDIST_WORKER` set by pytest-xdist, not user-controllable |
| T-09-08 | Tampering | build_complete flag in shared state | ACCEPTED | State file in temp dir with UUID isolation; flag is boolean — no injection surface |
| T-09-11 | Information Disclosure | build_complete flag in temp dir | ACCEPTED | Boolean flag only — no sensitive data; temp dir permissions are OS-default |
| T-09-12 | Elevation | Docker socket access on gw1+ | ACCEPTED | gw1+ never mounts DOCKER_SOCKET volume — `run_one_shot_container` is never called on gw1+ path |

---

## Unregistered Threat Flags

None identified during implementation (per SUMMARY.md).

---

## Verdict

All 12 threats accounted for: 4 mitigated (code-verified), 8 accepted (documented). Phase 09 is cleared to ship.

---

## Security Audit 2026-05-01

| Metric | Count |
|--------|-------|
| Threats found | 12 |
| Closed | 12 |
| Open | 0 |

**Re-verification notes:**

- T-09-04 (`wait_for_state_key` DoS): Confirmed at `_xdist.py:73,77,81` — 0.5s poll interval, deadline enforced, `pytest.fail()` on `error` key.
- T-09-06 (gw0 Docker startup failure): Confirmed at `localstack.py:196-204` (start exception), `localstack.py:208-216` (container None), `localstack.py:219-229` (network connect failure) — all three paths write `error` key.
- T-09-09 (gw0 build failure): Confirmed at `sam_build.py:145-151` (non-zero exit), `sam_build.py:152-160` (general exception) — both paths write `error` key.
- T-09-10 (gw1+ infinite wait): Confirmed at `sam_build.py:108` — `wait_for_state_key("build_complete", timeout=300)` with `pytest.fail()` on error/timeout in `_xdist.py:77,81`.
- No threat flags detected in 09-01-SUMMARY.md or 09-02-SUMMARY.md.
- All accepted threats maintain valid rationale (env var trust, UUID isolation, no injection surfaces).

**Verdict:** All 12 threats remain closed. No regressions detected.

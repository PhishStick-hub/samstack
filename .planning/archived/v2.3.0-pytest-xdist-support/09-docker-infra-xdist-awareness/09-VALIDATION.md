---
phase: 09
slug: docker-infra-xdist-awareness
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-01
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/unit/test_xdist_localstack.py tests/unit/test_xdist_sam_build.py tests/unit/test_xdist_fixtures.py tests/unit/test_xdist_resource_isolation.py -v` |
| **Full suite command** | `uv run pytest tests/unit/ -v` |
| **Estimated runtime** | ~0.1s (unit tests, no Docker) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_xdist*.py -v`
- **After every plan wave:** Run `uv run pytest tests/unit/ -v && uv run ruff check . && uv run ty check`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 0.1 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | INFRA-02, INFRA-05 | T-09-04, T-09-05, T-09-06 | gw0 writes endpoint, gw1+ yields proxy, error cascade | unit | `uv run pytest tests/unit/test_xdist_localstack.py -v` | ✅ | ✅ green |
| 09-01-02 | 01 | 1 | INFRA-02, INFRA-05 | T-09-04, T-09-05, T-09-06 | 13 tests covering master/gw0/gw1+ paths, no Docker | unit | `uv run pytest tests/unit/test_xdist_localstack.py -v` | ✅ | ✅ green |
| 09-01-03 | 01 | 1 | INFRA-02, INFRA-05 | — | ruff + ty + all unit tests green | lint+type | `uv run ruff check . && uv run ty check && uv run pytest tests/unit/ -v` | — | ✅ green |
| 09-02-01 | 02 | 1 | INFRA-03 | T-09-09, T-09-10, T-09-11, T-09-12 | gw0 runs build + writes flag, gw1+ polls, error cascade | unit | `uv run pytest tests/unit/test_xdist_sam_build.py -v` | ✅ | ✅ green |
| 09-02-02 | 02 | 1 | INFRA-03 | T-09-09, T-09-10, T-09-11, T-09-12 | 6 tests covering master/gw0/gw1+ paths, no Docker | unit | `uv run pytest tests/unit/test_xdist_sam_build.py -v` | ✅ | ✅ green |
| 09-02-03 | 02 | 1 | INFRA-03, INFRA-04 | T-09-09, T-09-10, T-09-11, T-09-12 | INFRA-04: UUID naming isolation verified | unit | `uv run pytest tests/unit/test_xdist_resource_isolation.py -v` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. Test files:
- `tests/unit/test_xdist_localstack.py` — 13 tests (created in 09-01)
- `tests/unit/test_xdist_sam_build.py` — 6 tests (created in 09-02)
- `tests/unit/test_xdist_resource_isolation.py` — 10 tests (created in validation)

---

## Manual-Only Verifications

None. All phase behaviors have automated verification.

---

## Validation Audit 2026-05-01

| Metric | Count |
|--------|-------|
| Gaps found | 1 |
| Resolved | 1 |
| Escalated | 0 |

**Gap resolved:** INFRA-04 (resource fixture per-worker isolation) — was verification-by-inspection only. Added `tests/unit/test_xdist_resource_isolation.py` with 10 automated tests verifying all 8 resource fixtures produce unique UUID-based names per call.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 1s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-01

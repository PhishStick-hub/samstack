---
phase: 11
slug: mock-coordination
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-01
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `uv run pytest tests/unit/test_mock_xdist.py -v` |
| **Full suite command** | `uv run pytest tests/unit/ tests/multi_lambda/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_mock_xdist.py -v`
- **After every plan wave:** Run `uv run pytest tests/unit/ tests/multi_lambda/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | MOCK-01 | T-11-01 / — | gw0 writes `mock_spy_bucket_{alias}` to state, gw1+ reads and constructs LambdaMock without calling make_s3_bucket | unit | `uv run pytest tests/unit/test_mock_xdist.py -v -k gw` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | MOCK-02 | T-11-02 / — | `sam_env_vars[function_name]` contains `MOCK_SPY_BUCKET`, `MOCK_FUNCTION_NAME`, `AWS_ENDPOINT_URL_S3` on both gw0 and gw1+ | unit | `uv run pytest tests/unit/test_mock_xdist.py -v -k env` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 2 | MOCK-03 | T-11-03 / — | Multiple workers writing spy events to shared bucket do not experience key collisions or data corruption | integration | `uv run pytest tests/multi_lambda/ -n 2 -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_mock_xdist.py` — unit tests for gw0/gw1+ split (MOCK-01, MOCK-02)
- [ ] Mock fixtures in `tests/unit/test_mock_xdist.py` — `s3_client` mock, `make_s3_bucket` mock, `sam_env_vars` dict

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cross-worker spy reads | MOCK-01 | Requires xdist with Docker (integration env) | Run `uv run pytest tests/multi_lambda/ -n 2 -v`, verify gw1+ reads spy events written by Lambda invocations from any worker |
| Mock env vars in SAM containers | MOCK-02 | Requires SAM container with env_vars.json | Verify via integration test: Lambda code inside SAM receives MOCK_SPY_BUCKET in env vars |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

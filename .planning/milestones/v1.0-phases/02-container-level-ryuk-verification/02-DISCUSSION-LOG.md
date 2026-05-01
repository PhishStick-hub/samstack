# Phase 2: Container-Level Ryuk Verification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 02-container-level-ryuk-verification
**Areas discussed:** Verification mechanism, Container scope, Test placement, Container access

---

## Verification Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Label inspection only | Assert LABEL_SESSION_ID is set on containers post-.start(). Fast, runs in CI everywhere. No crash test needed. | ✓ |
| Crash test for containers too | SIGKILL-style test asserting containers are removed by Ryuk. Linux-only like TEST-03. | |
| Both: label inspection + crash test | Label inspection runs in CI; crash test provides end-to-end coverage on Linux. | |

**User's choice:** Label inspection only  
**Notes:** TEST-03 already covers end-to-end network crash cleanup. Label inspection is sufficient to prove container Ryuk eligibility.

---

## Container Scope

| Option | Description | Selected |
|--------|-------------|----------|
| LocalStack only | Sufficient since all containers share DockerContainer.start() base. | |
| All three: LocalStack + SAM API + SAM Lambda | Explicit label assertions on each fixture type. | ✓ |
| LocalStack + one SAM container | Middle ground covering both fixture classes. | |

**User's choice:** All three: LocalStack + SAM API + SAM Lambda  
**Notes:** Requirement explicitly calls out all three fixture types.

---

## Test Placement

| Option | Description | Selected |
|--------|-------------|----------|
| New file: tests/integration/test_ryuk_container_labels.py | Dedicated file mirrors test_ryuk_crash.py pattern. | ✓ |
| Extend tests/integration/test_ryuk_crash.py | Add label assertions as second test class. | |
| Add assertions to existing fixture tests | Diffuse coverage across existing files. | |

**User's choice:** New file: tests/integration/test_ryuk_container_labels.py  
**Notes:** Keeps Ryuk label verification clearly separated from crash behavior tests.

---

## Container Access

| Option | Description | Selected |
|--------|-------------|----------|
| Docker SDK label query | containers.list(filters={"label": "org.testcontainers.session-id"}) | ✓ |
| Top-level test file at tests/ | Access sam_api / sam_lambda_endpoint fixtures directly. | |

**User's choice:** Docker SDK label query  
**Notes:** No fixture restructuring needed. Use SESSION_ID from testcontainers.core.labels to scope query to current session only.

---

## Claude's Discretion

- Exact placement of SAM container assertions (integration/ vs top-level tests/)
- Container name/image filtering to distinguish LocalStack vs SAM API vs SAM Lambda in Docker SDK responses

## Deferred Ideas

- Sub-container cascade: deferred to Phase 3 per roadmap
- Container crash test: label inspection chosen instead

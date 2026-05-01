# Phase 11: Mock Coordination - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-01
**Phase:** 11-mock-coordination
**Areas discussed:** Spy bucket coordination, sam_env_vars propagation, Teardown responsibility

---

## Spy bucket coordination

| Option | Description | Selected |
|--------|-------------|----------|
| Shared state key | gw0 writes bucket name to shared state as `mock_spy_bucket_{alias}`. gw1+ reads it via `wait_for_state_key()`. Matches established pattern. | ✓ |
| Deterministic name + lock | All workers compute same bucket name (no UUID). Lock-based creation with HeadBucket check. | |
| gw0-only mock creation | Only gw0 creates the mock. gw1+ reads bucket name from state, constructs LambdaMock directly. | |

**User's choice:** Shared state key approach — gw0 writes bucket name, gw1+ reads it. Follows the established `localstack_endpoint` / `sam_api_endpoint` pattern.

**Notes:** State key naming uses the alias (user-controlled, per-mock unique). gw1+ constructs LambdaMock using `s3_resource` pointed at the shared bucket, not a new `make_s3_bucket` call.

---

## sam_env_vars propagation

| Option | Description | Selected |
|--------|-------------|----------|
| Mutate on all workers | Both gw0 and gw1+ mutate `sam_env_vars[function_name]` with shared bucket name. gw0 feeds build; gw1+ does it for in-memory consistency. | ✓ |
| Skip mutation on gw1+ | gw1+ skips sam_env_vars entirely. SAM already has right env vars from gw0's build. | |
| Sync full env vars via state | gw0 writes full mock env vars dict to shared state. gw1+ reads and injects. | |

**User's choice:** Mutate on all workers — both gw0 and gw1+ inject `MOCK_SPY_BUCKET`, `MOCK_FUNCTION_NAME`, `AWS_ENDPOINT_URL_S3` into `sam_env_vars[function_name]`. Ensures any test code reading `sam_env_vars` directly sees correct values on all workers.

**Notes:** No shared state key needed for full env vars — just the bucket name. gw1+ already has the other values (alias, LocalStack endpoint) from its own fixture state.

---

## Teardown responsibility

| Option | Description | Selected |
|--------|-------------|----------|
| gw0 only | Only gw0 deletes the shared spy bucket on session teardown. gw1+ yields and returns with no teardown. | ✓ |
| gw0 deletes bucket, gw1+ can .clear() | gw0 owns bucket lifecycle. gw1+ can call LambdaMock.clear() (object-level, not bucket-level). | |
| Coordinated teardown via hook | Workers coordinate bucket deletion via pytest hook. | |

**User's choice:** gw0 only — matches the established gw0-only teardown pattern (INFRA-05, D-05 from Phase 10). Only gw0 stops Docker and deletes resources.

**Notes:** `LambdaMock.clear()` is still safe on any worker — it only deletes S3 objects, not the bucket. The bucket itself is solely gw0's responsibility.

---

## Claude's Discretion

- Exact code structure of the xdist split inside `make_lambda_mock`'s inner `_make` function
- Whether to add `acquire_infra_lock()` for bucket creation (depends on already-locked `localstack_endpoint`)
- Error message wording in `pytest.fail()` for gw1+ timeout
- Whether to expose shared bucket name as single key or bundle mock state

## Deferred Ideas

None — discussion stayed within phase scope.

# TESTING
_Last updated: 2026-04-23_

## Summary
Testing is split into three isolated suites: unit tests (MagicMock, no Docker), integration tests (LocalStack only, no SAM), and end-to-end SAM+LocalStack tests. The 4-tier fixture scoping pattern (session client/resource → session factory → function bare noun) prevents test pollution while keeping Docker startup overhead to a minimum.

## Test Framework

- **Runner**: `pytest` ≥ 8.0
- **Containers**: `testcontainers[localstack]` — no standalone LocalStack process, no Docker Compose
- **HTTP client**: `requests` for REST API tests
- **Stubs**: `boto3-stubs[lambda,s3,dynamodb,sqs,sns]` for type-annotated boto3 clients
- **Timeout**: `pytest-timeout` with `--timeout=300` for integration/e2e tests

## Suite Structure

| Suite | Location | Docker needed | SAM needed | Run command |
|-------|----------|--------------|------------|-------------|
| Unit | `tests/unit/` | No | No | `uv run pytest tests/unit/` |
| Settings/Process/Plugin/Errors | `tests/test_settings.py` etc. | No | No | `uv run pytest tests/test_*.py` |
| Integration (LocalStack only) | `tests/integration/` | Yes (LocalStack) | No | `uv run pytest tests/integration/` |
| SAM e2e (hello_world) | `tests/test_sam_api.py` etc. | Yes (full) | Yes | `uv run pytest tests/` |
| Multi-Lambda mock | `tests/multi_lambda/` | Yes (full) | Yes | `uv run pytest tests/multi_lambda/` |

The multi_lambda suite **must be run in isolation** — its `samstack_settings` conflicts with the root conftest's hello_world settings. The root `conftest.py` blocks it via `pytest_ignore_collect` unless explicitly targeted.

## Fixture Scoping (4-tier pattern)

```
scope="session"  →  {service}_client, {service}_resource   (stateless, shared)
scope="session"  →  make_{service}_{resource}              (factory callable)
scope="function" →  {service}_{resource}                   (one fresh resource per test)
```

- **Session-scoped factories** (`make_s3_bucket`, `make_dynamodb_table`, etc.) register cleanup at session teardown — resources created during the session are deleted at the end
- **Function-scoped fixtures** (`s3_bucket`, `sqs_queue`, etc.) create one fresh resource per test to prevent test pollution
- UUID suffixes on resource names prevent collisions between parallel or repeated runs

## Unit Tests

Location: `tests/unit/`

- Test resource wrapper classes (`S3Bucket`, `DynamoTable`, `SqsQueue`, `SnsTopic`) with `MagicMock`
- Test `mock/types.py` (`Call`, `CallList`) in pure Python — no AWS calls
- Test `mock/handler.py` by mocking boto3 S3 client
- `MagicMock` parameters annotated as `MagicMock` (not the real boto3 type) — `ty` flags missing mock attributes on real types

## Integration Tests (LocalStack Only)

Location: `tests/integration/`

- Spin up LocalStack via testcontainers; no SAM containers
- Test all 15 resource fixtures (S3, DynamoDB, SQS, SNS) against real LocalStack
- Each test gets a fresh function-scoped resource; session-scoped LocalStack is shared

## SAM End-to-End Tests

Location: `tests/test_sam_api.py`, `tests/test_sam_build.py`, `tests/test_sam_lambda.py`, `tests/test_localstack_integration.py`

- Full stack: LocalStack + SAM build + SAM start-api/start-lambda
- `test_localstack_integration.py` tests Lambda → S3 (real LocalStack) round-trips via SAM API
- Uses `requests` to hit SAM API Gateway endpoints
- `lambda_client` fixture (boto3) for direct Lambda invocations

## Multi-Lambda Mock Tests

Location: `tests/multi_lambda/`

- Tests the `samstack.mock` spy pattern: Lambda A calls Mock B
- Session fixture `_mock_b_session` is `autouse=True` to ensure registration before `sam_build` writes `env_vars.json`
- Function-scoped `mock_b` fixture calls `_mock_b_session.clear()` for test isolation
- Exercises both HTTP (API Gateway) and boto3 `lambda.invoke` call paths

## Test Fixture Lambdas

**`tests/fixtures/hello_world/`**
- `src/handler.py`: GET `/hello` → 200, POST `/hello` → write to S3 → 201, direct invoke → 200
- `template.yaml`: declares env vars including `TEST_BUCKET`, `AWS_ENDPOINT_URL_S3`, etc.

**`tests/fixtures/multi_lambda/`**
- `src/lambda_a/handler.py`: forwards to Mock B via HTTP and boto3 invoke
- `tests/mocks/mock_b/handler.py`: inlines `spy_handler` body (avoids PyPI resolution during `sam build`)
- `template.test.yaml`: declares both `LambdaAFunction` and `MockBFunction`

## Key Testing Policies

- **Never mock boto3** — always use `testcontainers[localstack]` for AWS service calls in integration tests
- **Never mock boto3** in unit tests of wrapper classes either — use `MagicMock` on the client object itself
- LocalStack credentials always `"test"` / `"test"` (from `_constants.py`)
- Short timeouts in unit/process tests (2–5 s); integration/SAM tests use `--timeout=300`
- `sam build` does not depend on `localstack_container` — build runs independently

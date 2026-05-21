---
name: add-resource
description: Scaffold a new AWS resource wrapper for samstack following the established S3/DynamoDB/SQS/SNS pattern
---

Scaffold a complete new AWS resource integration for samstack.

## What to build

Given `SERVICE` (e.g. `secretsmanager`) and `RESOURCE_TYPE` (e.g. `secret`):

1. **`src/samstack/resources/{service}.py`** — wrapper class `{ResourceType}` with:
   - `__init__(self, name: str, client: ...Client)` storing both
   - Standard CRUD methods matching the service's boto3 API
   - `.name` and `.client` properties
   - Type annotations using boto3-stubs (`boto3-stubs[{service}]`)

2. **Add to `src/samstack/fixtures/resources.py`** — four fixtures following the exact pattern of `s3_bucket` / `make_s3_bucket` / `s3_client` / `s3_resource`:
   - `{service}_client` — `scope="session"` boto3 low-level client pointed at LocalStack
   - `{service}_resource` — `scope="session"` boto3 resource (only if boto3 has a resource API for this service; SNS has none — skip it and note why)
   - `make_{service}_{resource_type}` — `scope="session"` factory; UUID-suffixed names, teardown loop after `yield`
   - `{service}_{resource_type}` — `scope="function"` convenience fixture that calls the factory and yields

3. **Update `src/samstack/plugin.py`** — add re-export lines for all new fixtures (follow the existing `noqa: F401` underscore-prefix import pattern)

4. **Update `pyproject.toml`** — add `[{service}]` to the boto3-stubs extras in `[dependency-groups] dev`

## Reference patterns

- Wrapper template: `src/samstack/resources/s3.py` (simple CRUD) and `src/samstack/resources/dynamodb.py` (query/scan)
- Fixture template: the `s3_*` block in `src/samstack/fixtures/resources.py`
- Import credentials from `samstack._constants`: `LOCALSTACK_ACCESS_KEY`, `LOCALSTACK_SECRET_KEY` — never hardcode `"test"`
- UUID suffix pattern: `f"{name}-{uuid4().hex[:8]}"`
- Client constructor pattern:
  ```python
  boto3.client(
      "{service}",
      endpoint_url=localstack_endpoint,
      region_name=samstack_settings.aws_region,
      aws_access_key_id=LOCALSTACK_ACCESS_KEY,
      aws_secret_access_key=LOCALSTACK_SECRET_KEY,
  )
  ```

## After scaffolding

Run: `uv run ruff check . && uv run ruff format --check . && uv run ty check`

Then add a unit test in `tests/unit/test_{service}_{resource_type}.py` following the pattern in `tests/unit/test_s3_bucket.py`.

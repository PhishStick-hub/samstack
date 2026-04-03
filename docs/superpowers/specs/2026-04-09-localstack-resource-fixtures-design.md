# LocalStack Resource Fixtures Design

**Date:** 2026-04-09
**Status:** Approved

## Problem

Child projects using samstack must hand-roll boto3 client fixtures and resource creation/teardown for every AWS service they test against (S3 buckets, DynamoDB tables, SQS queues, etc.). This leads to duplicated boilerplate across projects and requires users to know low-level boto3 API details just to write test assertions.

## Solution

Add thin wrapper classes and pytest fixture factories for four AWS services: S3, DynamoDB, SQS, SNS. Each wrapper provides a simple, typed API for common operations while exposing the raw boto3 client for advanced use cases. Both session-scoped factories and function-scoped convenience fixtures are provided.

## Architecture

### Wrapper classes (`src/samstack/resources/`)

One module per service, each defining a single class:

| Class | Module | Identity | Key Methods |
|-------|--------|----------|-------------|
| `S3Bucket` | `s3.py` | `name: str` | `put`, `get`, `get_json`, `delete`, `list` |
| `DynamoTable` | `dynamodb.py` | `name: str` | `put_item`, `get_item`, `delete_item`, `query`, `scan` |
| `SqsQueue` | `sqs.py` | `url: str` | `send`, `receive`, `purge` |
| `SnsTopic` | `sns.py` | `arn: str` | `publish`, `subscribe_sqs` |

Design principles:
- Each class stores its identity (`_name`/`_url`/`_arn`) and a typed boto3 client (`_client`)
- `.client` read-only property exposes the raw boto3 client for escape-hatch access
- `.name`/`.url`/`.arn` read-only properties expose the resource identity
- `dict` arguments to `put`/`send`/`publish` are auto-serialized to JSON
- `str` arguments to S3 `put` are auto-encoded to UTF-8
- Full type annotations using `boto3-stubs` (`mypy_boto3_s3.S3Client`, etc.)
- `from __future__ import annotations` in every module
- boto3-stubs imports behind `TYPE_CHECKING` guard (dev-only dependency)

### API surface

```python
# S3Bucket
class S3Bucket:
    def __init__(self, name: str, client: S3Client) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def client(self) -> S3Client: ...
    def put(self, key: str, data: bytes | str | dict[str, Any]) -> None: ...
    def get(self, key: str) -> bytes: ...
    def get_json(self, key: str) -> Any: ...
    def delete(self, key: str) -> None: ...
    def list(self, prefix: str = "") -> list[str]: ...

# DynamoTable
class DynamoTable:
    def __init__(self, name: str, client: DynamoDBClient) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def client(self) -> DynamoDBClient: ...
    def put_item(self, item: dict[str, Any]) -> None: ...
    def get_item(self, key: dict[str, Any]) -> dict[str, Any] | None: ...
    def delete_item(self, key: dict[str, Any]) -> None: ...
    def query(self, key_condition: str, values: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]: ...
    def scan(self, **kwargs: Any) -> list[dict[str, Any]]: ...

# SqsQueue
class SqsQueue:
    def __init__(self, url: str, client: SQSClient) -> None: ...
    @property
    def url(self) -> str: ...
    @property
    def client(self) -> SQSClient: ...
    def send(self, body: str | dict[str, Any], **kwargs: Any) -> str: ...
    def receive(self, max_messages: int = 1, wait_seconds: int = 0) -> list[dict[str, Any]]: ...
    def purge(self) -> None: ...

# SnsTopic
class SnsTopic:
    def __init__(self, arn: str, client: SNSClient) -> None: ...
    @property
    def arn(self) -> str: ...
    @property
    def client(self) -> SNSClient: ...
    def publish(self, message: str | dict[str, Any], subject: str | None = None) -> str: ...
    def subscribe_sqs(self, queue_arn: str) -> str: ...
```

### Fixtures (`src/samstack/fixtures/resources.py`)

Three tiers per service:

**1. Session-scoped boto3 clients** (4 fixtures):
- `s3_client`, `dynamodb_client`, `sqs_client`, `sns_client`
- Depend on `localstack_endpoint` and `samstack_settings`
- Use `endpoint_url=localstack_endpoint`, `region_name=samstack_settings.region`, hardcoded `test`/`test` credentials

**2. Session-scoped factories** (4 fixtures):
- `s3_bucket_factory(name) -> S3Bucket`
- `dynamodb_table_factory(name, keys) -> DynamoTable` — first key HASH, second RANGE
- `sqs_queue_factory(name) -> SqsQueue`
- `sns_topic_factory(name) -> SnsTopic`
- All UUID-suffix resource names for isolation
- Teardown deletes all created resources (objects, then containers)

**3. Function-scoped convenience fixtures** (4 fixtures):
- `s3_bucket`, `dynamodb_table`, `sqs_queue`, `sns_topic`
- Fresh resource per test, cleaned up after
- `dynamodb_table` defaults to `{"id": "S"}` key schema

### Dependency chain

```
s3_client           -> localstack_endpoint, samstack_settings
dynamodb_client     -> localstack_endpoint, samstack_settings
sqs_client          -> localstack_endpoint, samstack_settings
sns_client          -> localstack_endpoint, samstack_settings
s3_bucket_factory   -> s3_client
s3_bucket           -> s3_client
(same pattern for all services)
```

### Plugin registration

`plugin.py` re-exports all 12 new fixtures (4 clients + 4 factories + 4 function-scoped) so child projects get them automatically. `resources/__init__.py` re-exports the 4 wrapper classes.

### Dependencies

Add to `[dependency-groups] dev` in `pyproject.toml`:
```
boto3-stubs[lambda,s3,dynamodb,sqs,sns]>=1.35.0
```

## File layout

```
src/samstack/
├── resources/
│   ├── __init__.py          # re-exports S3Bucket, DynamoTable, SqsQueue, SnsTopic
│   ├── s3.py
│   ├── dynamodb.py
│   ├── sqs.py
│   └── sns.py
├── fixtures/
│   ├── resources.py         # 12 new fixtures
│   └── ... (existing unchanged)
├── plugin.py                # updated with new re-exports
└── ... (existing unchanged)

tests/
├── unit/
│   ├── __init__.py
│   ├── test_s3_bucket.py
│   ├── test_dynamo_table.py
│   ├── test_sqs_queue.py
│   └── test_sns_topic.py
├── integration/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_s3_fixtures.py
│   ├── test_dynamodb_fixtures.py
│   ├── test_sqs_fixtures.py
│   └── test_sns_fixtures.py
└── ... (existing unchanged)
```

## Testing strategy

### Unit tests (no Docker)

Mock boto3 clients with `unittest.mock.create_autospec` against typed stubs. Test:
- Serialization: `dict` -> JSON, `str` -> UTF-8, `bytes` passthrough
- Delegation: correct boto3 method called with correct arguments
- Edge cases: missing items return `None`, empty lists, missing `Contents` key

### Integration tests (Docker required)

Real LocalStack via existing `localstack_container` fixture. Test:
- Factory creates real resources
- CRUD round-trip (put -> get -> verify)
- UUID isolation (two factories produce distinct names)
- Function-scoped fixture creates/destroys per test
- `.client` escape hatch works for raw boto3 calls
- Cross-service: SNS -> SQS subscription

### TDD order

Each service built completely before starting the next:
1. S3: unit tests (RED) -> wrapper (GREEN) -> integration tests (RED) -> fixtures (GREEN)
2. DynamoDB: same cycle
3. SQS: same cycle
4. SNS: same cycle
5. Final: update plugin.py, resources/__init__.py, verify all checks pass

# STRUCTURE
_Last updated: 2026-04-23_

## Summary
`samstack` is a single-package pytest plugin with a clear separation between library source (`src/samstack/`) and test infrastructure (`tests/`). The source is organized by concern — fixtures, resources, mock utilities, and internal utilities — each in its own subpackage or module.

## Directory Layout

```
samstack/
├── src/samstack/           # Installable library
│   ├── __init__.py         # Public re-exports (version, etc.)
│   ├── plugin.py           # pytest11 entry point — re-exports all fixtures
│   ├── settings.py         # SamStackSettings frozen dataclass + load_settings()
│   ├── _constants.py       # Shared constants (LocalStack credentials)
│   ├── _errors.py          # Exception hierarchy
│   ├── _process.py         # wait_for_port, wait_for_http, stream_logs_to_file, run_one_shot_container
│   ├── fixtures/
│   │   ├── __init__.py
│   │   ├── _sam_container.py   # Shared SAM container helpers (build_sam_args, create_sam_container, _run_sam_service)
│   │   ├── localstack.py       # docker_network, localstack_container, localstack_endpoint
│   │   ├── sam_api.py          # sam_build, sam_api, sam_api_extra_args
│   │   ├── sam_build.py        # sam_build fixture
│   │   ├── sam_lambda.py       # sam_lambda_endpoint, sam_lambda_extra_args, lambda_client
│   │   └── resources.py        # 15 AWS resource fixtures (S3/DynamoDB/SQS/SNS)
│   ├── resources/
│   │   ├── __init__.py
│   │   ├── s3.py           # S3Bucket wrapper
│   │   ├── dynamodb.py     # DynamoTable wrapper
│   │   ├── sqs.py          # SqsQueue wrapper
│   │   └── sns.py          # SnsTopic wrapper
│   └── mock/
│       ├── __init__.py     # Public exports: spy_handler, Call, CallList, LambdaMock, make_lambda_mock
│       ├── handler.py      # spy_handler Lambda entry point (stdlib + boto3 only)
│       ├── types.py        # Call, CallList frozen dataclasses
│       └── fixture.py      # make_lambda_mock session factory fixture
├── tests/
│   ├── conftest.py         # Root: samstack_settings for hello_world, blocks multi_lambda
│   ├── fixtures/
│   │   ├── hello_world/    # Single Lambda test fixture (GET/POST /hello)
│   │   └── multi_lambda/   # Two-Lambda mock spy test fixture
│   ├── unit/               # Unit tests (no Docker); mock boto3 with MagicMock
│   ├── integration/        # LocalStack-only tests (no SAM); separate conftest
│   └── multi_lambda/       # End-to-end multi-Lambda tests; isolated session
├── pyproject.toml
└── CLAUDE.md
```

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `plugin.py` | pytest11 entry point; re-exports all fixtures so child projects get them automatically |
| `settings.py` | Configuration parsing from `[tool.samstack]` in pyproject.toml; frozen dataclass |
| `_constants.py` | `LOCALSTACK_ACCESS_KEY` / `LOCALSTACK_SECRET_KEY` — single definition, no per-module re-declaration |
| `_errors.py` | `SamStackError` hierarchy: `SamBuildError`, `SamStartupError`, `LocalStackStartupError`, `DockerNetworkError` |
| `_process.py` | Low-level Docker process utilities; `wait_for_port`, `wait_for_http`, `stream_logs_to_file`, `run_one_shot_container` |
| `fixtures/_sam_container.py` | Shared SAM container lifecycle: arg building, container creation, network alias wiring, `_run_sam_service` context manager |
| `fixtures/localstack.py` | Network + LocalStack container lifecycle |
| `fixtures/resources.py` | 15 AWS resource fixtures (4 per S3/DynamoDB/SQS, 3 for SNS) |
| `resources/*.py` | Thin boto3 wrappers (`S3Bucket`, `DynamoTable`, `SqsQueue`, `SnsTopic`) |
| `mock/handler.py` | Lambda spy handler; stdlib + boto3 only (no samstack import) |
| `mock/types.py` | `Call` + `CallList` with `.one`, `.last`, `.matching()` assertion API |
| `mock/fixture.py` | `make_lambda_mock` session-scoped factory |

## Naming Conventions

- Internal modules prefixed with `_` (e.g., `_errors.py`, `_process.py`, `_constants.py`, `_sam_container.py`)
- Fixture factories named `make_{service}_{resource_type}` (e.g., `make_s3_bucket`, `make_dynamodb_table`)
- Function-scoped convenience fixtures named as bare nouns (e.g., `s3_bucket`, `sqs_queue`)
- Session-scoped clients/resources named `{service}_client` / `{service}_resource`
- `noqa: F401` used on `__init__.py` re-exports to suppress unused import warnings

## Test Suite Organization

Three isolated test suites, each with its own `conftest.py` and `samstack_settings` fixture:

1. **Root tests** (`tests/test_*.py`) — unit + integration tests for the library itself, using `hello_world` fixture
2. **`tests/integration/`** — LocalStack-only resource fixture tests (no SAM containers)
3. **`tests/multi_lambda/`** — end-to-end multi-Lambda mock spy tests; must be run in isolation via `uv run pytest tests/multi_lambda/`

The root `conftest.py` uses `pytest_ignore_collect` to block `multi_lambda/` from being collected in the default session (conflicting `samstack_settings` would poison session-scoped SAM fixtures).

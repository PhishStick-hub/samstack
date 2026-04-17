# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`samstack` is a pytest plugin library (registered via `pytest11` entry point) that provides session-scoped fixtures for testing AWS Lambda functions locally. It runs SAM CLI and Lambda containers entirely inside Docker — no host `sam` install required. LocalStack provides the local AWS backend.

## Commands

```bash
# Install deps (including dev)
uv sync

# Lint
uv run ruff check .

# Format check (CI-safe)
uv run ruff format --check .

# Auto-fix formatting
uv run ruff format .

# Type check
uv run ty check

# All checks at once
uv run ruff check . && uv run ruff format --check . && uv run ty check

# Unit tests only (no Docker required)
uv run pytest tests/unit/ tests/test_settings.py tests/test_process.py tests/test_errors.py -v

# Single test
uv run pytest tests/test_settings.py::test_defaults_applied -v

# Full integration tests (requires Docker, pulls images on first run)
uv run pytest tests/ -v --timeout=300
```

## Architecture

### Type checking gotchas

`ty` does **not** support `# type: ignore[...]` (mypy-only). Prefer refactoring over escape hatches; avoid `cast()` as a generic workaround. In unit test files, annotate mock parameters as `MagicMock` — annotating them as the real boto3 type causes ty to flag missing mock attributes.

### LocalStack resource fixtures

`src/samstack/fixtures/resources.py` provides 15 fixtures for S3, DynamoDB, SQS, and SNS. S3, DynamoDB, and SQS each have four fixtures; SNS has three (no boto3 resource API):

- `{service}_client` — session-scoped boto3 low-level client pointed at LocalStack
- `{service}_resource` — session-scoped boto3 resource object (S3, DynamoDB, SQS only; SNS has no resource API)
- `make_{service}_{resource_type}` — session-scoped factory; call it with a name (and `keys` dict for DynamoDB) to get a wrapper instance with UUID suffix; all resources deleted at session teardown
- `{service}_{resource_type}` — function-scoped convenience fixture; one fresh resource per test, deleted after

Wrapper classes live in `src/samstack/resources/`:
- `S3Bucket` — `put(key, data)`, `get(key)`, `get_json(key)`, `delete(key)`, `list_keys(prefix)`, `.name`, `.client`
- `DynamoTable` — `put_item(item)`, `get_item(key)`, `delete_item(key)`, `query(key_condition, **kw)`, `scan()`, `.name`, `.client`
- `SqsQueue` — `send(body, **kw)`, `receive(max=10, wait=1)`, `purge()`, `.url`, `.client`
- `SnsTopic` — `publish(message, subject=None)`, `subscribe_sqs(queue_arn)`, `.arn`, `.client`

`DynamoTable` wraps `boto3.resource('dynamodb').Table` (high-level resource API) — item values are plain Python types, not `AttributeValueTypeDef` maps. `dynamodb_resource` is a public session fixture for external use. `s3_resource` and `sqs_resource` provide session-scoped boto3 resource objects for the same purpose. The pattern: use wrappers (`S3Bucket`, `SqsQueue`, `DynamoTable`) for setup and manipulation; use resource fixtures (`s3_resource`, `sqs_resource`, `dynamodb_resource`) to construct boto3 resource instances for assertions.

### Fixture dependency chain

All fixtures are `scope="session"` unless noted. The dependency graph is:

```
samstack_settings            (no deps)
docker_network               (no deps)
sam_env_vars                 → samstack_settings
localstack_container         → samstack_settings, docker_network
localstack_endpoint          → localstack_container
sam_build                    → samstack_settings, sam_env_vars
sam_api                      → samstack_settings, sam_build, docker_network, sam_api_extra_args
sam_lambda_endpoint          → samstack_settings, sam_build, docker_network, sam_lambda_extra_args
lambda_client                → samstack_settings, sam_lambda_endpoint

# Resource fixtures (all depend on localstack_endpoint + samstack_settings)
s3_client                    → localstack_endpoint, samstack_settings
s3_resource                  → localstack_endpoint, samstack_settings
make_s3_bucket            → s3_client
s3_bucket          [func]    → s3_client
dynamodb_client              → localstack_endpoint, samstack_settings
dynamodb_resource            → localstack_endpoint, samstack_settings
make_dynamodb_table       → dynamodb_client, dynamodb_resource
dynamodb_table     [func]    → dynamodb_client, dynamodb_resource
sqs_client                   → localstack_endpoint, samstack_settings
sqs_resource                 → localstack_endpoint, samstack_settings
make_sqs_queue            → sqs_client
sqs_queue          [func]    → sqs_client
sns_client                   → localstack_endpoint, samstack_settings
make_sns_topic            → sns_client
sns_topic          [func]    → sns_client
```

`sam_build` intentionally does not depend on `localstack_container` — the build step doesn't need LocalStack running. The network dependency is implicit: `sam_api` and `sam_lambda_endpoint` bring in `docker_network`, which ensures network exists before SAM containers start.

### How Docker networking works

1. `docker_network` creates a named Docker bridge network (`samstack-{uuid8}`)
2. `localstack_container` starts LocalStack, then connects it to that network with alias `localstack`
3. SAM containers (start-api, start-lambda) are connected **after** `.start()` via `_connect_container_with_alias` (see `fixtures/_sam_container.py`) with DNS aliases `sam-api` / `sam-lambda`. Aliases matter: Lambda A running inside a SAM-spawned container resolves `sam-lambda` reliably on Linux, where `host.docker.internal` is not available by default for SAM-spawned Lambda containers.
4. Lambda code inside SAM reaches LocalStack at `http://localstack:4566` and the local Lambda runtime at `http://sam-lambda:3001` — injected as per-service `AWS_ENDPOINT_URL_<SERVICE>` variables (boto3 ≥ 1.28 picks these up automatically).

### Per-service endpoint env vars (breaking change in 0.3.0)

`sam_env_vars` no longer emits a global `AWS_ENDPOINT_URL`. It sets:
- `AWS_ENDPOINT_URL_S3`, `AWS_ENDPOINT_URL_DYNAMODB`, `AWS_ENDPOINT_URL_SQS`, `AWS_ENDPOINT_URL_SNS` → LocalStack
- `AWS_ENDPOINT_URL_LAMBDA` → `http://sam-lambda:{settings.lambda_port}`

This lets Lambda-to-Lambda `boto3.client("lambda").invoke(...)` calls reach the SAM local-lambda runtime instead of LocalStack — a prerequisite for the `samstack.mock` use case. Lambda code consuming these env vars needs no `endpoint_url=` kwarg: boto3 auto-reads them.

**SAM env-var propagation gotcha**: `sam local` only delivers env vars to a Lambda container that are **declared on the function** (`Environment.Variables` in the template, either on the function directly or on `Globals.Function`). `--env-vars` JSON (both `Parameters` and per-function sections) is treated as *overrides* for already-declared keys — **undeclared keys are silently dropped**. Templates that want to receive `AWS_ENDPOINT_URL_S3`, `AWS_ENDPOINT_URL_LAMBDA`, `MOCK_SPY_BUCKET`, etc. at runtime must declare them (empty string is fine) in `Environment.Variables`. See `tests/fixtures/hello_world/template.yaml` and `tests/fixtures/multi_lambda/template.test.yaml` for the pattern.

### SAM containers

Both `sam_api` and `sam_lambda_endpoint` use `testcontainers.core.container.DockerContainer`. The SAM image runs the CLI inside Docker (not on the host). Volume mounts:
- `{project_root}` → `{project_root}` (real host path — **not** `/var/task`)
- `/var/run/docker.sock` → `/var/run/docker.sock` (Docker-in-Docker for Lambda containers)

The project is mounted at its **real host path** (not `/var/task`) so that Lambda containers created by SAM via the Docker socket receive volume paths that Docker Desktop can resolve. The SAM container's `working_dir` is also set to this host path.

Default CLI flags on both commands: `--skip-pull-image --warm-containers LAZY --host 0.0.0.0 --port {port} --env-vars {host_path}/{log_dir}/env_vars.json --docker-network {network} --container-host host.docker.internal --container-host-interface 0.0.0.0`

- `--host 0.0.0.0` — bind Flask inside the container on all interfaces so Docker port-mapping works
- `--docker-network` — puts Lambda containers on the same network so they can reach LocalStack
- `--container-host host.docker.internal` — tells SAM to reach Lambda containers via Docker Desktop's host gateway (required when SAM runs inside Docker on macOS)
- `--container-host-interface 0.0.0.0` — binds Lambda container ports on all interfaces

`sam_api` uses `wait_for_http` (not `wait_for_port`) to wait for Flask to be ready. Docker Desktop's port forwarder starts listening before Flask binds the port, so a TCP-only probe would succeed too early and result in connection resets.

The `env_vars.json` file is written to `{project_root}/{log_dir}/` by `sam_build`. The host path is passed directly to `--env-vars` since the project is mounted at its real path.

### Plugin registration

`plugin.py` is the `pytest11` entry point. It re-exports all fixtures from the four `fixtures/` modules so pytest discovers them automatically — child projects get all fixtures without any imports. `samstack_settings` is defined directly in `plugin.py` and searches upward from `Path.cwd()` for `pyproject.toml`.

### Settings

`SamStackSettings` is a **frozen** dataclass parsed from `[tool.samstack]` in the child project's `pyproject.toml`. `sam_image` is the only required field (no default). Has a `docker_platform` property (`linux/arm64` / `linux/amd64`). Child projects override `samstack_settings` fixture in their `conftest.py` to supply settings programmatically, which is how the library's own tests work (see `tests/conftest.py`).

### Overridable fixtures

These fixtures exist specifically to be overridden in child `conftest.py`:
- `samstack_settings` — swap the entire config
- `sam_env_vars` — extend or replace Lambda runtime env vars (dict is mutable; mutate it directly as shown in `tests/conftest.py`)
- `sam_api_extra_args` / `sam_lambda_extra_args` — append extra CLI flags
- `localstack_container`, `docker_network`, `localstack_endpoint` — swap infrastructure

### Test fixture Lambdas

`tests/fixtures/hello_world/` — single Lambda + `template.yaml` exercised by `tests/test_sam_api.py`, `tests/test_sam_lambda.py`, and `tests/test_sam_build.py`. Handler: GET `/hello` → 200, POST `/hello` → write to S3 → 201, direct invoke → 200.

`tests/fixtures/multi_lambda/` — two Lambdas exercising the `samstack.mock` flow. `template.test.yaml` declares `LambdaAFunction` (real, under `src/lambda_a/`) and `MockBFunction` (test-only spy, under `tests/mocks/mock_b/`). Lambda A forwards requests to Mock B via both HTTP (through API Gateway at `/mock-b/{proxy+}`) and boto3 `lambda_client.invoke`. `tests/mocks/mock_b/handler.py` inlines the body of `samstack.mock.spy_handler` — real user projects use the 2-line `from samstack.mock import spy_handler as handler` form with `samstack` in their mock's `requirements.txt`; the fixture inlines the logic so `sam build` doesn't need to resolve the library via PyPI during the repo's own tests.

Run multi_lambda integration suite in isolation (separate pytest session — its `samstack_settings` conflicts with the root `tests/conftest.py`): `uv run pytest tests/multi_lambda/ -v --timeout=300`.

### `samstack.mock` module

Public surface:
- `samstack.mock.spy_handler(event, context)` — Lambda-side handler; depends only on stdlib + boto3. Writes each event to `s3://{MOCK_SPY_BUCKET}/spy/{MOCK_FUNCTION_NAME}/<ts>-<uuid>.json`. Reads queued responses from `mock-responses/{name}/queue.json` (JSON list — pop head, write back remainder).
- `samstack.mock.Call` / `CallList` — frozen dataclass + sequence wrapper with `.one` / `.last` / `.matching(**filters)` assertion helpers (avoids index-based assertions).
- `samstack.mock.LambdaMock` — test-side handle: `.calls`, `.clear()`, `.next_response(resp)`, `.response_queue([resp, ...])`.
- `samstack.mock.make_lambda_mock` — session-scoped factory fixture (re-exported from `plugin.py`). Creates a spy bucket (or reuses one) and mutates `sam_env_vars[function_name]` to inject `MOCK_SPY_BUCKET`, `MOCK_FUNCTION_NAME`, `AWS_ENDPOINT_URL_S3`. Must be resolved **before** `sam_build` runs.

User pattern: session fixture calls `make_lambda_mock(...)`, function-scoped wrapper calls `.clear()` before yielding — gives parametrize-safe isolation without re-creating the bucket.

### `_process.py` utilities

- `wait_for_port` — TCP probe loop; raises `SamStartupError` with log tail on timeout
- `wait_for_http` — HTTP probe loop (any HTTP response = ready); used by `sam_api` because Docker Desktop's port forwarder accepts TCP before Flask starts, making a TCP-only probe succeed too early
- `stream_logs_to_file(container, log_path)` — daemon thread streaming container logs; accepts a Docker SDK container object (not an ID string)
- `run_one_shot_container` — runs a container to completion (used for `sam build`), returns `(logs, exit_code)`

`fixtures/_sam_container.py` — shared helpers for `sam_api` and `sam_lambda`: `build_sam_args()` (CLI arg list), `create_sam_container()` (container builder — intentionally does **not** pre-attach to `docker_network`; caller attaches with an alias after `.start()`), `_connect_container_with_alias()` / `_disconnect_container()` (network alias wiring, mirrors `localstack.py`), `_run_sam_service()` (context manager — starts container, attaches with alias, streams logs, waits for readiness, yields endpoint URL, disconnects + stops on exit), `DOCKER_SOCKET` constant. The `network_alias` parameter is mandatory on `_run_sam_service` — pass `"sam-api"` or `"sam-lambda"` to match the convention other containers rely on.

`_constants.py` — internal constants shared across fixtures: `LOCALSTACK_ACCESS_KEY` / `LOCALSTACK_SECRET_KEY` (both `"test"` — LocalStack's documented default). Import from here; do not re-define per-module.

Docker SDK (`import docker`) is imported lazily in `run_one_shot_container` to avoid import-time failures if Docker is not available.

### Architecture and cross-platform support

`SamStackSettings` has an `architecture` field (`arm64` or `x86_64`) auto-detected from `platform.machine()`. This sets `DOCKER_DEFAULT_PLATFORM` (`linux/arm64` / `linux/amd64`) on SAM and build containers so the correct Lambda emulation image is pulled.

On Linux, `host.docker.internal` is not available by default. The fixtures add `--add-host host.docker.internal:host-gateway` to SAM containers on non-Darwin platforms.

### Lambda container cleanup

SAM creates Lambda runtime containers (via the Docker socket) on `docker_network`. These are not tracked by testcontainers/Ryuk. The `docker_network` fixture teardown stops and removes all containers still connected to the network before destroying it.

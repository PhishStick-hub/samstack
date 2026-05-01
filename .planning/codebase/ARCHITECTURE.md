# Architecture

_Last updated: 2026-04-23_

## Summary

`samstack` is a pytest plugin library that provides session-scoped fixtures for testing AWS Lambda functions locally. It runs SAM CLI and Lambda containers entirely inside Docker using testcontainers, with LocalStack providing the local AWS backend. The plugin registers all fixtures automatically via the `pytest11` entry point — consuming projects need zero imports.

## Pattern Overview

**Overall:** Layered pytest plugin with fixture dependency injection

**Key Characteristics:**
- All infrastructure fixtures are `scope="session"` — containers start once per test run
- Resource fixtures (`s3_bucket`, `dynamodb_table`, etc.) are `scope="function"` — fresh per test
- Fixture overriding is the primary extension mechanism — child projects override `samstack_settings`, `sam_env_vars`, etc. in their `conftest.py`
- Docker-in-Docker: the SAM container spawns Lambda runtime containers via the host Docker socket mounted at `/var/run/docker.sock`
- All containers share a single named Docker bridge network (`samstack-{uuid8}`) so DNS aliases (`localstack`, `sam-api`, `sam-lambda`) work between containers

## Layers

**Settings Layer:**
- Purpose: Load and validate configuration from `[tool.samstack]` in `pyproject.toml`
- Location: `src/samstack/settings.py`
- Contains: Frozen `SamStackSettings` dataclass, `load_settings()` parser, architecture auto-detection
- Depends on: stdlib only (`tomllib`, `platform`, `dataclasses`)
- Used by: Every fixture that needs config (injected as `samstack_settings` fixture)

**Infrastructure Fixtures Layer:**
- Purpose: Start and manage Docker containers (LocalStack, Docker network, SAM processes)
- Location: `src/samstack/fixtures/localstack.py`, `src/samstack/fixtures/sam_build.py`, `src/samstack/fixtures/sam_api.py`, `src/samstack/fixtures/sam_lambda.py`
- Contains: Session-scoped fixtures that start/stop containers as context managers
- Depends on: `settings`, `_process`, `_sam_container`, `_errors`
- Used by: Resource fixtures, test code via `sam_api` / `lambda_client`

**SAM Container Helpers Layer:**
- Purpose: Shared logic for building and running `sam local start-*` containers
- Location: `src/samstack/fixtures/_sam_container.py`
- Contains: `build_sam_args()`, `create_sam_container()`, `_run_sam_service()` (context manager), `_connect_container_with_alias()`, `_disconnect_container_from_network()`, `DOCKER_SOCKET` constant
- Depends on: Docker SDK, testcontainers, `_errors`, `_process`, `settings`
- Used by: `sam_api.py`, `sam_lambda.py`, `localstack.py`

**Resource Wrapper Layer:**
- Purpose: Thin, test-ergonomic wrappers around raw boto3 clients/resources
- Location: `src/samstack/resources/s3.py`, `src/samstack/resources/dynamodb.py`, `src/samstack/resources/sqs.py`, `src/samstack/resources/sns.py`
- Contains: `S3Bucket`, `DynamoTable`, `SqsQueue`, `SnsTopic` classes — plain Python API over boto3
- Depends on: boto3 (type annotations only via `TYPE_CHECKING`)
- Used by: Resource fixtures in `fixtures/resources.py`, `mock/fixture.py`

**Resource Fixtures Layer:**
- Purpose: Create/delete AWS resources via LocalStack for test isolation
- Location: `src/samstack/fixtures/resources.py`
- Contains: 15 fixtures across S3, DynamoDB, SQS, SNS — clients, resources, factory fixtures, function-scoped convenience fixtures
- Depends on: `localstack_endpoint`, `samstack_settings`, resource wrapper classes
- Used by: Test code in consuming projects

**Mock Lambda Layer:**
- Purpose: Allow Lambda functions to be replaced with call-recording spy stubs during testing
- Location: `src/samstack/mock/handler.py`, `src/samstack/mock/fixture.py`, `src/samstack/mock/types.py`
- Contains: `spy_handler` (Lambda-side), `LambdaMock` + `make_lambda_mock` (test-side), `Call`/`CallList` types
- Depends on: `resources/s3.py` (fixture side), stdlib + boto3 only (handler side — must run inside Lambda container)
- Used by: Test suites using mock Lambda pattern

**Plugin Entry Point:**
- Purpose: Register all fixtures with pytest automatically
- Location: `src/samstack/plugin.py`
- Contains: Re-exports all fixtures from all four fixture modules, `samstack_settings` fixture, `_find_settings()` helper
- Depends on: All fixture modules, `settings`
- Used by: pytest (via `pytest11` entry point in `pyproject.toml`)

## Fixture Dependency Chain

All fixtures are `scope="session"` unless marked `[func]`:

```
samstack_settings            (no deps — reads pyproject.toml upward from cwd)
docker_network_name          (no deps — generates uuid-based name)
docker_network               → docker_network_name
sam_env_vars                 → samstack_settings
localstack_container         → samstack_settings, docker_network
localstack_endpoint          → localstack_container
sam_build                    → samstack_settings, sam_env_vars
sam_api                      → samstack_settings, sam_build, docker_network, sam_api_extra_args
sam_api_extra_args           (no deps — returns [])
sam_lambda_endpoint          → samstack_settings, sam_build, docker_network, sam_lambda_extra_args
sam_lambda_extra_args        (no deps — returns [])
lambda_client                → samstack_settings, sam_lambda_endpoint

# Resource fixtures (all depend on localstack_endpoint + samstack_settings)
s3_client                    → localstack_endpoint, samstack_settings
s3_resource                  → localstack_endpoint, samstack_settings
make_s3_bucket               → s3_client
s3_bucket          [func]    → s3_client
dynamodb_client              → localstack_endpoint, samstack_settings
dynamodb_resource            → localstack_endpoint, samstack_settings
make_dynamodb_table          → dynamodb_client, dynamodb_resource
dynamodb_table     [func]    → dynamodb_client, dynamodb_resource
sqs_client                   → localstack_endpoint, samstack_settings
sqs_resource                 → localstack_endpoint, samstack_settings
make_sqs_queue               → sqs_client
sqs_queue          [func]    → sqs_client
sns_client                   → localstack_endpoint, samstack_settings
make_sns_topic               → sns_client
sns_topic          [func]    → sns_client

# Mock fixtures
make_lambda_mock             → make_s3_bucket, sam_env_vars
```

**Critical ordering constraint:** `make_lambda_mock` must be resolved before `sam_build` runs. `sam_build` writes `env_vars.json` — any mock's env vars injected into `sam_env_vars` after that point will be silently ignored. The pattern: use `autouse=True` on a session fixture that calls `make_lambda_mock`.

**`sam_build` intentionally does not depend on `localstack_container`** — the build step does not need LocalStack running.

## Data Flow

**HTTP Lambda invocation via API Gateway:**
1. Test calls `requests.get(sam_api + "/path")`
2. `sam_api` endpoint → SAM Flask container (port-mapped to host) → Lambda runtime container
3. Lambda code executes; boto3 calls read `AWS_ENDPOINT_URL_*` env vars → LocalStack at `http://localstack:4566`
4. Response returns through SAM → test assertion

**Direct Lambda invocation:**
1. Test calls `lambda_client.invoke(FunctionName="Fn", Payload=b"{}")`
2. `lambda_client` → SAM local-lambda endpoint (port-mapped to host) → Lambda runtime container
3. Lambda code executes
4. Response returned as `Payload` in invoke response

**Mock Lambda spy flow:**
1. Lambda A invokes Lambda B via boto3 (`AWS_ENDPOINT_URL_LAMBDA` points to `sam-lambda`)
2. Mock B (`spy_handler`) writes normalized event to `s3://spy-bucket/spy/<alias>/<ts>.json`
3. Mock B pops and returns a queued response from `s3://spy-bucket/mock-responses/<alias>/queue.json` or returns default
4. Test reads `mock_b.calls` — fetches all spy objects from S3, deserializes into `CallList`

**Docker networking:**
1. `docker_network` creates bridge network `samstack-{uuid8}`
2. `localstack_container` starts, then connects with alias `localstack`
3. SAM containers start via `_run_sam_service`, then connect with alias `sam-api` or `sam-lambda`
4. Lambda code inside SAM containers reaches LocalStack via `http://localstack:4566`
5. Lambda-to-Lambda calls reach `http://sam-lambda:3001`
6. On teardown: `docker_network` fixture stops all containers still on the network before removing it

## Key Abstractions

**`SamStackSettings` (frozen dataclass):**
- Purpose: Single source of truth for all configuration — paths, ports, images, architecture
- Location: `src/samstack/settings.py`
- Pattern: Frozen dataclass; override the `samstack_settings` fixture in child `conftest.py` to supply programmatically

**Resource Wrappers (`S3Bucket`, `DynamoTable`, `SqsQueue`, `SnsTopic`):**
- Purpose: Ergonomic test API that hides boto3 verbosity — plain Python types in/out
- Location: `src/samstack/resources/`
- Pattern: `__init__(name/url/arn, client)` — wraps a pre-created AWS resource

**Factory Fixtures (`make_s3_bucket`, `make_dynamodb_table`, `make_sqs_queue`, `make_sns_topic`):**
- Purpose: Session-scoped callables that create uniquely named resources with automatic teardown
- Pattern: `yield callable` — callable appends to `created` list; teardown iterates and deletes all

**`LambdaMock`:**
- Purpose: Test-side handle to inspect captured calls and queue canned responses
- Location: `src/samstack/mock/fixture.py`
- Pattern: Session fixture creates it; function-scoped wrapper calls `.clear()` before each test

**`_run_sam_service` (context manager):**
- Purpose: Encapsulate full SAM container lifecycle — start, attach to network, wait for ready, yield URL, disconnect, stop
- Location: `src/samstack/fixtures/_sam_container.py`
- Used by: `sam_api` and `sam_lambda_endpoint` fixtures

## Entry Points

**pytest plugin registration:**
- Location: `src/samstack/plugin.py`
- Triggers: pytest discovers via `[project.entry-points."pytest11"]` in `pyproject.toml`
- Responsibilities: Re-export all fixtures so pytest finds them without any user imports

**`samstack_settings` fixture:**
- Location: `src/samstack/plugin.py`
- Triggers: First fixture in the dependency chain to run
- Responsibilities: Search upward from `cwd` for `pyproject.toml`, parse `[tool.samstack]`

**`sam_build` fixture:**
- Location: `src/samstack/fixtures/sam_build.py`
- Triggers: First time `sam_api` or `sam_lambda_endpoint` is requested
- Responsibilities: Write `env_vars.json`, run `sam build` in a one-shot container

## Error Handling

**Strategy:** Domain-specific exceptions raised at fixture setup time; teardown errors demoted to `warnings.warn`

**Hierarchy (`src/samstack/_errors.py`):**
- `SamStackError` — base
- `SamBuildError` — `sam build` container exited non-zero; includes full build logs
- `SamStartupError` — SAM process did not bind port within timeout (120 s); includes log tail
- `LocalStackStartupError` — LocalStack container did not become healthy; includes log tail
- `DockerNetworkError` — failed to create or attach the shared Docker bridge network

**Teardown resilience:** All `_teardown_network`, `_stop_network_container`, disconnect calls are wrapped in `try/except → warnings.warn`. Teardown failures never mask test failures.

## Cross-Cutting Concerns

**Logging:** Container stdout/stderr streamed to `{project_root}/{log_dir}/` via daemon threads (`stream_logs_to_file` in `src/samstack/_process.py`). Log files: `localstack.log`, `start-api.log`, `start-lambda.log`.

**Validation:** `load_settings()` validates `sam_image` is present and `architecture` is a known value. SAM template env var propagation requires keys to be declared in `template.yaml` `Environment.Variables` — undeclared keys injected via `--env-vars` are silently dropped by SAM.

**Authentication:** LocalStack accepts any credentials; fixtures use `"test"/"test"` (defined in `src/samstack/_constants.py` as `LOCALSTACK_ACCESS_KEY`/`LOCALSTACK_SECRET_KEY`). Never configurable — LocalStack's documented default.

**Cross-platform:** `_extra_hosts()` in `_sam_container.py` adds `host.docker.internal:host-gateway` on non-Darwin (Linux CI). Architecture auto-detected from `platform.machine()` → sets `DOCKER_DEFAULT_PLATFORM` on all containers.

**CI vs local:** `_is_ci()` (checks `CI` env var) controls `--skip-pull-image` — omitted in CI to pull fresh images; added locally to speed up reruns.

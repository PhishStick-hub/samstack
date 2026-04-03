# samstack — Design Spec

**Date:** 2026-04-03
**Status:** Approved

---

## Overview

`samstack` is a pytest plugin library that provides reusable fixtures for testing AWS Lambda functions locally using AWS SAM CLI (running in Docker) and LocalStack (via testcontainers). Child projects import it as a dev dependency and configure it via `[tool.samstack]` in their `pyproject.toml`.

---

## Goals

- Run `sam local start-api` and `sam local start-lambda` in Docker (no host SAM install required)
- Provide LocalStack as the local AWS backend via testcontainers
- SAM Lambda containers communicate with LocalStack over a shared Docker network
- Support environment variable injection into Lambda runtime (`--env-vars`)
- Support CLI argument overrides for SAM commands via fixtures and `pyproject.toml`
- Log SAM output to files; tail logs in error messages
- Crossplatform: works on Linux, macOS, Windows (Docker Desktop WSL2 backend)
- Scalable: any project with a `template.yaml` can adopt it in 3 steps

---

## Architecture

### Project Structure

```
samstack/
├── pyproject.toml
├── src/samstack/
│   ├── __init__.py              # re-exports public fixtures
│   ├── plugin.py                # pytest plugin entry point, reads pyproject.toml
│   ├── settings.py              # SamStackSettings dataclass
│   ├── fixtures/
│   │   ├── localstack.py        # LocalStack container + Docker network
│   │   ├── sam_build.py         # sam build (session-scoped, one-shot container)
│   │   ├── sam_api.py           # sam local start-api (long-running container)
│   │   └── sam_lambda.py        # sam local start-lambda (long-running container)
│   └── _process.py              # container lifecycle helpers, readiness probing
└── tests/
    ├── fixtures/
    │   └── hello_world/
    │       ├── template.yaml    # minimal SAM template (one Lambda + API Gateway)
    │       └── src/handler.py   # returns {"statusCode": 200, "body": "hello"}
    ├── conftest.py
    ├── test_sam_build.py
    ├── test_sam_api.py
    ├── test_sam_lambda.py
    └── test_localstack_integration.py
```

### Runtime Topology

```
Docker network: samstack-{session-id}
├── localstack container          internal hostname: localstack, port 4566
├── sam-api container             long-running, host port → api_port (default 3000)
└── sam-lambda container          long-running, host port → lambda_port (default 3001)
    └── Lambda containers         spun up by SAM via mounted Docker socket
```

All containers share one Docker bridge network. SAM Lambda containers reach LocalStack via `http://localstack:4566`. The library injects this as `AWS_ENDPOINT_URL` into the Lambda runtime automatically.

### Docker-in-Docker

SAM containers require Docker access to spin up Lambda containers. The Docker socket is mounted into every SAM container:

| Host path | Container path | Purpose |
|---|---|---|
| `{project_root}` | `/var/task` | Lambda source + `template.yaml` |
| `{project_root}/.aws-sam` | `/var/task/.aws-sam` | SAM build cache |
| `/var/run/docker.sock` | `/var/run/docker.sock` | Docker-in-Docker |

On Windows (Docker Desktop WSL2), the socket path is the same — no platform branching required.

---

## Configuration

### `pyproject.toml` in child project

```toml
[tool.samstack]
template = "template.yaml"                          # default: "template.yaml"
region = "us-east-1"                                # default: "us-east-1"
api_port = 3000                                     # default: 3000
lambda_port = 3001                                  # default: 3001
sam_image = "public.ecr.aws/sam/build-python3.13"  # required, no global default
localstack_image = "localstack/localstack:4"        # default: "localstack/localstack:4"
log_dir = "logs/sam"                                # default: "logs/sam" (relative to project root)
build_args = []                                     # extra args appended to sam build
add_gitignore = true                                # auto-add logs/sam/ to .gitignore

[tool.samstack.start_api_args]                      # extra flags merged with defaults for start-api
[tool.samstack.start_lambda_args]                   # extra flags merged with defaults for start-lambda
```

### `SamStackSettings` dataclass (`settings.py`)

Parsed from `pyproject.toml` at session start by `plugin.py`. Exposed as the `samstack_settings` fixture. All fields have defaults except `sam_image`.

---

## Fixtures

### Fixture Table

| Fixture | Scope | Returns | Override to... |
|---|---|---|---|
| `samstack_settings` | session | `SamStackSettings` | swap full config |
| `localstack_container` | session | `LocalStackContainer` | use custom image/ports |
| `docker_network` | session | `str` (network name) | use existing named network |
| `localstack_endpoint` | session | `str` (URL) | point at remote LocalStack |
| `sam_env_vars` | session | `dict[str, dict]` | add Lambda-specific env vars |
| `sam_build` | session | `None` (side-effect) | skip build or add flags |
| `sam_api_extra_args` | session | `list[str]` | override start-api CLI args |
| `sam_lambda_extra_args` | session | `list[str]` | override start-lambda CLI args |
| `sam_api` | session | `str` (base URL) | — |
| `sam_lambda_endpoint` | session | `str` (endpoint URL) | — |
| `lambda_client` | session | `LambdaClient` | change region/credentials |

All fixtures are session-scoped. Child projects override at the session level in their `conftest.py`.

### Default SAM CLI Flags

Both `sam local start-api` and `sam local start-lambda` use these defaults:

```
--skip-pull-image
--warm-containers EAGER
--log-file {log_dir}/start-api.log   (or start-lambda.log)
--port {api_port}                    (or lambda_port)
--env-vars {tmp_env_vars_file}
```

Child projects extend via `sam_api_extra_args` / `sam_lambda_extra_args` fixtures or `[tool.samstack.start_api_args]` in `pyproject.toml`.

### `sam_env_vars` Default Payload

```python
{
    "Parameters": {
        "AWS_ENDPOINT_URL": "http://localstack:4566",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
    }
}
```

Child project override example:

```python
@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars):
    sam_env_vars["MyFunction"] = {"MY_FEATURE_FLAG": "true"}
    return sam_env_vars
```

---

## Process Management

### SAM Build (one-shot container)

```python
container = (
    GenericContainer(sam_image)
    .with_volume_mapping(project_root, "/var/task", "rw")
    .with_volume_mapping("/var/run/docker.sock", "/var/run/docker.sock", "rw")
    .with_command("sam build --skip-pull-image " + " ".join(build_args))
    .with_working_dir("/var/task")
)
# wait for exit; raise SamBuildError on non-zero exit code with container logs
```

### SAM Start-API / Start-Lambda (long-running containers)

```python
container = (
    GenericContainer(sam_image)
    .with_network(docker_network)
    .with_volume_mapping(project_root, "/var/task", "rw")
    .with_volume_mapping(".aws-sam", "/var/task/.aws-sam", "ro")
    .with_volume_mapping("/var/run/docker.sock", "/var/run/docker.sock", "rw")
    .with_env("AWS_ENDPOINT_URL", "http://localstack:4566")
    .with_exposed_ports(port)
    .with_command("sam local start-api --skip-pull-image --warm-containers EAGER ...")
)
# readiness: TCP probe on mapped host port
# teardown: container.stop()
```

### Readiness Probing

TCP connection probe — no external tools, crossplatform:

```python
import socket
from contextlib import suppress

for _ in range(max_attempts):
    with suppress(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return  # ready
    time.sleep(0.5)
raise SamStartupError(port, log_tail)
```

### Log Streaming

SAM container stdout/stderr is streamed to `{log_dir}/start-api.log` (or `start-lambda.log`) on the host via testcontainers log consumer. On error, the last 50 lines are included in the exception message.

---

## Error Hierarchy

```
SamStackError                    # base; always catchable
├── SamBuildError                # sam build container exited non-zero; includes logs
├── SamStartupError              # port never bound within timeout; includes log tail
├── LocalStackStartupError       # LocalStack container unhealthy
└── DockerNetworkError           # failed to create/attach shared network
```

---

## Child Project Onboarding

### Step 1 — Add dependency

```toml
[dependency-groups]
dev = [
    "samstack>=0.1.0",
    "pytest>=8.0.0",
    "requests",
    "boto3-stubs[s3,sqs,lambda]",
]
```

### Step 2 — Configure `pyproject.toml`

```toml
[tool.samstack]
template = "template.yaml"
region = "us-east-1"
sam_image = "public.ecr.aws/sam/build-python3.13"
```

### Step 3 — Write tests

```python
# tests/test_api.py
import requests

def test_post_order(sam_api):
    r = requests.post(f"{sam_api}/orders", json={"item": "book"})
    assert r.status_code == 201

def test_invoke_directly(lambda_client):
    result = lambda_client.invoke(FunctionName="MyFunction", Payload=b"{}")
    assert result["StatusCode"] == 200
```

No `conftest.py` required for basic use. AWS service fixtures (S3 buckets, SQS queues, DynamoDB tables) are defined by the child project using `localstack_endpoint` from `samstack`.

### Plugin Registration

```toml
# samstack pyproject.toml
[project.entry-points."pytest11"]
samstack = "samstack.plugin"
```

Fixtures are auto-available in all child projects after installing `samstack` — no explicit imports needed.

---

## Testing the Library

`samstack` ships a minimal `hello_world` Lambda under `tests/fixtures/hello_world/` used by its own integration tests. Tests cover:

- `test_sam_build.py` — build succeeds, `.aws-sam/` created
- `test_sam_api.py` — `GET /hello` returns 200
- `test_sam_lambda.py` — invoke `HelloFunction` returns 200
- `test_localstack_integration.py` — Lambda reads/writes S3 or SQS seeded by fixtures

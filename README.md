# samstack

Pytest plugin that provides session-scoped fixtures for testing AWS Lambda functions locally. SAM CLI and Lambda containers run entirely inside Docker — no `sam` install required on the host. LocalStack provides the local AWS backend.

## How it works

```
your test  ──►  sam_api / lambda_client
                    │
                    ▼
              SAM container (Docker-in-Docker)
              ├── sam local start-api   (HTTP via API Gateway)
              └── sam local start-lambda (direct invoke)
                    │ creates Lambda runtime containers
                    ▼
              Lambda containers  ──►  LocalStack (S3, DynamoDB, SQS …)
```

Everything runs on an isolated Docker bridge network created per test session. After the session, all containers and the network are cleaned up automatically.

## Requirements

- Python ≥ 3.13
- Docker Desktop (macOS / Windows) or Docker Engine (Linux)
- No `sam` CLI on the host

## Installation

```bash
uv add --group dev samstack
# or
pip install samstack
```

samstack registers itself as a pytest plugin automatically via the `pytest11` entry point — no `conftest.py` imports needed.

## Minimal setup

### 1. `pyproject.toml`

```toml
[tool.samstack]
sam_image = "public.ecr.aws/sam/build-python3.13"
```

`sam_image` is the only required field.

### 2. `template.yaml`

Standard AWS SAM template. Set `Architectures` to match your host:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  MyFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: MyFunction
      CodeUri: src/
      Handler: handler.handler
      Runtime: python3.13
      Architectures:
        - arm64      # use x86_64 on Intel/AMD hosts
      Events:
        Api:
          Type: Api
          Properties:
            Path: /items
            Method: get
```

### 3. Write tests

```python
# tests/test_api.py
import requests

def test_get_items(sam_api: str) -> None:
    response = requests.get(f"{sam_api}/items", timeout=10)
    assert response.status_code == 200
```

```python
# tests/test_invoke.py
import json
from mypy_boto3_lambda import LambdaClient

def test_direct_invoke(lambda_client: LambdaClient) -> None:
    result = lambda_client.invoke(FunctionName="MyFunction", Payload=b"{}")
    assert result["StatusCode"] == 200
    payload = json.loads(result["Payload"].read())
    assert payload["statusCode"] == 200
```

### 4. Run

```bash
uv run pytest tests/ -v --timeout=300
```

On first run Docker pulls the SAM and Lambda images (~1 GB). Subsequent runs reuse cached images and complete in seconds.

---

## Fixtures reference

### SAM fixtures

All SAM fixtures are `scope="session"` — Docker containers start once and are shared across all tests.

| Fixture | Type | Description |
|---|---|---|
| `sam_api` | `str` | Base URL of `sam local start-api`, e.g. `http://127.0.0.1:3000` |
| `lambda_client` | `LambdaClient` | boto3 Lambda client pointing at `sam local start-lambda` |
| `localstack_endpoint` | `str` | LocalStack base URL, e.g. `http://127.0.0.1:4566` |
| `sam_env_vars` | `dict` | Env vars injected into all Lambda functions at runtime |
| `sam_build` | `None` | Runs `sam build`; depended on by `sam_api` and `lambda_client` |
| `sam_lambda_endpoint` | `str` | Raw `start-lambda` URL (used internally by `lambda_client`) |
| `localstack_container` | `LocalStackContainer` | Running LocalStack testcontainer |
| `docker_network` | `str` | Name of the shared Docker bridge network |
| `sam_api_extra_args` | `list[str]` | Extra CLI args appended to `sam local start-api` |
| `sam_lambda_extra_args` | `list[str]` | Extra CLI args appended to `sam local start-lambda` |

### LocalStack resource fixtures

Ready-to-use fixtures for S3, DynamoDB, SQS, and SNS. Each service provides:
- a **session-scoped boto3 client** (`s3_client`, `dynamodb_client`, `sqs_client`, `sns_client`)
- a **session-scoped factory** that creates uniquely-named resources and deletes them at the end of the session
- a **function-scoped convenience fixture** that creates one fresh resource per test and deletes it after

All resources get a UUID suffix on creation to avoid collisions between parallel test runs.

| Fixture | Scope | Type | Description |
|---|---|---|---|
| `s3_client` | session | `S3Client` | boto3 S3 client pointed at LocalStack |
| `s3_bucket_factory` | session | `Callable[[str], S3Bucket]` | Factory — call with a base name, returns a new `S3Bucket` |
| `s3_bucket` | function | `S3Bucket` | Fresh bucket per test; deleted after |
| `dynamodb_client` | session | `DynamoDBClient` | boto3 DynamoDB client pointed at LocalStack |
| `dynamodb_table_factory` | session | `Callable[[str, dict[str, str]], DynamoTable]` | Factory — call with name + key schema dict, returns a new `DynamoTable` |
| `dynamodb_table` | function | `DynamoTable` | Fresh table per test (key: `{"id": "S"}`); deleted after |
| `sqs_client` | session | `SQSClient` | boto3 SQS client pointed at LocalStack |
| `sqs_queue_factory` | session | `Callable[[str], SqsQueue]` | Factory — call with a base name, returns a new `SqsQueue` |
| `sqs_queue` | function | `SqsQueue` | Fresh queue per test; deleted after |
| `sns_client` | session | `SNSClient` | boto3 SNS client pointed at LocalStack |
| `sns_topic_factory` | session | `Callable[[str], SnsTopic]` | Factory — call with a base name, returns a new `SnsTopic` |
| `sns_topic` | function | `SnsTopic` | Fresh topic per test; deleted after |

#### Wrapper class APIs

Each wrapper exposes a high-level API and a `.client` property for raw boto3 access.

**`S3Bucket`**

```python
bucket.put("key.json", {"foo": "bar"})        # bytes | str | dict → S3 object
bucket.get("key.json")                         # → bytes
bucket.get_json("key.json")                    # → dict (JSON-decoded)
bucket.delete("key.json")
bucket.list_keys(prefix="uploads/")           # → list[str]
bucket.name                                    # → str
bucket.client                                  # → S3Client (raw escape hatch)
```

**`DynamoTable`** (uses the high-level resource API — items are plain Python dicts)

```python
table.put_item({"id": "1", "name": "widget"})
table.get_item({"id": "1"})                    # → dict | None
table.delete_item({"id": "1"})
table.query("id = :id", {":id": "1"})         # → list[dict]
table.query("pk = :pk", {":pk": "x"}, IndexName="gsi1")
table.scan()                                   # → list[dict]
table.scan(FilterExpression="attr = :v")
table.name                                     # → str
table.table                                    # → Table (boto3 resource Table)
table.client                                   # → DynamoDBClient (raw escape hatch)
```

**`SqsQueue`**

```python
queue.send("hello")                            # str | dict → message ID
queue.send({"task": "run"}, DelaySeconds=5)   # kwargs forwarded to boto3
queue.receive(max_messages=10, wait_seconds=5) # → list[dict]
queue.purge()
queue.url                                      # → str
queue.client                                   # → SQSClient (raw escape hatch)
```

**`SnsTopic`**

```python
topic.publish("hello")                         # str | dict → message ID
topic.publish({"event": "user.created"}, subject="New user")
topic.subscribe_sqs(queue_arn)                 # → subscription ARN
topic.arn                                      # → str
topic.client                                   # → SNSClient (raw escape hatch)
```

---

## Configuration

All fields in `[tool.samstack]` are optional except `sam_image`.

```toml
[tool.samstack]
sam_image         = "public.ecr.aws/sam/build-python3.13"  # required
template          = "template.yaml"
region            = "us-east-1"
api_port          = 3000
lambda_port       = 3001
localstack_image  = "localstack/localstack:4"
log_dir           = "logs/sam"
build_args        = []
start_api_args    = []
start_lambda_args = []
add_gitignore     = true
architecture      = "arm64"              # auto-detected; override if needed
```

| Field | Type | Default | Description |
|---|---|---|---|
| `sam_image` | string | **required** | Docker image used for `sam build`. See [SAM image versions](#sam-image-versions). |
| `template` | string | `"template.yaml"` | SAM template path, relative to `project_root`. |
| `region` | string | `"us-east-1"` | AWS region passed to SAM and LocalStack. |
| `api_port` | int | `3000` | Host port mapped to `sam local start-api`. |
| `lambda_port` | int | `3001` | Host port mapped to `sam local start-lambda`. |
| `localstack_image` | string | `"localstack/localstack:4"` | LocalStack Docker image. See [LocalStack image versions](#localstack-image-versions). |
| `log_dir` | string | `"logs/sam"` | Directory (relative to `project_root`) for SAM logs and `env_vars.json`. |
| `build_args` | list[string] | `[]` | Extra CLI args appended to `sam build`. |
| `start_api_args` | list[string] | `[]` | Extra CLI args appended to `sam local start-api`. |
| `start_lambda_args` | list[string] | `[]` | Extra CLI args appended to `sam local start-lambda`. |
| `add_gitignore` | bool | `true` | Automatically add `log_dir` to `.gitignore`. |
| `architecture` | string | auto-detected | Lambda architecture: `"arm64"` or `"x86_64"`. Auto-detected from `platform.machine()` — Apple Silicon / Linux ARM64 → `arm64`, Intel/AMD → `x86_64`. Controls `DOCKER_DEFAULT_PLATFORM` on SAM and build containers. |

---

## Customising fixtures

Override any fixture in your project's `conftest.py`.

### Supply settings programmatically

```python
# conftest.py
from pathlib import Path
import pytest
from samstack.settings import SamStackSettings

@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        project_root=Path(__file__).parent,
        region="eu-west-1",
    )
```

This is useful in monorepos where `pyproject.toml` is not at the project root.

### Inject environment variables into Lambda

`sam_env_vars` defaults to a dict with AWS credentials and endpoint pointing at LocalStack. Extend it with your own values:

```python
# conftest.py
import pytest

@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars: dict) -> dict:
    sam_env_vars["Parameters"]["MY_TABLE"] = "local-table"
    sam_env_vars["Parameters"]["FEATURE_FLAG"] = "true"
    return sam_env_vars
```

To target a specific function instead of all functions, use its logical name as the key:

```python
sam_env_vars["MyFunction"] = {"SECRET": "test-secret"}
```

### Use LocalStack in tests

samstack ships built-in fixtures for S3, DynamoDB, SQS, and SNS. Use the function-scoped fixtures for isolated per-test resources, or the session-scoped factories to share resources across tests.

```python
# tests/test_api.py
import requests

def test_post_creates_record(
    sam_api: str,
    dynamodb_table_factory,
    sam_env_vars,   # already injected; add your table name before containers start
) -> None:
    table = dynamodb_table_factory("orders", {"id": "S"})
    response = requests.post(f"{sam_api}/items", json={"id": "abc", "name": "widget"})
    assert response.status_code == 201
    assert table.get_item({"id": "abc"})["name"] == "widget"
```

For test-isolated resources, use the function-scoped fixtures directly:

```python
def test_upload_then_list(s3_bucket) -> None:
    s3_bucket.put("report.json", {"rows": 42})
    assert s3_bucket.list_keys() == ["report.json"]

def test_queue_round_trip(sqs_queue) -> None:
    sqs_queue.send({"job": "process"})
    messages = sqs_queue.receive(max_messages=1, wait_seconds=5)
    assert len(messages) == 1
```

To inject a resource name into Lambda at startup, extend `sam_env_vars` before containers start (use a session-scoped factory fixture so the name is stable):

```python
# conftest.py
import pytest
from samstack.resources.dynamodb import DynamoTable

TABLE_NAME = "orders-fixture"

@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars: dict) -> dict:
    sam_env_vars["Parameters"]["ORDERS_TABLE"] = TABLE_NAME
    return sam_env_vars

@pytest.fixture(scope="session")
def orders_table(dynamodb_table_factory) -> DynamoTable:
    return dynamodb_table_factory("orders", {"id": "S"})
```

When you need capabilities beyond the wrapper API, use `.client` to access the raw boto3 client:

```python
def test_raw_access(s3_bucket) -> None:
    # wrapper covers common ops; use .client for everything else
    s3_bucket.client.put_bucket_versioning(
        Bucket=s3_bucket.name,
        VersioningConfiguration={"Status": "Enabled"},
    )
```

### Pass extra CLI args

```python
@pytest.fixture(scope="session")
def sam_api_extra_args() -> list[str]:
    return ["--debug"]

@pytest.fixture(scope="session")
def sam_lambda_extra_args() -> list[str]:
    return ["--debug"]
```

---

## Lambda handler conventions

Lambda functions can reach LocalStack at `http://localstack:4566`, injected automatically as `AWS_ENDPOINT_URL`. Pass it as `endpoint_url` to boto3:

```python
import boto3, os

def handler(event, context):
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL") or None,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    # ...
```

In production `AWS_ENDPOINT_URL` is unset so boto3 hits real AWS. The `or None` guard ensures an empty string doesn't override production routing.

---

## SAM image versions

Pick the build image that matches your Lambda runtime:

| Runtime | `sam_image` |
|---|---|
| Python 3.13 | `public.ecr.aws/sam/build-python3.13` |
| Python 3.12 | `public.ecr.aws/sam/build-python3.12` |
| Python 3.11 | `public.ecr.aws/sam/build-python3.11` |
| Node.js 22 | `public.ecr.aws/sam/build-nodejs22.x` |
| Java 21 | `public.ecr.aws/sam/build-java21` |

Full list: [gallery.ecr.aws/sam](https://gallery.ecr.aws/sam).

---

## LocalStack image versions

The default is `localstack/localstack:4`. To pin a specific version or use LocalStack Pro, set `localstack_image` in `[tool.samstack]`:

```toml
[tool.samstack]
sam_image        = "public.ecr.aws/sam/build-python3.13"
localstack_image = "localstack/localstack:3"   # pin to v3
```

| Use case | `localstack_image` |
|---|---|
| Latest v4 (default) | `localstack/localstack:4` |
| Specific patch | `localstack/localstack:4.3.0` |
| Pin to v3 | `localstack/localstack:3` |
| LocalStack Pro | `localstack/localstack-pro:4` |

Full list: [hub.docker.com/r/localstack/localstack/tags](https://hub.docker.com/r/localstack/localstack/tags).

---

## Logs

SAM and build output is streamed to `{log_dir}/` (default `logs/sam/`):

```
logs/sam/
├── start-api.log      # sam local start-api stdout + Lambda invocation logs
├── start-lambda.log   # sam local start-lambda stdout
└── env_vars.json      # generated env vars file passed to SAM
```

On startup failure the last 50 log lines are included in the exception message. `log_dir/` is added to `.gitignore` automatically (set `add_gitignore = false` to disable).

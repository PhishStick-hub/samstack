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
| `warm_functions` | `list[str]` | Function names to pre-warm. See [Warm containers](#warm-containers). |
| `warm_api_routes` | `dict[str, str]` | Function name → API route path mapping for HTTP pre-warming. See [Warm containers](#warm-containers). |
| `sam_lambda_endpoint` | `str` | Raw `start-lambda` URL (used internally by `lambda_client`) |
| `localstack_container` | `LocalStackContainer` | Running LocalStack testcontainer |
| `docker_network` | `str` | Name of the shared Docker bridge network |
| `sam_api_extra_args` | `list[str]` | Extra CLI args appended to `sam local start-api` |
| `sam_lambda_extra_args` | `list[str]` | Extra CLI args appended to `sam local start-lambda` |

### LocalStack resource fixtures

Ready-to-use fixtures for S3, DynamoDB, SQS, and SNS. Each service provides:
- a **session-scoped boto3 client** (`s3_client`, `dynamodb_client`, `sqs_client`, `sns_client`)
- a **session-scoped boto3 resource object** (`s3_resource`, `dynamodb_resource`, `sqs_resource`) — S3, DynamoDB, and SQS only (SNS has no boto3 resource API)
- a **session-scoped `make_*` fixture** that creates uniquely-named resources and deletes them at the end of the session
- a **function-scoped convenience fixture** that creates one fresh resource per test and deletes it after

All resources get a UUID suffix on creation to avoid collisions between parallel test runs.

| Fixture | Scope | Type | Description |
|---|---|---|---|
| `s3_client` | session | `S3Client` | boto3 S3 client pointed at LocalStack |
| `s3_resource` | session | `S3ServiceResource` | boto3 S3 resource pointed at LocalStack |
| `make_s3_bucket` | session | `Callable[[str], S3Bucket]` | Call with a base name, returns a new `S3Bucket` |
| `s3_bucket` | function | `S3Bucket` | Fresh bucket per test; deleted after |
| `dynamodb_client` | session | `DynamoDBClient` | boto3 DynamoDB client pointed at LocalStack |
| `dynamodb_resource` | session | `DynamoDBServiceResource` | boto3 DynamoDB resource (high-level) pointed at LocalStack |
| `make_dynamodb_table` | session | `Callable[[str, dict[str, str]], DynamoTable]` | Call with name + key schema dict, returns a new `DynamoTable` |
| `dynamodb_table` | function | `DynamoTable` | Fresh table per test (key: `{"id": "S"}`); deleted after |
| `sqs_client` | session | `SQSClient` | boto3 SQS client pointed at LocalStack |
| `sqs_resource` | session | `SQSServiceResource` | boto3 SQS resource pointed at LocalStack |
| `make_sqs_queue` | session | `Callable[[str], SqsQueue]` | Call with a base name, returns a new `SqsQueue` |
| `sqs_queue` | function | `SqsQueue` | Fresh queue per test; deleted after |
| `sns_client` | session | `SNSClient` | boto3 SNS client pointed at LocalStack |
| `make_sns_topic` | session | `Callable[[str], SnsTopic]` | Call with a base name, returns a new `SnsTopic` |
| `sns_topic` | function | `SnsTopic` | Fresh topic per test; deleted after |
| `make_lambda_mock` | session | `Callable[..., LambdaMock]` | Wire a mock Lambda (spy bucket + env vars + response queue). See [Mocking other Lambdas](#mocking-other-lambdas-integration-tests). |

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
queue.receive(max=10, wait=5)                  # → list[dict]
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
log_dir           = "logs"
build_args        = []
start_api_args    = []
start_lambda_args = []
add_gitignore     = true
warm_functions    = []                    # functions to pre-warm (default: all)
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
| `log_dir` | string | `"logs"` | Directory (relative to `project_root`) for SAM and LocalStack logs and `env_vars.json`. |
| `build_args` | list[string] | `[]` | Extra CLI args appended to `sam build`. |
| `start_api_args` | list[string] | `[]` | Extra CLI args appended to `sam local start-api`. |
| `start_lambda_args` | list[string] | `[]` | Extra CLI args appended to `sam local start-lambda`. |
| `add_gitignore` | bool | `true` | Automatically add `log_dir` to `.gitignore`. |
| `warm_functions` | list[string] | `[]` | Lambda function names to pre-warm before tests. Empty list preserves `EAGER` behavior (all functions pre-warmed). Non-empty switches to `LAZY` — only listed functions get pre-warmed. See [Warm containers](#warm-containers). |
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

> **SAM caveat:** `sam local` only surfaces env vars that are **declared** on the
> function's `Environment.Variables` section of the template. Values in
> `sam_env_vars` (both `Parameters` and per-function entries) act as *overrides*
> for vars already declared on the function — undeclared ones are dropped
> silently. Declare each key you plan to inject, even as an empty string:
>
> ```yaml
> Resources:
>   MyFunction:
>     Type: AWS::Serverless::Function
>     Properties:
>       Environment:
>         Variables:
>           AWS_ENDPOINT_URL_S3: ""      # filled at runtime by sam_env_vars
>           AWS_ENDPOINT_URL_LAMBDA: ""
>           MY_TABLE: ""
> ```

### Use LocalStack in tests

samstack ships built-in fixtures for S3, DynamoDB, SQS, and SNS. Use the function-scoped fixtures for isolated per-test resources, or the session-scoped factories to share resources across tests.

```python
# tests/test_api.py
import requests

def test_post_creates_record(
    sam_api: str,
    make_dynamodb_table,
    sam_env_vars,   # already injected; add your table name before containers start
) -> None:
    table = make_dynamodb_table("orders", {"id": "S"})
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
    messages = sqs_queue.receive(max=1, wait=5)
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
def orders_table(make_dynamodb_table) -> DynamoTable:
    return make_dynamodb_table("orders", {"id": "S"})
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

## Warm containers

Controls which Lambda functions get pre-warmed containers before tests execute. Pre-warming eliminates cold-start latency: the first test invocation hits an already-warm container.

Two fixtures control pre-warming:

- **`warm_functions`** — a list of function names. Listed functions get a synthetic `lambda_client.invoke()` call before tests run.
- **`warm_api_routes`** — a dict mapping function names to HTTP paths (e.g. `{"MyFunc": "/items"}`). Listed functions get a synthetic HTTP GET before tests run.

The two fixtures combine. Here's what happens for each function:

| In `warm_functions`? | In `warm_api_routes`? | Result |
|---|---|---|
| ✅ | ❌ | Lambda invoke pre-warm only |
| ✅ | ✅ | Lambda invoke **+** HTTP GET pre-warm |
| ❌ | ✅ | **Nothing** — `warm_api_routes` without `warm_functions` is ignored |
| ❌ | ❌ | Cold start |

When `warm_functions` is empty (the default), `start-lambda` runs in `EAGER` mode — SAM pre-creates containers for **all** functions. When `warm_functions` is non-empty, `start-lambda` switches to `LAZY` mode and only the listed functions are pre-warmed; unlisted functions start cold.

### Examples

**Warm a function for direct Lambda invoke only:**

```python
# conftest.py
import pytest

@pytest.fixture(scope="session")
def warm_functions() -> list[str]:
    return ["ProcessOrder"]
```

`ProcessOrder` gets a synthetic `invoke()` before tests. No HTTP pre-warming.

**Warm a function for both Lambda invoke and HTTP:**

```python
# conftest.py
import pytest

@pytest.fixture(scope="session")
def warm_functions() -> list[str]:
    return ["HelloWorldFunction"]

@pytest.fixture(scope="session")
def warm_api_routes() -> dict[str, str]:
    return {"HelloWorldFunction": "/hello"}
```

`HelloWorldFunction` gets both a synthetic `invoke()` and an HTTP GET to `/hello` before tests.

**Warm multiple functions with mixed strategies:**

```python
# conftest.py
import pytest

@pytest.fixture(scope="session")
def warm_functions() -> list[str]:
    return ["ProcessOrder", "HelloWorldFunction"]

@pytest.fixture(scope="session")
def warm_api_routes() -> dict[str, str]:
    return {"HelloWorldFunction": "/hello"}
```

- `ProcessOrder` — Lambda invoke only (not in `warm_api_routes`)
- `HelloWorldFunction` — Lambda invoke + HTTP GET (in both lists)

**Via pyproject.toml (no conftest override needed for simple cases):**

```toml
[tool.samstack]
sam_image = "public.ecr.aws/sam/build-python3.13"
warm_functions = ["ProcessOrder", "SendNotification"]
```

### Known limitations

- **`--debug-port` is incompatible** with warm containers. SAM CLI (issue [#7308](https://github.com/aws/aws-sam-cli/issues/7308)) does not support port-based debugging when `--warm-containers LAZY` is set. Do not pass `--debug-port` in `sam_api_extra_args` or `sam_lambda_extra_args` when using warm containers.
- **No auto-discovery** of functions from the SAM template. You must explicitly list function names in `warm_functions` and route paths in `warm_api_routes`. Auto-discovery is planned for v1.2.
- **No multi-template support** per session. All functions must be declared in the single template referenced by `samstack_settings.template`.
- **Pre-warming is sequential** — each function or route is warmed one at a time. Large function lists may add noticeable startup time.
- **Crash test skips on macOS**. The Ryuk reaper process inside Docker Desktop's Linux VM does not reliably detect SIGKILL across the TCP proxy boundary. Warm container crash cleanup is verified on Linux CI.

---

## Lambda handler conventions

samstack injects **per-service** endpoint env vars (boto3 ≥ 1.28 auto-picks these up) so boto3 clients need no explicit `endpoint_url`:

| Variable | Points at |
|---|---|
| `AWS_ENDPOINT_URL_S3`, `AWS_ENDPOINT_URL_DYNAMODB`, `AWS_ENDPOINT_URL_SQS`, `AWS_ENDPOINT_URL_SNS` | LocalStack (`http://localstack:4566`) |
| `AWS_ENDPOINT_URL_LAMBDA` | SAM `start-lambda` (`http://sam-lambda:{lambda_port}`) — so Lambda-to-Lambda invokes stay in SAM instead of leaking into LocalStack |

```python
import boto3

def handler(event, context):
    s3 = boto3.client("s3")        # auto-routed to LocalStack
    lam = boto3.client("lambda")   # auto-routed to sam local start-lambda
    # ...
```

In production those env vars are unset, so boto3 hits real AWS with no code changes.

> **Breaking change (v0.3.0):** previously samstack set a global `AWS_ENDPOINT_URL` that routed **all** services — including Lambda — to LocalStack. Lambda-to-Lambda invokes now correctly reach the SAM local-lambda runtime. If your production code references `AWS_ENDPOINT_URL`, migrate to the per-service vars or drop the `endpoint_url` kwarg entirely.

---

## Mocking other Lambdas (integration tests)

When Lambda A calls Lambda B (via HTTP through API Gateway **or** via boto3 invoke), replace B with a mock that records every incoming call and returns canned responses. Mocks share the same SAM template as the real function — no fakes, no monkey-patching.

### Define the mock function in your test template

Keep production `template.yaml` clean, put the mock in a test-only template (e.g. `template.test.yaml`). The mock handler code belongs **under `tests/`**, never next to production `src/`:

```
lambda_a/
  template.yaml          # prod — only LambdaAFunction
  template.test.yaml     # test — LambdaAFunction + MockBFunction
  src/
    lambda_a/
      handler.py         # production code
  tests/
    mocks/
      mock_b/
        handler.py       # 1 line: re-exports samstack.mock.spy_handler
        requirements.txt # samstack
```

```yaml
# template.test.yaml
Resources:
  LambdaAFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/lambda_a/
      Handler: handler.handler
  MockBFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: tests/mocks/mock_b/
      Handler: handler.handler
      Events:
        Proxy:
          Type: Api
          Properties: { Path: /mock-b/{proxy+}, Method: ANY }
```

```python
# tests/mocks/mock_b/handler.py
from samstack.mock import spy_handler as handler
```

### Wire the mock from your conftest

```python
# tests/conftest.py
import pytest
from samstack.mock import LambdaMock

@pytest.fixture(scope="session")
def samstack_settings():
    from samstack.settings import SamStackSettings
    return SamStackSettings(
        sam_image="public.ecr.aws/sam/build-python3.13",
        template="template.test.yaml",
    )

@pytest.fixture(scope="session")
def sam_env_vars(sam_env_vars):
    # Lambda A uses plain HTTP (not boto3) to call Mock B — inject its URL.
    sam_env_vars["Parameters"]["LAMBDA_B_URL"] = "http://sam-api:3000/mock-b"
    return sam_env_vars

@pytest.fixture(scope="session", autouse=True)
def _mock_b_session(make_lambda_mock) -> LambdaMock:
    # autouse forces mock registration before sam_build reads sam_env_vars
    # and writes env_vars.json. Without it, tests that request `sam_api`
    # before `mock_b` never propagate MOCK_SPY_BUCKET to the Lambda.
    return make_lambda_mock("MockBFunction", alias="mock-b")

@pytest.fixture
def mock_b(_mock_b_session):
    _mock_b_session.clear()    # wipe spy + response queue between tests
    yield _mock_b_session
```

> **Template requirement**: every env var you plan to inject via
> `make_lambda_mock` / `sam_env_vars` must be declared on the function's
> `Environment.Variables` in `template.test.yaml` (empty string is fine) —
> `sam local` silently drops undeclared keys. For a mock function this means:
>
> ```yaml
> MockBFunction:
>   Type: AWS::Serverless::Function
>   Properties:
>     CodeUri: tests/mocks/mock_b/
>     Handler: handler.handler
>     Environment:
>       Variables:
>         MOCK_SPY_BUCKET: ""
>         MOCK_FUNCTION_NAME: ""
>         AWS_ENDPOINT_URL_S3: ""
> ```

### Write tests

```python
import json, requests

# 1. Verify Lambda A calls Mock B with the right payload (default 200 response).
def test_http_call(sam_api, mock_b):
    requests.post(f"{sam_api}/lambda-a/http", json={"path": "/orders", "payload": {"qty": 3}})
    assert mock_b.calls.one.path == "/orders"
    assert mock_b.calls.one.body == {"qty": 3}

# 2. Override Mock B's response for a specific test.
def test_error_path(sam_api, mock_b):
    mock_b.next_response({"statusCode": 500, "body": '{"error": "boom"}'})
    resp = requests.post(f"{sam_api}/lambda-a/http", json={"path": "/x", "payload": {}})
    assert resp.json() == {"error": "boom"}

# 3. Multi-call with a response queue.
def test_batch(lambda_client, mock_b):
    mock_b.response_queue([{"id": "a"}, {"id": "b"}, {"id": "c"}])
    for tag in ("a", "b", "c"):
        lambda_client.invoke(
            FunctionName="LambdaAFunction",
            Payload=json.dumps({"target": "b", "payload": {"tag": tag}}).encode(),
        )
    assert [c.body["tag"] for c in mock_b.calls] == ["a", "b", "c"]

# 4. Parametrized tests + filtering.
@pytest.mark.parametrize("user_id", ["u1", "u2", "u3"])
def test_path_per_user(sam_api, mock_b, user_id):
    requests.post(f"{sam_api}/lambda-a/http",
                  json={"path": f"/users/{user_id}", "payload": {}})
    assert mock_b.calls.one.path == f"/users/{user_id}"

def test_only_posts(sam_api, mock_b):
    # Mix of calls; filter to just the ones you care about.
    orders = mock_b.calls.matching(path="/orders", method="POST")
    assert orders.one.body["total"] == 100
```

### API summary

**`Call`** (frozen dataclass)
- `method: str` — HTTP verb or `"INVOKE"`
- `path: str | None` — request path (None for direct invokes)
- `headers: dict[str, str]` / `query: dict[str, str]`
- `body: Any` — JSON-parsed when `content-type` is JSON; raw string otherwise; invoke payload for direct invokes
- `raw_event: dict` — unmodified Lambda event

**`CallList`** (sequence of `Call`)
- `calls.one` — asserts exactly one call and returns it
- `calls.last` — last call
- `calls.matching(method="POST", path="/orders")` — new CallList filtered by field equality
- Supports `len()`, indexing, iteration

**`LambdaMock`**
- `.calls` — `CallList` in chronological order
- `.clear()` — remove all spy events + queued responses
- `.next_response(resp: dict)` — queue a single response
- `.response_queue(resps: list[dict])` — queue multiple responses (consumed head-first)
- `.name` / `.bucket` — spy alias and underlying `S3Bucket`

**`make_lambda_mock(function_name: str, *, alias: str, bucket: S3Bucket | None = None)`**
Session-scoped factory. Creates a spy bucket (or reuses one), injects `MOCK_SPY_BUCKET` / `MOCK_FUNCTION_NAME` / `AWS_ENDPOINT_URL_S3` into `sam_env_vars[function_name]`, returns a `LambdaMock`. Must be called **before** `sam_build` runs (i.e. before any test requests `sam_api` / `sam_lambda_endpoint`).

### How the spy stores calls

- Each incoming event is JSON-serialised (normalized into `Call` shape) and written to `s3://{spy_bucket}/spy/{alias}/{iso-timestamp}-{uuid}.json` — lex sort equals chronological order.
- `response_queue` lives at `s3://{spy_bucket}/mock-responses/{alias}/queue.json`; the head is popped and returned, remainder written back (or object deleted when empty).
- Multiple mocks can share one bucket — each owns its own prefix.

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

SAM and LocalStack output is streamed to `{log_dir}/` (default `logs/`):

```
logs/
├── localstack.log     # LocalStack container stdout + stderr
├── start-api.log      # sam local start-api stdout + Lambda invocation logs
├── start-lambda.log   # sam local start-lambda stdout
└── env_vars.json      # generated env vars file passed to SAM
```

On startup failure the last 50 log lines are included in the exception message. `log_dir/` is added to `.gitignore` automatically (set `add_gitignore = false` to disable).

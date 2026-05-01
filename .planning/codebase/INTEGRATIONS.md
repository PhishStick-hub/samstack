# External Integrations

_Last updated: 2026-04-23_

## Summary

`samstack` orchestrates three Docker-based services — LocalStack, SAM CLI (start-api), and SAM CLI (start-lambda) — connected via a named Docker bridge network. All AWS API calls from tests go to LocalStack at `http://localstack:4566` (inside Docker) or the host-mapped endpoint URL returned by `localstack_container.get_url()` (from tests). No real AWS services are contacted at any point.

## AWS Services (via LocalStack)

All AWS service calls are routed to LocalStack — never to real AWS endpoints.

**Services emulated:**
- S3 — `boto3.client("s3", endpoint_url=localstack_endpoint)` — `src/samstack/fixtures/resources.py`
- DynamoDB — `boto3.client("dynamodb", endpoint_url=localstack_endpoint)` — `src/samstack/fixtures/resources.py`
- SQS — `boto3.client("sqs", endpoint_url=localstack_endpoint)` — `src/samstack/fixtures/resources.py`
- SNS — `boto3.client("sns", endpoint_url=localstack_endpoint)` — `src/samstack/fixtures/resources.py`
- Lambda — `boto3.client("lambda", endpoint_url=sam_lambda_endpoint)` — pointed at SAM local-lambda runtime (not LocalStack); `src/samstack/fixtures/sam_lambda.py`

**LocalStack credentials (hardcoded constants):**
- `LOCALSTACK_ACCESS_KEY = "test"` — `src/samstack/_constants.py`
- `LOCALSTACK_SECRET_KEY = "test"` — `src/samstack/_constants.py`

**Default region:** `us-east-1` (overridable via `SamStackSettings.region`)

## Docker

Docker is the primary infrastructure layer — everything runs in containers.

**Docker SDK:**
- Package: `docker >= 7.0.0`
- Client: `docker.from_env()` — used in `src/samstack/fixtures/localstack.py` and `src/samstack/fixtures/_sam_container.py`
- Imported lazily in `run_one_shot_container` (`src/samstack/_process.py`) to avoid import-time failures when Docker is unavailable

**Docker socket:**
- `DOCKER_SOCKET = "/var/run/docker.sock"` — constant in `src/samstack/fixtures/_sam_container.py`
- Mounted into both LocalStack and SAM containers (Docker-in-Docker) so SAM can spawn Lambda runtime containers

**Docker networking:**
- `docker_network` fixture creates a named bridge network: `samstack-{uuid8}` — `src/samstack/fixtures/localstack.py`
- LocalStack connects with DNS alias `localstack`
- SAM start-api connects with alias `sam-api`
- SAM start-lambda connects with alias `sam-lambda`
- Lambda containers (spawned by SAM via socket) land on the same network; reach LocalStack at `http://localstack:4566`
- Network teardown stops and removes all connected containers before destroying the network

**Cross-platform host resolution:**
- macOS (Darwin): Docker Desktop provides `host.docker.internal` natively; no extra configuration
- Linux: `--add-host host.docker.internal:host-gateway` injected via `_extra_hosts()` in `src/samstack/fixtures/_sam_container.py`

## LocalStack

- Image: `localstack/localstack:4` (default; overridable via `SamStackSettings.localstack_image`)
- Started via `testcontainers.localstack.LocalStackContainer`
- Log output streamed to `{project_root}/{log_dir}/localstack.log`
- Endpoint exposed to host: returned by `localstack_container.get_url()` — `src/samstack/fixtures/localstack.py`
- Internal DNS alias `localstack` used by other containers on the shared bridge network

## SAM CLI (AWS Serverless Application Model)

SAM CLI runs **inside Docker** — no host `sam` install required.

**SAM image:**
- Configured by child project: `sam_image` in `[tool.samstack]` (required field, no default)
- Example: `public.ecr.aws/sam/build-python3.13`

**SAM start-api:**
- Fixture: `sam_api` — `src/samstack/fixtures/sam_api.py`
- Port: `SamStackSettings.api_port` (default `3000`)
- Readiness probe: `wait_for_http` (HTTP probe, not TCP) — avoids Docker Desktop port-forwarder false positives
- Log output: `{log_dir}/sam/api.log`
- DNS alias on bridge network: `sam-api`

**SAM start-lambda:**
- Fixture: `sam_lambda_endpoint` — `src/samstack/fixtures/sam_lambda.py`
- Port: `SamStackSettings.lambda_port` (default `3001`)
- Readiness probe: `wait_for_port` (TCP)
- Log output: `{log_dir}/sam/lambda.log`
- DNS alias on bridge network: `sam-lambda`

**SAM build:**
- Fixture: `sam_build` — `src/samstack/fixtures/sam_build.py`
- Runs `sam build` as a one-shot container via `run_one_shot_container` (`src/samstack/_process.py`)
- Does **not** depend on `localstack_container` — build does not need LocalStack

**CLI flags injected on all SAM containers:**
- `--skip-pull-image` (omitted in CI when `CI` env var is set)
- `--warm-containers LAZY`
- `--host 0.0.0.0`
- `--port {port}`
- `--env-vars {host_path}/{log_dir}/env_vars.json`
- `--docker-network {network}`
- `--container-host host.docker.internal`
- `--container-host-interface 0.0.0.0`

**Volume mounts (SAM containers):**
- `{project_root}` → `{project_root}` (real host path, not `/var/task`) — ensures Lambda containers receive resolvable volume paths
- `/var/run/docker.sock` → `/var/run/docker.sock`

## Environment Variables Injected into Lambda

Set by `sam_env_vars` fixture; written to `{log_dir}/env_vars.json`; consumed by `sam local` via `--env-vars`.

**Per-service LocalStack endpoints:**
- `AWS_ENDPOINT_URL_S3` → `http://localstack:4566`
- `AWS_ENDPOINT_URL_DYNAMODB` → `http://localstack:4566`
- `AWS_ENDPOINT_URL_SQS` → `http://localstack:4566`
- `AWS_ENDPOINT_URL_SNS` → `http://localstack:4566`
- `AWS_ENDPOINT_URL_LAMBDA` → `http://sam-lambda:{settings.lambda_port}`

boto3 ≥ 1.28 auto-reads `AWS_ENDPOINT_URL_<SERVICE>` — no `endpoint_url=` kwarg needed in Lambda code.

**SAM env-var propagation constraint:** `sam local` only delivers env vars that are **declared** on the function in the SAM template (`Environment.Variables`). Undeclared keys are silently dropped even if present in `--env-vars` JSON.

**Mock-specific vars (set by `make_lambda_mock`):**
- `MOCK_SPY_BUCKET` — S3 bucket name for spy call storage
- `MOCK_FUNCTION_NAME` — short alias used in S3 key prefixes
- `AWS_ENDPOINT_URL_S3` — already set above; overridden per-function for mock Lambdas

## S3 as Mock Transport (`samstack.mock`)

The `samstack.mock` module uses S3 (via LocalStack) as a side-channel between Lambda containers and the test process:

- **Spy calls:** written to `s3://{MOCK_SPY_BUCKET}/spy/{name}/<timestamp>-<uuid>.json` — `src/samstack/mock/handler.py`
- **Canned responses:** read from `s3://{MOCK_SPY_BUCKET}/mock-responses/{name}/queue.json` — `src/samstack/mock/handler.py`
- Test-side access: `LambdaMock` fixture reads/writes same bucket via `s3_client` — `src/samstack/mock/fixture.py`

## CI/CD

**Platform:** GitHub Actions

**Workflows** (`.github/workflows/`):
- `ci.yml` — triggers on push/PR to `main`; calls `_ci.yml`
- `_ci.yml` — reusable; runs quality checks (ruff format, ruff lint, ty check), unit tests; optionally runs build job
- `publish-pypi.yml` — builds wheel via `uv build`, publishes via `uv publish` to `pypi.org/project/samstack/`
- `publish-testpypi.yml` — same flow targeting Test PyPI
- `release-please.yml` — automated release PR management
- `lockfile.yml` — lockfile maintenance

**CI env vars / secrets:**
- `PYPI_TOKEN` — GitHub Actions secret; injected as `UV_PUBLISH_TOKEN` for `uv publish`

**Python setup in CI:**
- `astral-sh/setup-uv@v4` with cache enabled
- `actions/setup-python@v5` with `python-version: "3.13"`

## Package Distribution

- Registry: PyPI (`https://pypi.org/project/samstack/`)
- Build tool: `uv build`
- Publish tool: `uv publish`
- Homepage/repo: `https://github.com/PhishStick-hub/samstack`

## File Storage

**Logs (local, not committed):**
- `{project_root}/{log_dir}/localstack.log` — LocalStack container output
- `{project_root}/{log_dir}/sam/api.log` — SAM start-api output
- `{project_root}/{log_dir}/sam/lambda.log` — SAM start-lambda output
- `{project_root}/{log_dir}/env_vars.json` — generated env-vars file passed to `--env-vars`

**Directories listed in `.gitignore` via `add_gitignore` setting (default `True`):**
- `logs/` — all log output

## Authentication & Identity

- No real AWS credentials used — LocalStack accepts `"test"` / `"test"` for all services
- No OAuth, OIDC, or external identity provider
- PyPI publish authenticated via `PYPI_TOKEN` secret in GitHub Actions environment

---

_Integration audit: 2026-04-23_

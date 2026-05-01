# Technology Stack

_Last updated: 2026-04-23_

## Summary

`samstack` is a pytest plugin library (Python 3.13) that provides session-scoped fixtures for testing AWS Lambda functions locally via SAM CLI and LocalStack — both running in Docker containers managed by testcontainers. The project is packaged as a standard Python wheel distributed to PyPI, using hatchling as the build backend and uv as the package manager.

## Languages

**Primary:**
- Python 3.13 — entire library source and test suite
  - Enforced via `.python-version` (pinned to `3.13`)
  - `requires-python = ">=3.13"` in `pyproject.toml`

**Secondary:**
- None — single-language project

## Runtime

**Environment:**
- CPython 3.13

**Package Manager:**
- `uv` (Astral) — dependency resolution, virtualenv, lock, run, build, publish
- Lockfile: `uv.lock` (present and committed)
- `.venv/` holds the local virtualenv

## Frameworks

**Core:**
- `pytest >= 8.0.0` — test runner and plugin host; `samstack` registers via `pytest11` entry point in `pyproject.toml`

**Containers / Infrastructure:**
- `testcontainers[localstack] >= 4.10.0` — manages LocalStack Docker container lifecycle; `LocalStackContainer` from `testcontainers.localstack`; `DockerContainer` from `testcontainers.core.container` for SAM containers
- `docker >= 7.0.0` — Docker SDK for Python; used for network management, container log streaming, one-shot build containers

**AWS SDK:**
- `boto3 >= 1.35.0` — AWS SDK; all clients pointed at LocalStack endpoint; per-service `AWS_ENDPOINT_URL_<SERVICE>` env vars (boto3 ≥ 1.28 auto-picks these up)

**Testing (dev):**
- `pytest-timeout >= 2.4.0` — per-test timeout enforcement (integration tests use `--timeout=300`)
- `requests >= 2.32.0` — HTTP client for REST API assertions against `sam local start-api`
- `boto3-stubs[lambda,s3,dynamodb,sqs,sns] >= 1.35.0` — type stubs for boto3 clients; used in `TYPE_CHECKING` blocks only

**Build:**
- `hatchling >= 1.26` — PEP 517 build backend; wheel target configured in `[tool.hatch.build.targets.wheel]`

## Key Dependencies

**Critical:**
- `testcontainers[localstack]` — the container lifecycle abstraction that the entire fixture chain depends on; `LocalStackContainer` is the heart of the infrastructure layer
- `docker` (Docker SDK) — imported lazily in `run_one_shot_container` (`src/samstack/_process.py`) to avoid import-time failures; also used directly in `localstack.py` and `_sam_container.py` for network and alias management
- `boto3` — all resource wrappers (`S3Bucket`, `DynamoTable`, `SqsQueue`, `SnsTopic`) and mock handler depend on it; mock handler (`src/samstack/mock/handler.py`) uses only stdlib + boto3 (no other samstack imports) so it can run inside a Lambda container

**Infrastructure:**
- `pytest` — the host framework; plugin auto-discovered via `pytest11` entry point; all fixtures use `@pytest.fixture(scope="session")` or `scope="function"`

## Configuration

**Tool configuration (`pyproject.toml` `[tool.samstack]`):**
- `sam_image` — required; Docker image for SAM CLI (e.g. `public.ecr.aws/sam/build-python3.13`)
- `template` — SAM template file, default `template.yaml`
- `region` — AWS region, default `us-east-1`
- `api_port` — default `3000`
- `lambda_port` — default `3001`
- `localstack_image` — default `localstack/localstack:4`
- `log_dir` — default `logs`
- `architecture` — `arm64` or `x86_64`; auto-detected from `platform.machine()` if omitted
- `build_args`, `start_api_args`, `start_lambda_args` — extra CLI args

**Pytest (`pyproject.toml` `[tool.pytest.ini_options]`):**
- Suppresses `DeprecationWarning` from `testcontainers.*`

**Linting / Formatting:**
- `ruff >= 0.15.2` — linter and formatter (no separate `.ruff.toml`; config would live in `pyproject.toml` if added)
- `ty >= 0.0.18` — type checker (Astral's ty; **not** mypy/pyright); does **not** support `# type: ignore[...]`

**Build:**
- `pyproject.toml` — single source of truth; `[build-system]` section uses hatchling
- `uv.lock` — lockfile committed to repo

## Platform Requirements

**Development:**
- Docker Desktop (macOS) or Docker Engine (Linux) — required at test time
- Python 3.13
- `uv` installed globally

**Production / Deployment:**
- Distributed as a Python wheel to PyPI (`pypi.org/project/samstack/`)
- Published via `uv build` + `uv publish` using `PYPI_TOKEN` GitHub Actions secret
- No runtime server; library-only package

---

_Stack analysis: 2026-04-23_

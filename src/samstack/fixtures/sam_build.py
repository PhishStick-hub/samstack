from __future__ import annotations

import json
from pathlib import Path

import pytest

from samstack._constants import (
    LOCALSTACK_ACCESS_KEY,
    LOCALSTACK_INTERNAL_URL,
    LOCALSTACK_SECRET_KEY,
)
from samstack._errors import SamBuildError
from samstack._process import run_one_shot_container
from samstack._xdist import (
    Role,
    StateKeys,
    wait_for_state_key,
    worker_role,
    write_error_for,
    write_state_file,
)
from samstack.fixtures._sam_container import DOCKER_SOCKET, _is_ci
from samstack.settings import SamStackSettings


def _add_gitignore_entry(project_root: Path, log_dir: str) -> None:
    gitignore = project_root / ".gitignore"
    entry = f"{log_dir}/"
    if gitignore.exists():
        content = gitignore.read_text()
        if entry in content.splitlines():
            return
        gitignore.write_text(content.rstrip("\n") + f"\n{entry}\n")
    else:
        gitignore.write_text(f"{entry}\n")


@pytest.fixture(scope="session")
def sam_env_vars(samstack_settings: SamStackSettings) -> dict[str, dict[str, str]]:
    """
    Default environment variables injected into all Lambda functions at runtime.

    Routes each AWS service to the correct local backend via per-service
    ``AWS_ENDPOINT_URL_<SERVICE>`` variables (boto3 >= 1.28):

    - S3, DynamoDB, SQS, SNS → LocalStack (``http://localstack:4566``)
    - Lambda → SAM local start-lambda (``http://sam-lambda:3001``) — so Lambda
      code that invokes another Lambda via ``boto3.client('lambda')`` hits the
      SAM runtime, not LocalStack.

    Override in your conftest.py to add function-specific vars:

        @pytest.fixture(scope="session")
        def sam_env_vars(sam_env_vars):
            sam_env_vars["MyFunction"] = {"MY_VAR": "value"}
            return sam_env_vars
    """
    return {
        "Parameters": {
            "AWS_ENDPOINT_URL_S3": LOCALSTACK_INTERNAL_URL,
            "AWS_ENDPOINT_URL_DYNAMODB": LOCALSTACK_INTERNAL_URL,
            "AWS_ENDPOINT_URL_SQS": LOCALSTACK_INTERNAL_URL,
            "AWS_ENDPOINT_URL_SNS": LOCALSTACK_INTERNAL_URL,
            "AWS_ENDPOINT_URL_LAMBDA": f"http://sam-lambda:{samstack_settings.lambda_port}",
            "AWS_DEFAULT_REGION": samstack_settings.region,
            "AWS_ACCESS_KEY_ID": LOCALSTACK_ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": LOCALSTACK_SECRET_KEY,
        }
    }


@pytest.fixture(scope="session")
def warm_functions(samstack_settings: SamStackSettings) -> list[str]:
    """
    List of Lambda function names to pre-warm before tests execute.

    Defaults to ``samstack_settings.warm_functions`` (from ``[tool.samstack]``
    in pyproject.toml). Override in your conftest.py to specify functions
    programmatically:

        @pytest.fixture(scope="session")
        def warm_functions() -> list[str]:
            return ["MyFuncA", "MyFuncB"]

    Behavior by service:

    - ``start-lambda``: empty list (default) sets ``--warm-containers EAGER``
      so SAM pre-creates containers for **all** functions (backward
      compatible). A non-empty list switches to ``LAZY`` and only the listed
      functions receive a synthetic ``invoke()`` before tests run.
    - ``start-api``: always runs ``LAZY``. Only functions present in both
      ``warm_functions`` and ``warm_api_routes`` receive a synthetic HTTP GET
      before tests run.
    """
    return samstack_settings.warm_functions


@pytest.fixture(scope="session")
def sam_build(
    samstack_settings: SamStackSettings,
    sam_env_vars: dict[str, dict[str, str]],
) -> None:
    """Run `sam build` in a one-shot Docker container. Runs once per test session.

    Under xdist: gw0 runs the build and writes a ``build_complete`` flag to
    shared state; gw1+ workers poll for the flag and proceed without
    re-running the build (timeout 300s).
    """
    role = worker_role()

    # === Worker path: wait for controller's build, skip build ===
    if role is Role.WORKER:
        wait_for_state_key(StateKeys.BUILD_COMPLETE, timeout=300)
        return

    # === Master / controller path: run sam build ===
    log_dir = samstack_settings.project_root / samstack_settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # Write env vars JSON to a path accessible inside the SAM container
    env_vars_path = log_dir / "env_vars.json"
    env_vars_path.write_text(json.dumps(sam_env_vars, indent=2))

    # Mount the project at its real host path so that Lambda containers
    # created by SAM via the Docker socket can also mount it — Docker Desktop
    # only shares /Users (and similar host paths), not paths inside containers.
    host_path = str(samstack_settings.project_root)
    skip_pull: list[str] = [] if _is_ci() else ["--skip-pull-image"]
    build_cmd = [
        "sam",
        "build",
        *skip_pull,
        "--template",
        samstack_settings.template,
        *samstack_settings.build_args,
    ]
    volumes = {
        host_path: {"bind": host_path, "mode": "rw"},
        DOCKER_SOCKET: {"bind": DOCKER_SOCKET, "mode": "rw"},
    }

    try:
        logs, exit_code = run_one_shot_container(
            image=samstack_settings.sam_image,
            command=build_cmd,
            volumes=volumes,
            working_dir=host_path,
            environment={"DOCKER_DEFAULT_PLATFORM": samstack_settings.docker_platform},
        )
        if exit_code != 0:
            if role is Role.CONTROLLER:
                write_error_for(
                    StateKeys.BUILD_COMPLETE,
                    f"sam build failed with exit code {exit_code}",
                )
            raise SamBuildError(logs=logs)
    except SamBuildError:
        raise
    except Exception as exc:
        if role is Role.CONTROLLER:
            write_error_for(StateKeys.BUILD_COMPLETE, f"sam build failed: {exc}")
        raise

    # Signal gw1+ that the build is complete
    if role is Role.CONTROLLER:
        write_state_file(StateKeys.BUILD_COMPLETE, True)

    if samstack_settings.add_gitignore:
        _add_gitignore_entry(samstack_settings.project_root, samstack_settings.log_dir)

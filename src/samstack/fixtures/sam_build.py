from __future__ import annotations

import json
from pathlib import Path

import pytest

from samstack._constants import LOCALSTACK_ACCESS_KEY, LOCALSTACK_SECRET_KEY
from samstack._errors import SamBuildError
from samstack._process import run_one_shot_container
from samstack.fixtures._sam_container import DOCKER_SOCKET
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

    Override in your conftest.py to add function-specific vars:

        @pytest.fixture(scope="session")
        def sam_env_vars(sam_env_vars):
            sam_env_vars["MyFunction"] = {"MY_VAR": "value"}
            return sam_env_vars
    """
    return {
        "Parameters": {
            "AWS_ENDPOINT_URL": "http://localstack:4566",
            "AWS_DEFAULT_REGION": samstack_settings.region,
            "AWS_ACCESS_KEY_ID": LOCALSTACK_ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": LOCALSTACK_SECRET_KEY,
        }
    }


@pytest.fixture(scope="session")
def sam_build(
    samstack_settings: SamStackSettings,
    sam_env_vars: dict[str, dict[str, str]],
) -> None:
    """
    Run `sam build` in a one-shot Docker container. Runs once per test session.

    The build output lands in {project_root}/.aws-sam/ and is reused by
    sam_api and sam_lambda_endpoint fixtures.
    """
    log_dir = samstack_settings.project_root / samstack_settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # Write env vars JSON to a path accessible inside the SAM container
    env_vars_path = log_dir / "env_vars.json"
    env_vars_path.write_text(json.dumps(sam_env_vars, indent=2))

    # Mount the project at its real host path so that Lambda containers
    # created by SAM via the Docker socket can also mount it — Docker Desktop
    # only shares /Users (and similar host paths), not paths inside containers.
    host_path = str(samstack_settings.project_root)
    build_cmd = ["sam", "build", "--skip-pull-image", "--template", samstack_settings.template, *samstack_settings.build_args]
    volumes = {
        host_path: {"bind": host_path, "mode": "rw"},
        DOCKER_SOCKET: {"bind": DOCKER_SOCKET, "mode": "rw"},
    }

    logs, exit_code = run_one_shot_container(
        image=samstack_settings.sam_image,
        command=build_cmd,
        volumes=volumes,
        working_dir=host_path,
        environment={"DOCKER_DEFAULT_PLATFORM": samstack_settings.docker_platform},
    )
    if exit_code != 0:
        raise SamBuildError(logs=logs)

    if samstack_settings.add_gitignore:
        _add_gitignore_entry(samstack_settings.project_root, samstack_settings.log_dir)

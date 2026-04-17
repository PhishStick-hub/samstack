"""
Pytest plugin entry point for samstack.

Registered via [project.entry-points."pytest11"] in pyproject.toml:
    samstack = "samstack.plugin"

This module registers all fixtures and provides the samstack_settings fixture
by reading [tool.samstack] from the child project's pyproject.toml.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from samstack.fixtures.localstack import (
    docker_network,
    docker_network_name,
    localstack_container,
    localstack_endpoint,
)
from samstack.fixtures.resources import (
    dynamodb_client,
    dynamodb_resource,
    dynamodb_table,
    make_dynamodb_table,
    make_s3_bucket,
    make_sns_topic,
    make_sqs_queue,
    s3_bucket,
    s3_client,
    s3_resource,
    sns_client,
    sns_topic,
    sqs_client,
    sqs_queue,
    sqs_resource,
)
from samstack.fixtures.sam_api import sam_api, sam_api_extra_args
from samstack.fixtures.sam_build import sam_build, sam_env_vars
from samstack.fixtures.sam_lambda import (
    lambda_client,
    sam_lambda_endpoint,
    sam_lambda_extra_args,
)
from samstack.mock.fixture import make_lambda_mock
from samstack.settings import SamStackSettings, load_settings

__all__ = [
    "docker_network",
    "docker_network_name",
    "dynamodb_client",
    "dynamodb_resource",
    "dynamodb_table",
    "lambda_client",
    "localstack_container",
    "localstack_endpoint",
    "make_dynamodb_table",
    "make_lambda_mock",
    "make_s3_bucket",
    "make_sns_topic",
    "make_sqs_queue",
    "s3_bucket",
    "s3_client",
    "s3_resource",
    "sam_api",
    "sns_client",
    "sns_topic",
    "sqs_client",
    "sqs_queue",
    "sqs_resource",
    "sam_api_extra_args",
    "sam_build",
    "sam_env_vars",
    "sam_lambda_endpoint",
    "sam_lambda_extra_args",
    "samstack_settings",
]


@pytest.fixture(scope="session")
def samstack_settings() -> SamStackSettings:
    """
    Load [tool.samstack] from the child project's pyproject.toml.

    samstack searches upward from the current working directory for pyproject.toml.
    Override this fixture to supply settings programmatically:

        @pytest.fixture(scope="session")
        def samstack_settings() -> SamStackSettings:
            return SamStackSettings(sam_image="public.ecr.aws/sam/build-python3.13")
    """
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.exists():
            return load_settings(parent)
    raise FileNotFoundError(
        "pyproject.toml not found. samstack requires [tool.samstack] in pyproject.toml."
    )

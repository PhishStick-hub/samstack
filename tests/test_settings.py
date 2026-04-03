from pathlib import Path

import pytest

from samstack.settings import SamStackSettings, load_settings


def test_defaults_applied(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.samstack]\nsam_image = "public.ecr.aws/sam/build-python3.13"\n'
    )
    settings = load_settings(tmp_path)
    assert settings.template == "template.yaml"
    assert settings.region == "us-east-1"
    assert settings.api_port == 3000
    assert settings.lambda_port == 3001
    assert settings.localstack_image == "localstack/localstack:4"
    assert settings.log_dir == "logs/sam"
    assert settings.build_args == []
    assert settings.add_gitignore is True
    assert settings.start_api_args == []
    assert settings.start_lambda_args == []
    assert settings.project_root == tmp_path


def test_overrides_applied(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("""
[tool.samstack]
sam_image = "public.ecr.aws/sam/build-python3.13"
region = "eu-west-1"
api_port = 8080
lambda_port = 8081
log_dir = "my-logs"
build_args = ["--use-container"]
add_gitignore = false
start_api_args = ["--debug"]
start_lambda_args = ["--debug"]
""")
    settings = load_settings(tmp_path)
    assert settings.region == "eu-west-1"
    assert settings.api_port == 8080
    assert settings.lambda_port == 8081
    assert settings.log_dir == "my-logs"
    assert settings.build_args == ["--use-container"]
    assert settings.add_gitignore is False
    assert settings.start_api_args == ["--debug"]
    assert settings.start_lambda_args == ["--debug"]


def test_missing_sam_image_raises(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.samstack]\n")
    with pytest.raises(ValueError, match="sam_image"):
        load_settings(tmp_path)


def test_missing_tool_samstack_section_raises(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
    with pytest.raises(ValueError, match="\\[tool\\.samstack\\]"):
        load_settings(tmp_path)


def test_settings_is_dataclass() -> None:
    s = SamStackSettings(sam_image="test-image")
    assert s.sam_image == "test-image"
    assert s.region == "us-east-1"

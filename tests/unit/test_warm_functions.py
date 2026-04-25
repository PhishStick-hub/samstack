"""Unit tests for warm_functions configuration, validation, and fixture wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

import samstack.plugin as plugin
from samstack.settings import SamStackSettings, load_settings


def test_warm_functions_defaults_to_empty_list() -> None:
    """Settings without warm_functions in TOML default to empty list."""
    s = SamStackSettings(sam_image="test-image")
    assert s.warm_functions == []


def test_warm_functions_default_in_load_settings(tmp_path: Path) -> None:
    """load_settings returns empty list when warm_functions not in TOML."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.samstack]\nsam_image = "public.ecr.aws/sam/build-python3.13"\n'
    )
    settings = load_settings(tmp_path)
    assert settings.warm_functions == []


def test_warm_functions_from_toml(tmp_path: Path) -> None:
    """warm_functions is parsed from TOML as a list of strings."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.samstack]\n"
        'sam_image = "public.ecr.aws/sam/build-python3.13"\n'
        'warm_functions = ["FuncA", "FuncB"]\n'
    )
    settings = load_settings(tmp_path)
    assert settings.warm_functions == ["FuncA", "FuncB"]


def test_warm_functions_empty_toml_list(tmp_path: Path) -> None:
    """Empty warm_functions list in TOML is valid."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.samstack]\n"
        'sam_image = "public.ecr.aws/sam/build-python3.13"\n'
        "warm_functions = []\n"
    )
    settings = load_settings(tmp_path)
    assert settings.warm_functions == []


def test_warm_functions_rejects_non_list(tmp_path: Path) -> None:
    """load_settings raises ValueError when warm_functions is not a list."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.samstack]\n"
        'sam_image = "public.ecr.aws/sam/build-python3.13"\n'
        'warm_functions = "not-a-list"\n'
    )
    with pytest.raises(ValueError, match="warm_functions must be a list"):
        load_settings(tmp_path)


def test_warm_functions_rejects_non_string_elements(tmp_path: Path) -> None:
    """load_settings raises ValueError when warm_functions contains non-string elements."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.samstack]\n"
        'sam_image = "public.ecr.aws/sam/build-python3.13"\n'
        'warm_functions = ["valid", 123]\n'
    )
    with pytest.raises(ValueError, match="warm_functions must contain only strings"):
        load_settings(tmp_path)


def test_warm_functions_in_plugin_all() -> None:
    """warm_functions is exported in plugin.__all__ and importable."""
    assert "warm_functions" in plugin.__all__, (
        "warm_functions not found in plugin.__all__"
    )
    assert hasattr(plugin, "warm_functions"), (
        "warm_functions not importable from samstack.plugin"
    )


def test_warm_containers_mode_empty_is_eager() -> None:
    """Empty warm_functions selects EAGER mode."""
    from samstack.fixtures.sam_lambda import _warm_containers_mode

    assert _warm_containers_mode([]) == "EAGER"


def test_warm_containers_mode_non_empty_is_lazy() -> None:
    """Non-empty warm_functions selects LAZY mode."""
    from samstack.fixtures.sam_lambda import _warm_containers_mode

    assert _warm_containers_mode(["FuncA"]) == "LAZY"
    assert _warm_containers_mode(["FuncA", "FuncB"]) == "LAZY"

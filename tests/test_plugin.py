"""Unit tests for samstack.plugin — settings discovery and re-export list."""

from __future__ import annotations

from pathlib import Path

import pytest

import samstack.plugin as plugin
from samstack.settings import SamStackSettings


def _write_pyproject(
    path: Path, sam_image: str = "public.ecr.aws/sam/build-python3.13"
) -> None:
    (path / "pyproject.toml").write_text(
        f'[tool.samstack]\nsam_image = "{sam_image}"\n'
    )


def test_find_settings_finds_pyproject_in_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_pyproject(tmp_path, "my-test-image")
    monkeypatch.chdir(tmp_path)
    settings = plugin._find_settings()
    assert isinstance(settings, SamStackSettings)
    assert settings.sam_image == "my-test-image"


def test_find_settings_finds_pyproject_in_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_pyproject(tmp_path, "parent-image")
    subdir = tmp_path / "sub" / "project"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    settings = plugin._find_settings()
    assert settings.sam_image == "parent-image"


def test_find_settings_raises_when_no_pyproject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # tmp_path is under /tmp/pytest-... — no pyproject.toml in that ancestor chain.
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="pyproject.toml"):
        plugin._find_settings()


def test_plugin_all_names_importable() -> None:
    for name in plugin.__all__:
        assert hasattr(plugin, name), (
            f"'{name}' in __all__ but not importable from samstack.plugin"
        )

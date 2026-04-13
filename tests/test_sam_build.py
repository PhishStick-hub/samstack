"""sam build succeeds and produces .aws-sam/ build directory."""

from __future__ import annotations

from samstack.settings import SamStackSettings


def test_build_produces_aws_sam_dir(
    sam_build: None, samstack_settings: SamStackSettings
) -> None:
    aws_sam_dir = samstack_settings.project_root / ".aws-sam"
    assert aws_sam_dir.exists(), f".aws-sam not found at {aws_sam_dir}"


def test_build_produces_build_dir(
    sam_build: None, samstack_settings: SamStackSettings
) -> None:
    build_dir = samstack_settings.project_root / ".aws-sam" / "build"
    assert build_dir.exists(), f".aws-sam/build not found at {build_dir}"

from __future__ import annotations

import dataclasses
import platform
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


def _detect_architecture() -> Literal["arm64", "x86_64"]:
    """Return 'arm64' on Apple Silicon / Linux ARM hosts, 'x86_64' otherwise.

    platform.machine() returns:
      - 'arm64'   on macOS ARM (Apple Silicon)
      - 'aarch64' on Linux ARM64
      - 'x86_64'  on Intel/AMD (macOS and Linux)
    """
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return "x86_64"


@dataclass(frozen=True)
class SamStackSettings:
    sam_image: str
    template: str = "template.yaml"
    region: str = "us-east-1"
    api_port: int = 3000
    lambda_port: int = 3001
    localstack_image: str = "localstack/localstack:4"
    log_dir: str = "logs"
    build_args: list[str] = field(default_factory=list)
    add_gitignore: bool = True
    start_api_args: list[str] = field(default_factory=list)
    start_lambda_args: list[str] = field(default_factory=list)
    warm_functions: list[str] = field(default_factory=list)
    project_root: Path = field(default_factory=Path.cwd)
    architecture: Literal["arm64", "x86_64"] = field(
        default_factory=_detect_architecture
    )

    @property
    def docker_platform(self) -> str:
        return "linux/arm64" if self.architecture == "arm64" else "linux/amd64"


def load_settings(project_root: Path) -> SamStackSettings:
    """Parse [tool.samstack] from pyproject.toml in project_root."""
    pyproject = project_root / "pyproject.toml"
    with pyproject.open("rb") as f:
        data = tomllib.load(f)

    tool = data.get("tool", {})
    if "samstack" not in tool:
        raise ValueError(
            "[tool.samstack] section not found in pyproject.toml. "
            "Add it to configure samstack."
        )

    cfg: dict[str, Any] = tool["samstack"]

    if not cfg.get("sam_image"):
        raise ValueError(
            "sam_image is required in [tool.samstack]. "
            'Example: sam_image = "public.ecr.aws/sam/build-python3.13"'
        )

    arch = cfg.get("architecture")
    if arch is not None and arch not in ("arm64", "x86_64"):
        raise ValueError(
            f"architecture must be 'arm64' or 'x86_64', got '{arch}'. "
            "Remove the field to auto-detect from the host machine."
        )

    if "warm_functions" in cfg:
        warm = cfg["warm_functions"]
        if not isinstance(warm, list):
            raise ValueError(
                f"warm_functions must be a list of strings, got {type(warm).__name__}"
            )
        for v in warm:
            if not isinstance(v, str):
                raise ValueError(
                    f"warm_functions must contain only strings, "
                    f"got element of type {type(v).__name__}"
                )

    # Let the dataclass field defaults be the single source of truth.
    # TOML already parses integers natively; list/bool/str fields pass through unchanged.
    known = {f.name for f in dataclasses.fields(SamStackSettings)} - {
        "sam_image",
        "project_root",
    }
    filtered = {k: v for k, v in cfg.items() if k in known}
    return SamStackSettings(
        sam_image=cfg["sam_image"], project_root=project_root, **filtered
    )

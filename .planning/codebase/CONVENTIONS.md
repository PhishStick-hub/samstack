# CONVENTIONS
_Last updated: 2026-04-23_

## Summary
The codebase uses Python 3.13 with strict type annotations enforced by `ty`, `ruff` for linting/formatting, and frozen dataclasses for immutable config. All modules use `from __future__ import annotations` for deferred evaluation. No comments except where `why` is non-obvious.

## Language and Toolchain

- **Python**: 3.13 minimum (`requires-python = ">=3.13"`)
- **Formatter/Linter**: `ruff` (no black, no flake8, no pylint)
- **Type Checker**: `ty` (not mypy or pyright)
- **Package Manager**: `uv` (no pip, no poetry)
- **Build Backend**: `hatchling`

## Type Annotations

- All modules start with `from __future__ import annotations` for PEP 563 deferred evaluation
- `collections.abc.Iterator` / `Callable` preferred over `typing.Generator` / `typing.Callable`
- `Literal["arm64", "x86_64"]` used for constrained string fields
- `TYPE_CHECKING` guard for boto3/Docker SDK types to avoid circular imports and heavy imports at runtime
- In unit test files: annotate mock parameters as `MagicMock` (not as the real boto3 type — ty flags missing mock attributes on real types)
- `cast()` is **never used** as a type workaround; prefer boto3-stubs overloads or typed local vars
- `ty` does **not** support `# type: ignore[...]` (mypy-only); refactor over escape hatches

## Dataclass Patterns

- `SamStackSettings` is a `frozen=True` dataclass — immutable after construction
- `field(default_factory=...)` for mutable defaults (`list[str]`, `Path.cwd`)
- Settings parsed from TOML; known field names validated against `dataclasses.fields()`

## Error Handling

- Custom exception hierarchy rooted at `SamStackError(Exception)`
- Each error stores structured fields (e.g., `SamBuildError.logs`, `SamStartupError.port`, `SamStartupError.log_tail`)
- `__init__` on each exception calls `super().__init__` with a human-readable message
- `contextlib.suppress` used in cleanup blocks where exceptions should be swallowed silently
- `warnings.warn` (with `stacklevel=2`) for non-fatal teardown failures

## Code Style

- No docstrings unless the function signature is ambiguous; one-line comments only where the `why` is non-obvious
- Functions kept small; `_run_sam_service` is the largest unit (~50 lines) and uses `@contextmanager`
- Immutability preferred: frozen dataclasses for config, new dicts instead of mutation (except `sam_env_vars` fixture which is explicitly mutable by design)
- `noqa: F401` used on `__init__.py` re-exports to suppress unused import lint warnings
- `noqa: S310` used on `urllib.request.urlopen` (URL from internal code, not user input)

## Import Organization

- Standard library first, then third-party, then local
- `from __future__ import annotations` always first line
- Docker SDK (`import docker`) imported lazily inside `run_one_shot_container` to avoid import-time failures if Docker is unavailable

## Configuration

Ruff configured in `pyproject.toml`:
- No separate `.ruff.toml` file
- `filterwarnings` suppresses `DeprecationWarning` from testcontainers in pytest output
- Dev dependencies in `[dependency-groups] dev` (not `[project.dependencies]`)

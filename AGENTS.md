# AGENTS.md

This file provides guidance to AI coding agents when working with code in this repository.

## Project summary

`samstack` is a pytest plugin that provides session-scoped fixtures for testing AWS Lambda functions locally. Everything runs inside Docker — SAM CLI, Lambda containers, and Floci (local AWS emulator). One shared Docker bridge network connects them all; everything is auto-cleaned by Ryuk at session end.

## Every change must pass

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
```

Run unit tests (fast, no Docker):
```bash
uv run pytest tests/unit/ tests/test_settings.py tests/test_process.py tests/test_errors.py tests/test_plugin.py -v
```

## Naming conventions

- Fixture files live in `src/samstack/fixtures/`. One file per subsystem (`floci.py`, `resources.py`, `sam_build.py`, `sam_api.py`, `sam_lambda.py`).
- Internal helpers are prefixed with `_` (`_connect_container_with_alias`, `_apply_emulator_configs`).
- Constants are `UPPER_CASE` and defined in `src/samstack/_constants.py`.
- Error classes are defined in `src/samstack/_errors.py` and re-exported from `src/samstack/__init__.py`.
- All public fixtures and classes are re-exported from `plugin.py` (the pytest11 entry point).

## Fixture design rules

1. **Session-scoped by default.** Docker containers start once per session, not per test. Use function-scoped fixtures only for test-isolated resource wrappers (`s3_bucket`, `dynamodb_table`, `sqs_queue`, `sns_topic`).
2. **Dependency via pytest DI.** Fixtures request other fixtures as parameters — never import them directly. The dependency graph is documented in `CLAUDE.md`.
3. **Cleanup via teardown, not `atexit`.** Session fixtures use `yield` with `finally` blocks. Function-scoped fixtures use `yield` + cleanup.
4. **Network aliases are canonical.** Every container on the Docker bridge network gets a DNS alias (`"floci"`, `"sam-api"`, `"sam-lambda"`). Lambda containers running inside SAM resolve these aliases to reach the emulator or invoke other Lambdas. Changing an alias is a breaking change — env vars and hardcoded URLs in multiple files must be updated together.
5. **Credentials are constants.** `FLOCI_ACCESS_KEY` and `FLOCI_SECRET_KEY` (both `"test"`) are defined once in `_constants.py`. Never hardcode them in individual files.

## Settings changes

`SamStackSettings` is a **frozen** dataclass in `src/samstack/settings.py`. Adding a field means:
1. Add it to the dataclass with a default (unless it's `sam_image`, the only required field).
2. Verify `load_settings()` passes it through from TOML — the `known` set auto-filters fields, but check behavior for non-trivial types.
3. Update `tests/test_settings.py` if it has a default worth asserting.
4. Update `README.md` in the configuration table.
5. Update `CLAUDE.md` if it changes the fixture dependency graph.

## Adding a new resource fixture pattern

The pattern in `resources.py` for each service (S3, DynamoDB, SQS, SNS):
1. A **session-scoped boto3 client** fixture (`{service}_client`) depending on `floci_endpoint` + `samstack_settings`.
2. A **session-scoped boto3 resource** fixture (`{service}_resource`) if the service has a resource API.
3. A **session-scoped factory** (`make_{service}_{type}`) that creates uniquely-named resources and cleans them all up on teardown.
4. A **function-scoped convenience fixture** (`{service}_{type}`) that creates one fresh resource per test.

The wrapper class (in `src/samstack/resources/`) wraps the boto3 client/resource with a high-level API and exposes `.client` as an escape hatch.

## Migrating emulator backends

When swapping the local AWS emulator (e.g. LocalStack → Floci):
1. Change the dependency in `pyproject.toml` and run `uv sync`.
2. Create the new container fixture file (e.g. `fixtures/floci.py`), mirroring the old one's structure.
3. Update all imports and references: `_constants.py`, `_errors.py`, `plugin.py`, `__init__.py`, `resources.py`, `sam_build.py`, `sam_lambda.py`, `mock/fixture.py`.
4. Update all DNS alias strings (appears in `floci.py` network connection, `sam_build.py` env vars, `mock/fixture.py` hardcoded URL).
5. Update `CLAUDE.md` fixture graph, networking docs, and constant names.
6. Update `README.md` — search for old name across the whole file; no partial replacements.
7. Run `uv run ruff check . && uv run ruff format --check . && uv run ty check`.
8. Run full integration suite with `uv run pytest tests/ -v --timeout=300`.

## Type checking

`ty` does **not** support `# type: ignore[...]`. Avoid `cast()` as a workaround. In test files, annotate mock parameters as `MagicMock` — real boto3 types cause `ty` to flag missing mock attributes.

## Commit conventions

- `feat!:` for breaking changes (major version bump)
- `feat:` for new features (minor bump)
- `fix:` for user-facing bug fixes (patch bump)
- `chore:`, `ci:`, `docs:`, `test:`, `refactor:` — no version bump

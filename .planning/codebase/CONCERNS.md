# CONCERNS
_Last updated: 2026-04-23_

## Summary
The codebase is well-structured with few obvious concerns. The most significant issues are the multi_lambda test suite isolation requirement (manual CLI discipline needed), the SAM env-var propagation gotcha (silent key dropping), and the Docker-in-Docker networking complexity that is platform-specific.

## Technical Debt

### Multi-Lambda Test Isolation (Manual Discipline Required)
`tests/multi_lambda/` must be run with `uv run pytest tests/multi_lambda/ -v` — not as part of the root `tests/` session. The root `conftest.py` blocks it via `pytest_ignore_collect`, but this protection only works when pytest collects from the root. If a developer runs `uv run pytest .` from the repo root, they will get the block. However, any CI configuration that runs suites separately must know this constraint. The isolation mechanism works, but requires documentation discipline.

### SAM `env_vars.json` Timing Constraint
`make_lambda_mock` **must be resolved before `sam_build` runs** — documented in CLAUDE.md and enforced by making `_mock_b_session` `autouse=True`. This is a hidden ordering constraint: if a user forgets `autouse=True` or calls `make_lambda_mock` after `sam_build`, the mock env vars will be silently missing from the Lambda container.

### `sam_env_vars` Mutation Pattern
The `sam_env_vars` fixture is mutable by design (conftest overrides mutate the dict in-place). This is intentional but unusual — it is the only place in the codebase where mutation is preferred over immutability. The pattern is documented but could surprise contributors.

## Known Limitations

### SAM Env-Var Propagation Gotcha (Breaking Behavior)
`sam local` silently drops env-var keys that are not declared in `Environment.Variables` in the SAM template. Keys passed via `--env-vars` JSON are treated as *overrides*, not additions. Consumer Lambda templates must declare every key with an empty string default. This is a SAM CLI limitation, not a samstack bug — but it causes silent failures that are hard to diagnose.

### Multi-Lambda Suite Session Conflict
Running `uv run pytest tests/` (all tests) will collect `tests/multi_lambda/` only when explicitly targeted. The `pytest_ignore_collect` guard works, but this means the multi_lambda suite is never run by a plain `uv run pytest tests/ -v` unless the developer knows to target it separately. CI must run two separate pytest invocations to cover both suites.

### Docker-in-Docker on Linux
`host.docker.internal` is not available by default on Linux. The `_extra_hosts()` function adds `host.docker.internal:host-gateway` on non-Darwin platforms. This works on most Linux Docker setups but may fail in unusual Docker configurations (e.g., rootless Docker, Podman). The workaround is platform-detected at runtime.

### Ryuk and Lambda Container Cleanup
SAM creates Lambda runtime containers via the Docker socket — these are not tracked by testcontainers/Ryuk. The `docker_network` fixture teardown stops and removes all containers connected to the network before destroying it, which is the cleanup mechanism. If a test is killed mid-run (SIGKILL), orphaned Lambda containers may remain. Developers should run `docker ps -a` to check after crashes.

### `sam build` Output Volume Mount
The project is mounted at its **real host path** (not `/var/task`) so that Lambda containers created by SAM receive volume paths that Docker Desktop can resolve. This means the `project_root` path must be accessible and identical inside the Docker context. On macOS this works via Docker Desktop file sharing; on Linux it works natively. Remote Docker daemons (e.g., Docker on a VM) would break this assumption.

## Platform-Specific Concerns

| Concern | Darwin (macOS) | Linux |
|---------|---------------|-------|
| `host.docker.internal` | Available via Docker Desktop | Added via `--add-host host.docker.internal:host-gateway` |
| `_extra_hosts()` | Returns `{}` | Returns `{"host.docker.internal": "host-gateway"}` |
| Architecture auto-detection | `platform.machine()` → `arm64` or `x86_64` | `platform.machine()` → `aarch64` or `x86_64` |
| `--skip-pull-image` | Always added (dev) | Skipped in CI (`CI` env var set) |

## TODO / FIXME Items

No `TODO`, `FIXME`, `HACK`, or `XXX` comments found in the source or test files. The codebase is comment-minimal by convention — non-obvious decisions are documented in CLAUDE.md rather than inline.

## Areas for Potential Improvement

- **No `pytest-cov` / coverage tracking** — the library has good test breadth but no enforced coverage gate in CI
- **`run_one_shot_container` lazy Docker import** — `import docker` inside the function body avoids import-time failures but makes the dependency less visible; could be moved to a dedicated module
- **`sam_api` / `sam_lambda` fixture duplication** — both follow the same `_run_sam_service` pattern; the duplication is intentional (different subcommands, ports, wait modes) but the setup code is structurally identical
- **`tests/fixtures/multi_lambda/tests/mocks/mock_b/handler.py` inlines `spy_handler`** — done to avoid PyPI resolution during `sam build` in repo's own tests; real users use `from samstack.mock import spy_handler as handler`; the inlining creates a maintenance risk if `spy_handler` logic changes

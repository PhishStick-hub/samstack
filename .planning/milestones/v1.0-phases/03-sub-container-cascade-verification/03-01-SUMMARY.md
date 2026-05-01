# 03-01 SUMMARY — Extend crash test with hard sub-container assertion

## What was built
- Upgraded `_write_subprocess_session()` signature to accept `fixture_dir: Path` keyword-only parameter
- New generated conftest embeds absolute path to hello_world fixture, provides `samstack_settings` pointing at it
- New generated test `test_invoke_lambda_then_stall` invokes Lambda via `requests.get(f"{sam_api}/hello")` then stalls 120s
- Added `_poll_containers_gone()` module-level helper that polls `containers.list(all=True, filters={"name": name_prefix})`
- Replaced the print-based `cascade_note` observation with `assert sub_containers_gone` (30s timeout)
- Caller now passes `fixture_dir=Path.cwd() / "tests" / "fixtures" / "hello_world"` and uses `--timeout=180`
- Parent wait increased to 60s (was 5s) to allow full SAM bootstrap + Lambda invocation before SIGKILL

## Decisions implemented
- D-03: Hard-assert containers removed (not just stopped)
- D-04: Crash path timeout 30s
- D-05: macOS skip preserved via existing pytestmark
- D-06: TEST-03 upgraded from observation to assertion
- D-08: HTTP GET /hello for Lambda invocation

## Self-Check: PASSED
- `uv run python -c "import ast; ast.parse(...)"` — syntax valid
- `uv run ruff check tests/integration/test_ryuk_crash.py` — clean
- All acceptance criteria met (grep checks for function definitions, fixture references, timeout values)

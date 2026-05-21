# Code Review — feat: per-function warm container control (3b51e02)

## Executive Assessment

The commit introduces a useful, well-scoped feature: selective per-function warm-container pre-warming for both `start-lambda` (boto3 invoke) and `start-api` (HTTP GET). The architecture is consistent with the existing fixture-overridable pattern, documentation is thorough, and the integration tests use a sound UUID identity marker to verify warm-container behavior.

**Overall grade: B+**. The feature is solid, but the test suite contains a **high-severity false-confidence test** and a **medium-severity documentation inconsistency** that could mislead users about backward-compatibility behavior. A few extraction refactors improve testability without changing runtime semantics.

---

## Ranked Issues

### HIGH

1. **Bogus unit test (`test_sam_lambda_warm_containers_logic`) tested inline Python, not production code.**
   - **File:** `tests/unit/test_warm_functions.py`
   - **Problem:** The test hardcoded the same `"LAZY" if warm_fns else "EAGER"` expression that lives in `sam_lambda_endpoint`. It gave the illusion of coverage while being decoupled from the actual fixture. Changing the fixture logic would not break this test.
   - **Fix:** Extract `_warm_containers_mode(...)` as a pure function in `sam_lambda.py` and unit-test it directly. Remove the inline-logic test.

### MEDIUM

2. **Misleading `warm_functions` fixture docstring.**
   - **File:** `src/samstack/fixtures/sam_build.py`
   - **Problem:** Claims "An empty list (the default) means no pre-warming — backward compatible with existing behavior." For `start-lambda`, an empty list actually triggers `EAGER` (SAM pre-warms **all** functions). The README table is correct; the fixture docstring contradicts it.
   - **Fix:** Rewrite docstring to explain the asymmetric behavior across `start-lambda` and `start-api`.

3. **Crash-test false-positive risk.**
   - **File:** `tests/integration/test_warm_crash.py`
   - **Problem:** If the subprocess pytest session fails before creating any `sam_` containers, the post-SIGKILL assertion passes vacuously (zero containers === "cleaned up").
   - **Fix:** Assert that `sam_` containers exist **before** sending SIGKILL.

4. **Fragile `Path.cwd()` assumption in crash test.**
   - **File:** `tests/integration/test_warm_crash.py`
   - **Problem:** `fixture_dir = Path.cwd() / "tests" / "fixtures" / "warm_check"` breaks if pytest is invoked from a subdirectory.
   - **Fix:** Derive path from `__file__`.

### LOW

5. **Trivial dataclass field-access tests.**
   - **File:** `tests/unit/test_warm_functions.py`
   - **Problem:** `test_warm_functions_fixture_returns_settings_value` and `test_warm_functions_empty_fixture_returns_empty` test `settings.warm_functions == [...]`, which is just dataclass attribute access with no fixture logic involved.
   - **Fix:** Removed.

6. **Fixture logic not directly testable (sam_api route filtering).**
   - **File:** `src/samstack/fixtures/sam_api.py`
   - **Problem:** The dict comprehension `{k: v for k, v in warm_api_routes.items() if k in warm_functions}` lives inside the `sam_api` generator fixture, making it unreachable for unit tests.
   - **Fix:** Extract `_filter_warm_routes(...)` pure function and add coverage.

---

## Refactoring Plan & Execution

| Order | File | Change | Validation |
|---|---|---|---|
| 1 | `src/samstack/fixtures/sam_build.py` | Rewrite `warm_functions` docstring to accurately describe EAGER/LAZY asymmetry. | `ruff check`, `ty check` |
| 2 | `src/samstack/fixtures/sam_lambda.py` | Extract `_warm_containers_mode(...)` pure function; type as `Literal["LAZY", "EAGER"]`. | `ruff check`, `ty check`, pytest |
| 3 | `src/samstack/fixtures/sam_api.py` | Extract `_filter_warm_routes(...)` pure function. | `ruff check`, `ty check`, pytest |
| 4 | `tests/unit/test_warm_functions.py` | Remove bogus inline-logic test and trivial tests; add real tests for `_warm_containers_mode`. | pytest |
| 5 | `tests/unit/test_sam_api_warm.py` | New file: tests for `_filter_warm_routes`. | pytest |
| 6 | `tests/integration/test_warm_crash.py` | Add pre-kill container assertion; replace `Path.cwd()` with `Path(__file__)`-relative path. | `ruff check`, `ty check` |

All steps executed. No runtime behavior changed.

---

## Final Summary

- **Tests:** 107 → 110 unit tests. Removed 3 low-value/bogus tests; added 5 real ones.
- **Coverage gaps closed:** `warm_containers` mode selection, API route filtering.
- **Quality gates:** `ruff check .`, `ruff format --check .`, `ty check`, and full unit-test suite all pass.
- **Remaining risks:**
  - Integration crash test still relies on a fixed 15-second sleep; consider polling for container creation to reduce flakiness on slow CI runners.
  - `_pre_warm_functions` hardcodes 120-second boto3 timeouts with no override mechanism. Acceptable for now, but may need configurability if users run very large Lambdas.
  - `warm_functions` list is not deduplicated; duplicates cause redundant pre-warm invocations. Harmless but wasteful.

---

*Review completed.*

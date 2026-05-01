---
phase: 10-sam-api-lambda-xdist-awareness
reviewed: 2026-05-01T12:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - src/samstack/fixtures/sam_api.py
  - tests/unit/test_xdist_sam_api.py
  - src/samstack/fixtures/sam_lambda.py
  - tests/unit/test_xdist_sam_lambda.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-05-01T12:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the xdist-awareness implementation for `sam_api` and `sam_lambda_endpoint` fixtures. Both fixtures follow an identical, well-structured pattern: the controller (master/gw0) starts the container and optionally writes the endpoint to shared state; gw1+ workers poll a state file for the endpoint and yield it without any Docker calls.

The implementation is consistent, test coverage is thorough across all three paths (master, gw0, gw1+), and generator lifecycle is properly managed. No critical issues or security concerns found. One resource-management issue (unclosed HTTP response) and a few minor quality notes.

---

## Warnings

### WR-01: Unclosed HTTP response in `_pre_warm_api_routes`

**File:** `src/samstack/fixtures/sam_api.py:47`
**Issue:** `urllib.request.urlopen()` returns an HTTP response object, but the result is never closed. When the pre-warm request succeeds (HTTP 2xx), the response body is left unread and unclosed, leaking a socket connection until the garbage collector runs. While this only happens once per session and the volume is trivially small, proper resource management should close the response to avoid file-descriptor leaks and `ResourceWarning` in debug modes.

**Fix:**
```python
import contextlib

# Line 47 — replace:
urllib.request.urlopen(url, timeout=10.0)  # noqa: S310

# with:
with contextlib.closing(urllib.request.urlopen(url, timeout=10.0)):  # noqa: S310
    pass
```

Alternatively, use `urllib.request.urlopen` in a `with` block and read or discard the response:
```python
try:
    with urllib.request.urlopen(url, timeout=10.0) as resp:  # noqa: S310
        resp.read()  # consume body to allow connection reuse
except urllib.error.HTTPError:
    pass
```

---

## Info

### IN-01: Magic number for HTTP timeout

**File:** `src/samstack/fixtures/sam_api.py:47`
**Issue:** The pre-warm HTTP timeout `10.0` is a bare magic number. Consider extracting to a module-level constant or retrieving it from `SamStackSettings` for consistency with the rest of the configuration.

**Fix:** Define `_PRE_WARM_HTTP_TIMEOUT = 10.0` at module level, or add a `pre_warm_timeout` field to `SamStackSettings` (defaulting to 10.0).

---

### IN-02: Broad `except Exception` in `_pre_warm_functions`

**File:** `src/samstack/fixtures/sam_lambda.py:56`
**Issue:** The `except Exception` clause catches all exceptions, including `KeyboardInterrupt` and `SystemExit`. While this is intentional (any boto3 failure should surface as a `SamStartupError`), a bare `except Exception` that doesn't re-raise `KeyboardInterrupt`/`SystemExit` can mask intentional process termination signals. In practice boto3 won't raise these, but a comment documenting the intent would help future readers.

**Fix:** Add a comment above the except line:
```python
except Exception as exc:  # catch-all: any boto3 failure is a startup error
```

---

### IN-03: `Any` type annotation on boto3 client in `_pre_warm_functions`

**File:** `src/samstack/fixtures/sam_lambda.py:41`
**Issue:** The local `client` variable is annotated as `client: Any`, but the module already imports `LambdaClient` from `mypy_boto3_lambda` under `TYPE_CHECKING` (line 12). Using `LambdaClient` would provide better IDE support and catch type errors at static-check time.

**Fix:**
```python
from typing import TYPE_CHECKING, Any, Literal, cast

# Then on line 41, replace:
client: Any = boto3.client(...)

# with:
client = cast("LambdaClient", boto3.client(...))
```

This uses `cast` with a forward-reference string (works with `from __future__ import annotations`) and avoids importing `LambdaClient` at runtime.

---

_Reviewed: 2026-05-01T12:00:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_

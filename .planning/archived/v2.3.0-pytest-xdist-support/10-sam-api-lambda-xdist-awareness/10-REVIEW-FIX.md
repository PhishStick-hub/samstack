---
phase: 10-sam-api-lambda-xdist-awareness
fixed_at: 2026-05-01T01:23:53+02:00
review_path: .planning/phases/10-sam-api-lambda-xdist-awareness/10-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 10: Code Review Fix Report

**Fixed at:** 2026-05-01T01:23:53+02:00
**Source review:** .planning/phases/10-sam-api-lambda-xdist-awareness/10-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (`critical_warning`): 1
- Fixed: 1
- Skipped: 0

## Fixed Issues

### WR-01: Unclosed HTTP response in `_pre_warm_api_routes`

**Files modified:** `src/samstack/fixtures/sam_api.py`
**Commit:** 6c91594
**Applied fix:** Wrapped `urllib.request.urlopen()` call in `contextlib.closing()` to ensure the HTTP response is properly closed, preventing socket connection leaks. Added `import contextlib` at module level. The `with` block uses `pass` since the pre-warm only needs to trigger the connection — any HTTP response (2xx/4xx/5xx) counts as success, and the existing exception handlers remain unchanged.

---

_Fixed: 2026-05-01T01:23:53+02:00_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_

---
status: partial
phase: 12-integration-testing-ci-docs-benchmarking
source: [12-VERIFICATION.md]
started: 2026-05-01T12:00:00Z
updated: 2026-05-01T12:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Run xdist basic integration tests with `-n 2`
expected: 4 tests pass (test_get_hello_from_sam_api, test_post_hello_writes_to_s3, test_lambda_direct_invoke, test_xdist_shared_localstack). No worker errors or timeouts.
command: `uv run pytest tests/xdist/test_basic.py -v -n 2 --timeout=300`
requires: Docker daemon, SAM image pull, LocalStack container startup (~2-3 min)
result: [pending]

### 2. Run resource parallelism tests with `-n 4`
expected: 4 tests pass (S3, DynamoDB, SQS, SNS). No cross-worker interference. No ConnectionRefusedError or teardown races.
command: `uv run pytest tests/xdist/test_resource_parallelism.py -v -n 4 --timeout=300`
requires: Docker daemon, 4 workers sharing one LocalStack instance
result: [pending]

### 3. Run crash recovery test (Linux only)
expected: Test passes (1 passed). Subprocess exits non-zero, output contains "failed", does NOT contain `docker.errors` or `connection refused`.
command: `uv run pytest tests/xdist/test_crash/test_crash.py -v --timeout=300`
requires: Linux + Docker-in-Docker with Ryuk enabled. macOS skips.
result: [pending]

### 4. Run benchmark script
expected: Outputs speedup table with Configuration/Time/Speedup columns. Speedup > 1.0x for parallel configs.
command: `uv run python scripts/benchmark.py`
requires: Docker for integration tests. ~5-15 min (4 sequential runs).
result: [pending]

### 5. Verify no dangling Docker containers after crash test
expected: Zero containers and zero networks from crash test session. Ryuk reaper cleaned up.
command: `docker ps -a --filter "label=org.testcontainers.session-id"` and `docker network ls --filter "name=samstack"`
requires: Docker socket access
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps

#!/usr/bin/env python3
"""Benchmark samstack test suite with and without pytest-xdist.

Measures wall-clock execution time of the integration test suite
under sequential (baseline), -n 2, -n 4, and -n auto configurations.
Outputs a table with speedup factors.

Usage:
  uv run python scripts/benchmark.py
"""

from __future__ import annotations

import subprocess
import sys
import time

# Integration tests (Docker-requiring tests — skip unit tests and xdist suite)
# Excludes test_ryuk_sam_labels.py: checks container labels by session ID —
# incompatible with xdist where gw0 creates containers with a different
# testcontainers session than gw1+ workers.
TEST_TARGETS = [
    "tests/test_sam_api.py",
    "tests/test_sam_lambda.py",
    "tests/test_sam_build.py",
    "tests/test_localstack_integration.py",
    "tests/test_subcontainer_teardown.py",
    "tests/integration/",
]

# Configurations to benchmark
CONFIGS = [
    ("baseline", []),
    ("-n 2", ["-n", "2"]),
    ("-n 4", ["-n", "4"]),
    ("-n auto", ["-n", "auto"]),
]

TIMEOUT = 300


def run_suite(extra_args: list[str]) -> tuple[float, int]:
    """Run the integration test suite and return (elapsed_seconds, exit_code)."""
    cmd = [
        "uv",
        "run",
        "pytest",
        *TEST_TARGETS,
        "-v",
        "--timeout",
        str(TIMEOUT),
        *extra_args,
    ]
    start = time.perf_counter()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT * 2,  # generous timeout for slower CI
    )
    elapsed = time.perf_counter() - start
    return elapsed, result.returncode


def main() -> None:
    print("=" * 60)
    print("samstack xdist benchmark")
    print("=" * 60)
    print()

    results: dict[str, tuple[float, int]] = {}
    for name, args in CONFIGS:
        print(f"Running {name}... ", end="", flush=True)
        try:
            elapsed, code = run_suite(args)
            results[name] = (elapsed, code)
            status = "OK" if code == 0 else f"FAIL ({code})"
            print(f"{elapsed:.1f}s ({status})")
        except subprocess.TimeoutExpired:
            print("TIMEOUT")
            results[name] = (TIMEOUT * 2, -1)
        except Exception as exc:
            print(f"ERROR: {exc}")
            results[name] = (0.0, -1)

    baseline_s = results.get("baseline", (0.0, 0))[0]
    if baseline_s <= 0:
        print("ERROR: baseline failed — cannot compute speedups")
        sys.exit(1)

    print()
    print(f"{'Configuration':<14} {'Time (s)':>10} {'Speedup':>10}")
    print("-" * 36)
    for name in ["baseline", "-n 2", "-n 4", "-n auto"]:
        elapsed, code = results.get(name, (0.0, -1))
        speedup = baseline_s / elapsed if elapsed > 0 else 0.0
        exit_label = "" if code == 0 else f" (exit {code})"
        print(f"{name:<14} {elapsed:>9.1f}s {speedup:>9.2f}x{exit_label}")


if __name__ == "__main__":
    main()

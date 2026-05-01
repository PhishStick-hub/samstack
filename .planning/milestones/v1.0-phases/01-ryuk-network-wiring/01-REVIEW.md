---
phase: 01-ryuk-network-wiring
reviewed: 2026-04-23T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - src/samstack/fixtures/localstack.py
  - tests/unit/test_docker_network.py
  - tests/integration/test_ryuk_crash.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-23T00:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the Ryuk network-wiring implementation: the `docker_network` and `localstack_container` session fixtures, their unit test suite, and the crash-cleanup integration test.

The core logic is sound. The Ryuk registration path (`Reaper.get_instance()` then socket send), the label injection on network creation, and the teardown ordering (disconnect containers before removing the network) are all correct. The integration test strategy — spawning a subprocess pytest session, SIGKILLing it, and polling Docker for network removal — is the right approach for this kind of crash-cleanup guarantee.

Three warnings and three info items were identified. The most actionable warning is a race condition in the integration test's network-discovery step: the test polls Docker 3 seconds after subprocess launch and searches by label, which can find networks from concurrent samstack test runs (including the parent pytest process itself). The remaining warnings are an unchecked `get_wrapped_container()` return value in `_connect_container_with_alias` and a teardown gap in `_stop_network_container` where a successful `container.stop()` does not log but a failed one does.

---

## Warnings

### WR-01: Integration test network-discovery can match networks from other concurrent pytest sessions

**File:** `tests/integration/test_ryuk_crash.py:101-109`

**Issue:** After the subprocess is spawned, the test queries Docker for all networks with the label `org.testcontainers.session-id` and takes `[0]` — the first match. If the parent pytest process (or a parallel CI job) has its own `docker_network` fixture active at the same time, `samstack_networks` will contain more than one entry. The test would then pick the wrong network, assert on the wrong name, and potentially declare victory for a network that was never registered with the subprocess's Ryuk instance. Even in the single-session case the subprocess's own `SESSION_ID` differs from the parent's, so the label alone is insufficient to identify which network belongs to the subprocess.

**Fix:** Filter by a name prefix that is unique to the subprocess. Because `docker_network_name` already generates `samstack-{uuid8}`, filter by both label and name prefix, or — better — read the network name from the subprocess's stdout rather than querying Docker:

```python
# Option A: name-prefix filter (safe in single-machine concurrency)
samstack_networks = docker_client.networks.list(
    filters={"label": "org.testcontainers.session-id", "name": "samstack-"}
)
# Still use [0] but the risk is now a concurrent samstack run, not the parent.

# Option B: read network name from subprocess stdout (most robust)
# In the subprocess test, print the fixture value:
#   def test_stall(docker_network: str) -> None:
#       print(f"SAMSTACK_NETWORK={docker_network}", flush=True)
#       time.sleep(60)
#
# In the integration test, read it back:
stdout_lines = proc.stdout.read().decode(errors="replace").splitlines()
# (read in a thread with a timeout before SIGKILL)
network_name = next(
    line.split("=", 1)[1]
    for line in stdout_lines
    if line.startswith("SAMSTACK_NETWORK=")
)
```

---

### WR-02: `_stop_network_container` swallows the disconnect when stop/remove succeed

**File:** `src/samstack/fixtures/localstack.py:33-46`

**Issue:** When `container.stop()` and `container.remove()` succeed, the function returns silently — correct. But when they raise, the `except` block only calls `network.disconnect(container, force=True)` inside `contextlib.suppress(Exception)`, meaning the disconnect attempt is also silently eaten. This is intentional for teardown resilience. However, after a successful `container.stop()` + `container.remove()`, the function never explicitly disconnects the container from the network before removal. Docker removes container network endpoints when the container is removed, so this is not a functional bug — but if `container.remove(force=True)` itself is what fails (e.g., container is still in use), the disconnect fallback fires correctly.

The real concern: the `except` block calls `network.disconnect(container, force=True)` passing the **container object** as the first argument. The Docker SDK `network.disconnect()` accepts either a container ID string or a container object. Passing the object is valid with `docker-py`, but it is worth confirming the SDK version used accepts this form.

**Fix:** No code change required if the docker-py version in use accepts container objects. Add a comment to make the intent explicit:

```python
with contextlib.suppress(Exception):
    # Pass container object directly — docker-py accepts Container or id str.
    network.disconnect(container, force=True)
```

If there is any doubt about SDK compatibility, use `container.id` explicitly:
```python
with contextlib.suppress(Exception):
    network.disconnect(container.id, force=True)
```

---

### WR-03: `_poll_until_gone` timeout of 5 s may be too short on slow CI

**File:** `tests/integration/test_ryuk_crash.py:116`

**Issue:** Ryuk's default reconnection interval is 1 second and it may take a few seconds to detect the lost connection and act. On a loaded CI runner the total latency (SIGKILL detected → Ryuk acts → Docker removes network) can exceed 5 seconds. The test will then falsely fail with "Ryuk did not clean it up."

**Fix:** Increase the timeout to at least 10–15 seconds and document the rationale:

```python
gone = _poll_until_gone(docker_client, network_name, timeout=15.0, interval=0.5)
```

And update the assertion message to match:
```python
assert gone, (
    f"Docker network '{network_name}' still exists 15 s after SIGKILL. "
    "Ryuk did not clean it up. Verify TESTCONTAINERS_RYUK_DISABLED is not set."
)
```

---

## Info

### IN-01: `docker_network` fixture accesses `Reaper._socket` — private attribute coupling

**File:** `src/samstack/fixtures/localstack.py:86-87`

**Issue:** `Reaper._socket` is a private attribute of the testcontainers `Reaper` class. Its name, type, and semantics are not guaranteed stable across testcontainers releases. A future testcontainers upgrade could rename or restructure it, causing a silent `AttributeError` that gets swallowed by the outer `except Exception`.

**Fix:** Add a version pin comment and a unit test assertion that confirms the attribute exists at import time, so a testcontainers upgrade that removes it is caught loudly at test time rather than silently at runtime:

```python
# Relies on testcontainers internals (Reaper._socket).
# If this breaks after a testcontainers upgrade, update to use the new
# public API or replicate the filter registration logic.
if Reaper._socket is not None:
    Reaper._socket.send(...)
```

Consider wrapping the attribute access in `getattr` with a clear warning if missing:
```python
sock = getattr(Reaper, "_socket", None)
if sock is not None:
    sock.send(f"network=name={docker_network_name}\r\n".encode())
```

---

### IN-02: Integration test subprocess stdout/stderr are not consumed — subprocess may deadlock on large output

**File:** `tests/integration/test_ryuk_crash.py:88-92`

**Issue:** The subprocess is created with `stdout=subprocess.PIPE, stderr=subprocess.PIPE` but neither pipe is read before `proc.wait()` is called at line 113. If the subprocess emits more output than the OS pipe buffer allows (typically 64 KB on Linux), it will block on a write to stdout/stderr and never reach the `time.sleep(60)`. `proc.wait()` after SIGKILL drains nothing and returns immediately, but the stall may not occur — the 3-second sleep may find no network because the subprocess never reached the fixture setup step.

**Fix:** Either discard output to avoid buffering, or use a thread to drain it:

```python
# Simplest fix — discard output:
proc = subprocess.Popen(
    ["uv", "run", "pytest", str(session_dir), "-v", "--timeout=120"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

# Or capture for diagnostics on failure:
import threading

stdout_chunks: list[bytes] = []
stderr_chunks: list[bytes] = []

def _drain(pipe: object, buf: list[bytes]) -> None:
    for chunk in iter(lambda: pipe.read(4096), b""):  # type: ignore[attr-defined]
        buf.append(chunk)

threading.Thread(target=_drain, args=(proc.stdout, stdout_chunks), daemon=True).start()
threading.Thread(target=_drain, args=(proc.stderr, stderr_chunks), daemon=True).start()
```

---

### IN-03: Magic number `3` (seconds) for subprocess startup wait lacks a named constant or comment

**File:** `tests/integration/test_ryuk_crash.py:96`

**Issue:** `time.sleep(3)` is explained by an inline comment but the value `3` is not configurable or documented as a minimum bound. If the machine is slow (or a new dependency added to samstack increases session startup time), the sleep may expire before the network is created.

**Fix:** Extract to a named constant at module level with a comment:

```python
# Generous startup window — docker_network runs at session start and
# completes in < 1 s on a warm Docker daemon; 5 s covers slow CI runners.
_SUBPROCESS_STARTUP_WAIT_S: float = 5.0

# ... later:
time.sleep(_SUBPROCESS_STARTUP_WAIT_S)
```

---

_Reviewed: 2026-04-23T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

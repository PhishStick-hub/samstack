# Phase 3 Research: Sub-Container Cascade Verification

**Phase:** 03 — Sub-Container Cascade Verification
**Date:** 2026-04-25

<domain_summary>
## What We're Verifying

When `_teardown_network()` removes the Docker bridge network (normal exit) or Ryuk removes it (crash), SAM Lambda runtime sub-containers — spawned by the SAM CLI container via Docker-in-Docker — must be cleaned up. These sub-containers are NOT labeled with `org.testcontainers.session-id` (SAM CLI creates them directly via Docker socket, outside testcontainers' lifecycle), so Ryuk cannot clean them up directly. The cascade hypothesis is: when the network is removed, Docker force-disconnects attached containers, and those containers are then either stopped/removed by Docker itself or by the SAM CLI container's teardown.

Phase 3 turns the Phase 1/2 observation (`cascade_note` print) into a hard assertion.
</domain_summary>

<findings>
## Research Findings

### 1. Docker Network Removal Cascade Behavior

**What happens when a bridge network is removed while containers are still attached:**

Docker's network driver (`bridge`) will **force-disconnect** all attached containers before removing the network. This is observable:

```python
network.remove()  # Docker internally: disconnect all containers → remove network
```

However, Docker does **NOT** automatically stop or remove the containers. They transition to having no network attachment but remain in `running` state. The relevant Docker daemon issue ([moby/moby #23302](https://github.com/moby/moby/issues/23302)) confirms: "Removing a network does not stop containers still attached to it."

**Implication for Phase 3:** The `containers.list(filters={"network": network_name})` filter is state-dependent. Immediately after `network.remove()`, containers may still appear as `running` but with no network attachment. The `network` filter will return empty once Docker daemon reconciles the state. This means the assertion needs a polling loop with enough timeout for Docker daemon to process the disconnect event.

### 2. `_teardown_network` Normal Exit Path

In `localstack.py:49-59`, the normal exit path:
```python
def _teardown_network(network, name):
    network.reload()
    for container in network.containers:
        _stop_network_container(network, container)  # stop + remove
    network.remove()
```

This iterates containers on the network at the moment of teardown. For SAM Lambda sub-containers:
- **If the SAM CLI container is still running** (teardown order: SAM → LocalStack → network), the Lambda sub-container is still attached. It gets stopped and removed by `_stop_network_container`.
- **If the SAM CLI container has already stopped** (it got its own disconnect + stop in `_run_sam_service`'s `finally`), SAM CLI's teardown may have already stopped the Lambda sub-container with LAZY warm containers.

**Edge case:** If SAM API fixture teardown (disconnect + stop) happens BEFORE `_teardown_network` fire, the Lambda sub-container is already exiting when `_teardown_network` iterates. The sub-container may be in `exited` state, not `removed`. `_stop_network_container` calls `container.stop()` + `container.remove(force=True)`, which cleans up exited containers.

**Verification timing:** The assertion must run AFTER the full session teardown completes. For normal exit, this means in a post-session hook or a separate polling step.

### 3. Ryuk Crash Path Timing

**How Ryuk detects and acts on SIGKILL:**

1. SIGKILL is delivered to the pytest process (instant)
2. The TCP connection between the pytest process and the Ryuk container breaks
3. Ryuk detects the broken connection (via `select`/`epoll` — typically 1-5 seconds)
4. Ryuk runs its network cleanup filter: removes all networks matching `name=<registered_name>`
5. Docker removes the network, force-disconnecting attached containers

**Total latency:** 5-15 seconds in practice (tested in Phase 1 TEST-03 with 15s timeout). The 30s timeout suggested in D-04 is conservative and covers:
- CPU contention on CI runners
- Docker daemon load
- SAM CLI container (also SIGKILLed — PID namespace sharing means the subprocess SIGKILL cascades to its Docker child process)
- Docker async cleanup after network removal

**SAM CLI container fate:** When the pytest subprocess is SIGKILLed, the Docker container running SAM CLI is also killed (it's a child process in the same PID namespace or gets cleaned up by Ryuk's session cleanup). The SAM CLI process death may or may not trigger its own cleanup of Lambda sub-containers before Ryuk removes the network.

**Critical timing insight:** The assertion should first verify the network is gone (Phase 1 D-10 is already covered), then separately poll for sub-container removal. These are two distinct Docker operations.

### 4. SAM LAZY Warm Containers Lifecycle

With `--warm-containers LAZY` (the samstack default):
- A Lambda runtime container is created on first invocation
- It stays alive for a period after invocation (typically 10-15 seconds on idle)
- SAM CLI sends a shutdown signal on its own exit

**Implication for crash test:** The subprocess must:
1. Start SAM API (creates SAM CLI container)
2. Invoke Lambda via HTTP (creates Lambda sub-container on network)
3. Sleep briefly (2-3s) to ensure Lambda container exists
4. SIGKILL the subprocess (SAM CLI container dies, Lambda sub-container orphaned)

**Implication for normal teardown test:** The test must:
1. Invoke Lambda (creates sub-container)
2. Let the test function exit normally
3. Session teardown runs the fixture chain: SAM API disconnect+stop → LocalStack disconnect+stop → `_teardown_network` → network remove
4. After the full session ends, poll Docker for sub-containers

### 5. Docker SDK Query Mechanisms

**Option A: `containers.list(filters={"network": network_name})`**
- Returns containers attached to the named network at query time
- After network removal: returns empty list immediately (containers are disconnected)
- This is the correct filter for "are there any containers still attached to this network"

**Option B: `network.containers` (from `client.networks.get(name)`)**
- Requires the network to still exist (404 after removal)
- Not useful for post-removal verification

**Option C: `containers.list(filters={"name": "sam_"})`**
- Filters by container name prefix (SAM CLI creates Lambda containers with `sam_` prefix)
- Useful as a secondary check when the network is already gone

**Recommended for Phase 3:** Use filter A before network removal, then filter C after network removal to catch containers that existed on the network but are now disconnected. The most precise assertion: "no containers with `sam_` prefix remain after cleanup" — this catches SAM Lambda sub-containers regardless of network attachment state.

### 6. Subprocess Crash Test: SAM Session Requirements

The existing TEST-03 subprocess session is minimal (only `docker_network`). To create Lambda sub-containers, the subprocess needs:

```python
# Required fixtures for SAM + Lambda invocation:
# 1. samstack_settings → SamStackSettings with hello_world project_root
# 2. docker_network (already standard)
# 3. localstack_container (Lambda code references localstack DNS alias)
# 4. sam_env_vars → injects TEST_BUCKET for Lambda handler
# 5. sam_build → builds the Lambda code package
# 6. sam_api → starts SAM API (exposes /hello endpoint)
```

**For the crash test subprocess:** The `_write_subprocess_session()` function must write a conftest that includes all these fixtures. The subprocess test file should:
1. Use `sam_api` fixture to get the endpoint
2. Call `requests.get(f"{sam_api}/hello")` to trigger Lambda + create sub-container
3. Sleep briefly (2-3s) to ensure sub-container exists
4. Stall indefinitely (so SIGKILL arrives while SAM + Lambda are running)

**Dependency:** `sam_build` does NOT depend on `localstack_container` (per CLAUDE.md architecture). But Lambda invocation via HTTP requires LocalStack to be running (the Lambda handler resolves `AWS_ENDPOINT_URL_S3` → `localstack:4566`). So the subprocess conftest must include `localstack_container` even though `sam_build` doesn't need it.

### 7. Normal Teardown Test: Approach Options

**Option 1: Inline test in existing session** — Add a test to `tests/` top-level that uses existing `sam_api` fixture, invokes Lambda, records current sub-container count, and lets the test end. A separate session fixture asserts cleanup.

**Option 2: Separate test file with post-session hook** — Create `tests/test_subcontainer_cascade.py` with a `@pytest.fixture(scope="session", autouse=True)` that records Docker state before and after the session.

**Option 3: Subprocess test (mirror crash test)** — Spawn a subprocess that runs a full SAM session, invoke Lambda, exit cleanly, then poll Docker from the parent.

**Recommended:** Option 2 (post-session hook). It's the simplest — no subprocess management, uses existing session fixtures, and the hook fires after all fixtures teardown (including `_teardown_network`).

**But:** The `sam_api` fixture yields the API URL. When teardown runs, it disconnects+stops the SAM CLI container. Lambda sub-containers may already be gone by the time `_teardown_network` fires, depending on SAM CLI's own teardown behavior. This is actually what we're testing — so the assertion must run AFTER the session teardown chain completes.

### 8. Platform-Specific Considerations

**Linux (CI):**
- Crash test: Ryuk reliably detects SIGKILL connection drops. Tested in Phase 1 TEST-03.
- Normal teardown: `_teardown_network` runs `network.remove()` which is synchronous.
- Docker daemon is native — no VM layer delay.

**macOS (Docker Desktop):**
- Crash test: SKIP — Docker Desktop's TCP proxy does not propagate SIGKILL connection drops to Ryuk in the Linux VM. D-05.
- Normal teardown: Runs on macOS — `_teardown_network` uses Docker API, which works through Docker Desktop's TCP proxy.
- Docker daemon runs in a Linux VM; VM CPU contention may affect cleanup timing.

**CI (GitHub Actions):**
- `_is_ci()` returns True → SAM uses `--skip-pull-image` is NOT added (the negation logic in `build_sam_args()`)
- Wait, actually looking at the code: `skip_pull: list[str] = [] if _is_ci() else ["--skip-pull-image"]` — so on CI, the skip_pull list is EMPTY, meaning images ARE pulled. This is correct for CI where images aren't cached.
- CI runners have limited resources; timeout tolerances should account for slower Docker operations.

### 9. Docker SDK Client Connection in Subprocess

The crash test's parent process uses `docker.from_env()` to connect to the Docker daemon. The subprocess uses Docker indirectly (through testcontainers for `docker_network`). The parent must be able to query the subprocess's containers.

**Key insight:** Both parent and subprocess connect to the same Docker daemon. The parent's `docker_client.containers.list(filters={"name": "sam_"})` will find the subprocess's Lambda sub-containers because Docker daemon is shared.

### 10. Race Condition: Container Removal vs Polling

After network removal, Docker daemon asynchronously processes container state transitions. A container may be:
1. `running` → still alive, network disconnected
2. `exited` → stopped but not removed
3. `removing` → Docker is removing it
4. Not found → fully removed

The assertion should accept that containers in state 3-4 are "gone" and treat state 1-2 as "still present." Use `containers.list(all=True)` to include exited containers, then filter by name prefix `sam_`.

**Polling strategy (mirrors `_poll_until_gone`):**
```python
def _poll_containers_gone(client, name_prefix, timeout, interval):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = client.containers.list(
            all=True, filters={"name": name_prefix}
        )
        if not remaining:
            return True
        time.sleep(interval)
    return False
```
</findings>

<constraints>
## Constraints for Planning

1. **No fixture code changes** — Phase 3 is verification-only. All existing fixtures (`_teardown_network`, `docker_network`, `localstack_container`, `sam_api`, `sam_lambda_endpoint`) are read-only.
2. **Gate on `ryuk_disabled`** — D-09 from Phase 1: all Ryuk-aware assertions use `testcontainers_config.ryuk_disabled`.
3. **Platform skip for crash path** — D-05: crash-path assertion skips on macOS (`sys.platform == "darwin"`). Normal teardown runs everywhere.
4. **Hard-assert removal, not just exit** — D-03: use `containers.list(all=True, filters={"name": "sam_"})` to assert zero containers remain, not just network-disconnected.
5. **Timeout tolerances** — Crash: 30s, Normal: 15s. These are the user's suggested values; CI testing may require adjustment.
6. **Same test patterns as Phase 1/2** — `pytestmark` module-level skip guards, Docker SDK `from_env()` client, polling loops, subprocess session pattern.
7. **Lambda invocation via HTTP** — Use `requests.get(f"{sam_api}/hello")` rather than `lambda_client.invoke`. Per CONTEXT.md specifics: "exercises a more complete sub-container creation that mirrors production use."
</constraints>

<verification_strategy>
## Verification Strategy

### Crash Path (Ryuk)
- Extend `test_ryuk_crash.py` → upgrade `_write_subprocess_session` to include full SAM session with `samstack_settings`, `localstack_container`, `sam_env_vars`, `sam_build`, `sam_api`
- Subprocess test: invoke Lambda via `requests.get(f"{sam_api}/hello")`, sleep 2-3s, stall
- Parent: SIGKILL → poll network gone (existing assert) → poll `sam_` containers gone (new assert, 30s timeout)
- Module skip: `ryuk_disabled or sys.platform == "darwin"`

### Teardown Path (Normal Exit)
- New test: `tests/integration/test_subcontainer_cascade.py` or within `test_ryuk_crash.py`
- Uses existing session fixtures (LocalStack only via integration conftest, or full SAM via separate conftest)
- Approach: session-scoped autouse fixture that records pre-test container count, invokes Lambda, ends the session normally, post-session hook polls for `sam_` containers
- Module skip: `ryuk_disabled` only (runs on macOS too)
</verification_strategy>

<common_pitfalls>
## Common Pitfalls

1. **Network filter after network removal returns empty** — Don't use `filters={"network": network_name}` after the network is gone. Use `filters={"name": "sam_"}` instead.
2. **Containers in 'exited' state** — Use `all=True` in `containers.list()` to include stopped containers. A stopped but not removed container is still "not cleaned up."
3. **SAM CLI container teardown order** — In the normal exit path, SAM API fixture's `finally` block runs before `_teardown_network`. The sub-container might already be stopped by SAM CLI, but should also be removed.
4. **Subprocess session performance** — The crash test subprocess now needs a full SAM build + LocalStack pull. This adds ~30-60 seconds to the test. Use `--skip-pull-image` in non-CI environments.
5. **Concurrent test sessions** — If multiple pytest sessions run concurrently, `filters={"name": "sam_"}` may match containers from other sessions. Use additional filtering (network name or timestamp) to isolate.
6. **Docker-in-Docker latency** — The SAM CLI container communicates with the Docker daemon via mounted socket. Container creation (Lambda sub-container) may take 1-3 seconds after invocation. Account for this in sleep timing.
</common_pitfalls>

<dependencies>
## Dependencies

- **Phase 1 (complete):** `docker_network` Ryuk wiring, `_teardown_network`, TEST-03 crash test pattern, `_poll_until_gone()` helper
- **Phase 2 (complete):** `test_ryuk_container_labels.py` — confirms main containers carry Ryuk labels; Phase 3's sub-containers do NOT carry these labels, making the cascade verification necessary
- **testcontainers library:** `LABEL_SESSION_ID`, `SESSION_ID`, `testcontainers_config.ryuk_disabled` — already imported across the codebase
- **Docker SDK:** `docker.from_env()`, `containers.list()`, `networks.get()`, `NotFound` — established patterns in Phase 1
- **hello_world fixture Lambda:** GET `/hello` → 200 for sub-container creation trigger
</dependencies>

<architectural_notes>
## Architectural Notes

### Why this matters

SAM CLI's local Lambda runtime creates containers via Docker-in-Docker. These containers are NOT managed by testcontainers — they lack Ryuk labels. If a pytest session crashes:
- Phase 1 ensures the network is cleaned up (Ryuk removes it)
- Phase 2 ensures the main containers (LocalStack, SAM CLI) are cleaned up
- Phase 3 ensures the Lambda sub-containers are cleaned up — the last piece of the "no leftovers" guarantee

### The cascade contract

The implicit contract Phase 3 verifies:
1. SAM CLI container manages its own sub-containers (stops them on shutdown)
2. Docker daemon disconnects sub-containers from the network when the network is removed
3. Disconnected sub-containers are eventually removed by Docker (or are acceptable in `exited` → `removed` transition)

If this verification fails, it means sub-containers linger after a crash, which is a leak that accumulates across test runs.
</architectural_notes>

<standard_stack>
## Standard Stack (for planning)

No new dependencies. The test code uses:
- `pytest` (already installed)
- `docker` SDK (already installed — `docker-py`)
- `requests` (already installed)
- `testcontainers` (already installed — `testcontainers[localstack]`)
- `subprocess`, `signal`, `time`, `sys`, `pathlib` (stdlib)
- `concurrent.futures` — stdlib (for polling with timeout)
</standard_stack>

<dont_hand_roll>
## Don't Hand-Roll

- Docker SDK container management — use `docker.from_env().containers.list()` and `network.remove()`, not raw Docker CLI subprocess calls
- Subprocess management — use `subprocess.Popen` with `os.kill(signal.SIGKILL)`, not shell scripts or docker CLI
- Polling — follow the existing `_poll_until_gone()` pattern in `test_ryuk_crash.py:71-85`; don't use while-true-sleep
</dont_hand_roll>

---

*Research completed: 2026-04-25*

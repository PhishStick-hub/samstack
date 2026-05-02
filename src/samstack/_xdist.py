"""xdist coordination primitives: shared state file, file locks, role detection.

Under pytest-xdist each worker is a separate Python process. samstack starts
expensive Docker infrastructure (LocalStack, SAM containers) exactly once per
session by electing the first worker (``gw0``) as controller and having all
other workers (``gw1+``) wait for shared state written to the filesystem.

Three roles are modelled explicitly via :class:`Role`:

- ``MASTER``    — no xdist; same process owns and tears down everything.
- ``CONTROLLER``— ``gw0``; under xdist, owns the shared infrastructure.
- ``WORKER``    — ``gw1+``; under xdist, consumes state written by ``gw0``.

Code that needs to discriminate "owns infra vs proxies infra" should use
:func:`worker_role`. Code only needs to know "should I write state?" via
``role is Role.CONTROLLER`` (master never writes state — there's no one
listening). The legacy :func:`is_controller` helper conflates MASTER + CONTROLLER
and remains only for backward-compatibility with existing call sites.

State-file invariants
~~~~~~~~~~~~~~~~~~~~~
- Writers hold ``state.lock`` (filelock) and write atomically via temp-file +
  ``os.replace``. POSIX guarantees the rename is atomic on the same filesystem.
- Readers do **not** hold the lock; they observe either the pre-write or
  post-write contents, never a torn read. This is safe given the atomic-rename
  invariant; it matters because :func:`wait_for_state_key` polls in a tight
  loop and lock contention would serialise all workers.
"""

from __future__ import annotations

import contextlib
import enum
import json
import os
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

import pytest
from filelock import FileLock, Timeout


# --- Role detection -----------------------------------------------------------


class Role(enum.Enum):
    """Execution role of the current process under (or without) pytest-xdist."""

    MASTER = "master"
    CONTROLLER = "controller"  # gw0 under xdist
    WORKER = "worker"  # gw1+


def get_worker_id() -> str:
    """Return the raw ``PYTEST_XDIST_WORKER`` env var, or ``"master"``."""
    return os.environ.get("PYTEST_XDIST_WORKER", "master")


def worker_role(worker_id: str | None = None) -> Role:
    """Return the :class:`Role` for ``worker_id`` (defaults to current process)."""
    if worker_id is None:
        worker_id = get_worker_id()
    if worker_id == "master":
        return Role.MASTER
    if worker_id == "gw0":
        return Role.CONTROLLER
    if worker_id.startswith("gw"):
        return Role.WORKER
    return Role.MASTER


def is_xdist_worker(worker_id: str | None = None) -> bool:
    """True if running under xdist (any ``gwN`` worker, controller or not)."""
    return worker_role(worker_id) in (Role.CONTROLLER, Role.WORKER)


def is_controller(worker_id: str | None = None) -> bool:
    """True if this process should run controller-side initialisation.

    This is ``True`` for both MASTER (no xdist) and CONTROLLER (gw0). It is
    intentionally coarse: most fixture bodies want to know "do I run the
    real init code?" The narrower question "should I write to the shared
    state file?" needs ``worker_role(...) is Role.CONTROLLER``.
    """
    return worker_role(worker_id) is not Role.WORKER


# --- Session state directory --------------------------------------------------


_session_uuid: str | None = None


def get_session_uuid() -> str:
    """Return a stable 8-char session id shared across all xdist workers."""
    global _session_uuid
    if _session_uuid is None:
        # Under xdist, all workers see the same PYTEST_XDIST_TESTRUNUID, so
        # they share a state directory. Outside xdist we fabricate one.
        xdist_uid = os.environ.get("PYTEST_XDIST_TESTRUNUID")
        _session_uuid = (xdist_uid or uuid.uuid4().hex)[:8]
    return _session_uuid


def get_state_dir() -> Path:
    """Return the per-session shared state directory, creating it if missing."""
    d = Path(tempfile.gettempdir()) / f"samstack-{get_session_uuid()}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- State file r/w -----------------------------------------------------------


_STATE_FILE_LOCK: FileLock | None = None


def _get_state_lock() -> FileLock:
    global _STATE_FILE_LOCK
    if _STATE_FILE_LOCK is None:
        _STATE_FILE_LOCK = FileLock(str(get_state_dir() / "state.lock"), timeout=10.0)
    return _STATE_FILE_LOCK


def read_state_file() -> dict[str, Any]:
    """Return the current shared state as a dict (empty if no file yet).

    Lock-free; safe because writes are atomic-rename. See module docstring.
    """
    state_path = get_state_dir() / "state.json"
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text())


def write_state_file(key: str, value: Any) -> None:
    """Atomically merge ``{key: value}`` into the shared state file."""
    with _get_state_lock():
        state = read_state_file()
        state[key] = value
        state_path = get_state_dir() / "state.json"
        fd, tmp_path = tempfile.mkstemp(dir=str(state_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f)
            os.replace(tmp_path, str(state_path))
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_path)
            raise


# --- State keys ---------------------------------------------------------------


class StateKeys:
    """Centralised state-file key names. One source of truth for the schema."""

    DOCKER_NETWORK = "docker_network"
    LOCALSTACK_ENDPOINT = "localstack_endpoint"
    SAM_API_ENDPOINT = "sam_api_endpoint"
    SAM_LAMBDA_ENDPOINT = "sam_lambda_endpoint"
    BUILD_COMPLETE = "build_complete"
    LEGACY_ERROR = "error"  # back-compat: pre-step-3 single-error slot

    @staticmethod
    def error_for(state_key: str) -> str:
        """Per-key error slot, so two failing controllers don't clobber."""
        return f"error_{state_key}"

    @staticmethod
    def worker_done(worker_id: str) -> str:
        """Marker each worker writes during teardown so gw0 knows when to stop."""
        return f"{worker_id}_done"

    @staticmethod
    def mock_spy_bucket(alias: str) -> str:
        return f"mock_spy_bucket_{alias}"


# --- Waiting on state keys ----------------------------------------------------


def wait_for_state_key(
    key: str,
    timeout: float = 120.0,
    poll_interval: float = 0.5,
) -> Any:
    """Block until ``key`` appears in shared state. Fail fast on errors.

    Watches three slots in priority order:

    1. ``error_{key}`` — failure recorded specifically for this state key.
    2. ``error``       — legacy global failure slot (pre-step-3 fixtures).
    3. ``key``         — success.

    Raises ``pytest.fail.Exception`` on timeout or recorded error.
    """
    per_key_error = StateKeys.error_for(key)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_state_file()
        if per_key_error in state:
            pytest.fail(f"gw0 failed while preparing '{key}': {state[per_key_error]}")
        if StateKeys.LEGACY_ERROR in state:
            pytest.fail(
                f"gw0 infrastructure startup failed: {state[StateKeys.LEGACY_ERROR]}"
            )
        if key in state:
            return state[key]
        time.sleep(poll_interval)
    pytest.fail(f"Timed out after {timeout}s waiting for gw0 to create '{key}'")


def write_error_for(state_key: str, message: str) -> None:
    """Record a controller-side failure for ``state_key`` so workers fail fast."""
    write_state_file(StateKeys.error_for(state_key), message)


# --- Infra lock (single-process re-entry guard) -------------------------------


_lock: FileLock | None = None
_lock_held = False


def acquire_infra_lock() -> bool:
    """Try to take the cross-process infra lock without blocking.

    Returns ``False`` if this process already holds it (re-entry) or another
    process holds it. ``True`` on first successful acquisition.
    """
    global _lock, _lock_held
    if _lock_held:
        return False
    _lock = FileLock(str(get_state_dir() / "infra.lock"), timeout=0)
    try:
        _lock.acquire(timeout=0)
    except Timeout:
        return False
    _lock_held = True
    return True


def release_infra_lock() -> None:
    """Release the cross-process infra lock; idempotent."""
    global _lock, _lock_held
    if _lock is not None:
        with contextlib.suppress(Exception):
            _lock.release()
    _lock = None
    _lock_held = False


# --- Worker-done coordination -------------------------------------------------


def wait_for_workers_done(timeout: float = 300.0) -> None:
    """Block until every ``gw1+`` worker has signalled completion.

    Called by the controller during teardown of *shared* infrastructure to
    guarantee no worker is still issuing requests against it. Workers signal
    completion by writing ``StateKeys.worker_done(worker_id)`` to shared state.

    No-op outside xdist or with a single worker.
    """
    worker_count_str = os.environ.get("PYTEST_XDIST_WORKER_COUNT")
    if not worker_count_str:
        return
    worker_count = int(worker_count_str)
    if worker_count <= 1:
        return

    expected = {StateKeys.worker_done(f"gw{i}") for i in range(1, worker_count)}
    deadline = time.monotonic() + timeout
    while expected and time.monotonic() < deadline:
        state = read_state_file()
        expected -= expected & set(state)
        if not expected:
            return
        time.sleep(0.5)
    if expected:
        pytest.fail(
            f"Timed out after {timeout}s waiting for workers to complete: {expected}"
        )


# --- Shared-session helper ----------------------------------------------------


T = TypeVar("T")
S = TypeVar("S")


@contextmanager
def xdist_shared_session(
    state_key: str,
    *,
    on_controller: Callable[[], "contextlib.AbstractContextManager[tuple[T, S]]"],
    on_worker: Callable[[S], T] = lambda v: v,  # type: ignore[assignment,return-value]
    timeout: float = 120.0,
    error_prefix: str | None = None,
    wait_for_workers_on_teardown: bool = False,
) -> Iterator[T]:
    """Coordinate a shared session-scoped resource across xdist workers.

    Encapsulates the controller/worker branching, state-file writes, error
    propagation, and (for workers) done-signalling that every shared fixture
    needs. Each fixture supplies:

    - ``on_controller`` — factory returning a context manager that, on enter,
      yields ``(user_resource, state_value)``: ``user_resource`` is what the
      fixture yields to tests; ``state_value`` is the JSON-serialisable handle
      written to shared state for workers to consume.
    - ``on_worker``     — maps the ``state_value`` read from shared state back
      to a ``user_resource`` (typically a lightweight proxy). Defaults to
      identity, useful when the state value *is* the resource (a URL string).
    - ``error_prefix``  — optional human-readable prefix prepended to the
      controller-side failure message before it's published to shared state.
      Workers see ``"<prefix>: <exception>"``; helpful when the exception type
      alone doesn't communicate which fixture failed.
    - ``wait_for_workers_on_teardown`` — when True, the CONTROLLER blocks on
      :func:`wait_for_workers_done` BEFORE its ``on_controller`` context
      exits. Use this for any controller-owned shared resource (LocalStack,
      SAM containers) that workers may still be calling at teardown — pytest
      finalises session-scoped fixtures in LIFO order, so a controller that
      finishes its assigned tests first would otherwise tear down shared
      infra while workers are still mid-test.

    Roles:

    - MASTER   — runs ``on_controller``, yields the resource, no state writes.
    - CONTROLLER — same as MASTER, plus writes ``state_key`` on success and
      ``error_{state_key}`` on failure.
    - WORKER   — waits for ``state_key`` (or fails fast on recorded errors),
      yields ``on_worker(state_value)``, signals ``worker_done`` on teardown.

    For controller-side teardown coordination (waiting for workers to finish
    before tearing down), use :func:`wait_for_workers_done` inside
    ``on_controller``'s ``__exit__`` path or in the depending fixture's
    teardown — kept out of this helper so the dependency graph stays explicit.
    """
    role = worker_role()
    if role is Role.WORKER:
        state_value = wait_for_state_key(state_key, timeout=timeout)
        try:
            yield on_worker(state_value)
        finally:
            with contextlib.suppress(Exception):
                write_state_file(StateKeys.worker_done(get_worker_id()), True)
        return

    # MASTER and CONTROLLER both run the real init. Only CONTROLLER writes
    # to shared state — MASTER has no audience.
    try:
        with on_controller() as (resource, state_value):
            if role is Role.CONTROLLER:
                write_state_file(state_key, state_value)
            try:
                yield resource
            finally:
                # Block teardown until every worker signals completion, so
                # we don't close the shared resource while a worker is still
                # talking to it. Has to live INSIDE on_controller's context
                # so we still hold the resource while we wait.
                if role is Role.CONTROLLER and wait_for_workers_on_teardown:
                    wait_for_workers_done()
    except Exception as exc:
        if role is Role.CONTROLLER:
            message = f"{error_prefix}: {exc}" if error_prefix else str(exc)
            with contextlib.suppress(Exception):
                write_error_for(state_key, message)
        raise

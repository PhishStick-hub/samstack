from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

_session_uuid: str | None = None
_state_lock = threading.Lock()
_lock: Any = None
_lock_held = False


def get_worker_id() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "master")


def is_xdist_worker(worker_id: str | None = None) -> bool:
    if worker_id is None:
        worker_id = get_worker_id()
    return worker_id != "master" and worker_id.startswith("gw")


def is_controller(worker_id: str | None = None) -> bool:
    if worker_id is None:
        worker_id = get_worker_id()
    return worker_id in ("master", "gw0")


def get_session_uuid() -> str:
    global _session_uuid
    if _session_uuid is None:
        _session_uuid = uuid.uuid4().hex[:8]
    return _session_uuid


def get_state_dir() -> Path:
    d = Path(tempfile.gettempdir()) / f"samstack-{get_session_uuid()}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_state_file() -> dict[str, Any]:
    state_path = get_state_dir() / "state.json"
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text())


def write_state_file(key: str, value: Any) -> None:
    with _state_lock:
        state = read_state_file()
        state[key] = value
        state_path = get_state_dir() / "state.json"
        state_path.write_text(json.dumps(state))


def wait_for_state_key(
    key: str,
    timeout: float = 120.0,
    poll_interval: float = 0.5,
) -> Any:
    import pytest

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_state_file()
        if "error" in state:
            pytest.skip(f"gw0 infrastructure startup failed: {state['error']}")
        if key in state:
            return state[key]
        time.sleep(poll_interval)
    pytest.skip(f"Timed out after {timeout}s waiting for gw0 to create '{key}'")


def acquire_infra_lock() -> bool:
    from filelock import FileLock, Timeout

    global _lock, _lock_held
    if _lock_held:
        return False

    lock_path = get_state_dir() / "infra.lock"
    _lock = FileLock(str(lock_path), timeout=0)
    try:
        _lock.acquire(timeout=0)
    except Timeout:
        return False
    _lock_held = True
    return True


def release_infra_lock() -> None:
    global _lock, _lock_held
    if _lock is not None:
        with contextlib.suppress(Exception):
            _lock.release()
    _lock = None
    _lock_held = False

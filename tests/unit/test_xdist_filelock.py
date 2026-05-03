from __future__ import annotations

from pathlib import Path

import pytest

from samstack._xdist import InfraLockError, infra_lock


def test_acquired_when_free(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    with infra_lock():
        lock_file = tmp_path / "infra.lock"
        assert lock_file.exists()


def test_raises_when_locked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Two separate FileLock instances on the same path — only first succeeds."""
    from filelock import FileLock

    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    lock_path = tmp_path / "infra.lock"

    lock1 = FileLock(str(lock_path), timeout=0)
    try:
        lock1.acquire(timeout=0)
        with pytest.raises(InfraLockError):
            with infra_lock():
                pass  # pragma: no cover
    finally:
        lock1.release()


def test_releases_on_exit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Lock is released when the context manager exits."""
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    with infra_lock():
        pass
    with infra_lock():
        lock_file = tmp_path / "infra.lock"
        assert lock_file.exists()

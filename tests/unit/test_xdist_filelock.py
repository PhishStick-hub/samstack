from __future__ import annotations

from pathlib import Path

import pytest

from samstack._xdist import acquire_infra_lock, get_state_dir, release_infra_lock


def test_acquire_returns_true(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    try:
        assert acquire_infra_lock() is True
    finally:
        release_infra_lock()


def test_acquire_fails_when_locked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    try:
        assert acquire_infra_lock() is True
        assert acquire_infra_lock() is False
    finally:
        release_infra_lock()


def test_release_allows_reacquire(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    assert acquire_infra_lock() is True
    release_infra_lock()
    try:
        assert acquire_infra_lock() is True
    finally:
        release_infra_lock()


def test_lock_file_at_expected_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    try:
        acquire_infra_lock()
        lock_file = tmp_path / "infra.lock"
        assert lock_file.exists()
    finally:
        release_infra_lock()


def test_acquire_from_different_instance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Two separate FileLock instances on the same path — only first succeeds."""
    from filelock import FileLock, Timeout

    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    lock_path = tmp_path / "infra.lock"

    # First instance acquires
    lock1 = FileLock(str(lock_path), timeout=0)
    try:
        lock1.acquire(timeout=0)
        # Second instance (separate object) should fail
        lock2 = FileLock(str(lock_path), timeout=0)
        with pytest.raises(Timeout):
            lock2.acquire(timeout=0)
    finally:
        lock1.release()

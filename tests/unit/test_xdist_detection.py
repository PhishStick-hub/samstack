from __future__ import annotations

import os

import pytest

from samstack._xdist import get_worker_id, is_controller, is_xdist_worker


def test_get_worker_id_master(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    assert get_worker_id() == "master"


def test_get_worker_id_gw0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    assert get_worker_id() == "gw0"


def test_get_worker_id_gw1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    assert get_worker_id() == "gw1"


def test_is_xdist_worker_master() -> None:
    assert is_xdist_worker("master") is False


def test_is_xdist_worker_gw0() -> None:
    assert is_xdist_worker("gw0") is True


def test_is_xdist_worker_gw1() -> None:
    assert is_xdist_worker("gw1") is True


def test_is_xdist_worker_defaults_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw2")
    assert is_xdist_worker() is True


def test_is_controller_master() -> None:
    assert is_controller("master") is True


def test_is_controller_gw0() -> None:
    assert is_controller("gw0") is True


def test_is_controller_gw1() -> None:
    assert is_controller("gw1") is False


def test_is_controller_defaults_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    assert is_controller() is True

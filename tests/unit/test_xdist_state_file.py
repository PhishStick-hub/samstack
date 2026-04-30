from __future__ import annotations

from pathlib import Path

import pytest

from samstack._xdist import (
    get_session_uuid,
    get_state_dir,
    read_state_file,
    wait_for_state_key,
    write_state_file,
)


def test_write_and_read_round_trip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    write_state_file("my_key", "my_value")
    result = read_state_file()
    assert result["my_key"] == "my_value"


def test_read_empty_returns_dict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    assert read_state_file() == {}


def test_write_preserves_existing_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    write_state_file("key_a", "value_a")
    write_state_file("key_b", "value_b")
    result = read_state_file()
    assert result["key_a"] == "value_a"
    assert result["key_b"] == "value_b"


def test_session_uuid_cached() -> None:
    a = get_session_uuid()
    b = get_session_uuid()
    assert a == b
    # Must be 8 hex chars
    assert len(a) == 8
    assert all(c in "0123456789abcdef" for c in a)


def test_state_dir_uses_uuid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    # Reset cached uuid so we get a fresh one tied to our tmp_path
    monkeypatch.setattr("samstack._xdist._session_uuid", None)
    d = get_state_dir()
    assert d.name.startswith("samstack-")
    uuid_part = d.name[len("samstack-") :]
    assert len(uuid_part) == 8
    assert all(c in "0123456789abcdef" for c in uuid_part)


def test_wait_for_state_key_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    write_state_file("ready", True)
    result = wait_for_state_key("ready", timeout=1.0)
    assert result is True


def test_wait_for_state_key_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    with pytest.raises(pytest.fail.Exception):
        wait_for_state_key("nonexistent", timeout=0.1)


def test_wait_for_state_key_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("samstack._xdist.get_state_dir", lambda: tmp_path)
    write_state_file("error", "boom")
    with pytest.raises(pytest.fail.Exception, match="boom"):
        wait_for_state_key("any", timeout=1.0)

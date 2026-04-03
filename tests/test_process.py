import socket
from pathlib import Path

import pytest

from samstack._errors import SamStartupError
from samstack._process import tail_log_file, wait_for_port


def test_tail_log_file_returns_last_n_lines(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("\n".join(str(i) for i in range(100)))
    tail = tail_log_file(log, lines=10)
    lines = tail.strip().splitlines()
    assert len(lines) == 10
    assert lines[-1] == "99"


def test_tail_log_file_missing_returns_empty(tmp_path: Path) -> None:
    result = tail_log_file(tmp_path / "nonexistent.log")
    assert result == ""


def test_wait_for_port_succeeds_when_port_open(tmp_path: Path) -> None:
    # bind a free port, then wait for it
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.listen(1)
    log = tmp_path / "test.log"
    try:
        wait_for_port("127.0.0.1", port, log_path=log, timeout=5.0)
    finally:
        srv.close()


def test_wait_for_port_raises_on_timeout(tmp_path: Path) -> None:
    log = tmp_path / "test.log"
    log.write_text("some log line")
    with pytest.raises(SamStartupError) as exc_info:
        wait_for_port("127.0.0.1", 19999, log_path=log, timeout=1.0, interval=0.2)
    assert "19999" in str(exc_info.value)
    assert "some log line" in str(exc_info.value)

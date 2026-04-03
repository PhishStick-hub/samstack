from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from samstack._errors import SamStartupError

if TYPE_CHECKING:
    from docker.models.containers import Container


def tail_log_file(path: Path, lines: int = 50) -> str:
    """Return the last *lines* lines of a log file, or '' if missing."""
    if not path.exists():
        return ""
    content = path.read_text(errors="replace")
    return "\n".join(content.splitlines()[-lines:])


def wait_for_port(
    host: str,
    port: int,
    log_path: Path,
    timeout: float = 120.0,
    interval: float = 0.5,
) -> None:
    """Block until *port* accepts TCP connections or raise SamStartupError."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            socket.create_connection((host, port), timeout=1.0).close()
            return
        except OSError:
            time.sleep(interval)
    raise SamStartupError(port=port, log_tail=tail_log_file(log_path))


def wait_for_http(
    host: str,
    port: int,
    log_path: Path,
    path: str = "/",
    timeout: float = 120.0,
    interval: float = 1.0,
) -> None:
    """Block until an HTTP GET returns any response (any status code).

    Unlike wait_for_port (TCP probe), this confirms the HTTP server is
    fully initialised and handling requests — not just that the port forwarder
    is listening.  Raises SamStartupError on timeout.
    """
    url = f"http://{host}:{port}{path}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2.0)  # noqa: S310
            return
        except urllib.error.HTTPError:
            # Any HTTP error (4xx/5xx) means the server is up
            return
        except (urllib.error.URLError, OSError):
            time.sleep(interval)
    raise SamStartupError(port=port, log_tail=tail_log_file(log_path))


def stream_logs_to_file(container: Container, log_path: Path) -> threading.Thread:
    """Stream Docker container stdout/stderr to *log_path* in a daemon thread.

    *container* is a Docker SDK container object (docker.models.containers.Container).
    """

    def _stream() -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with log_path.open("a") as f:
                for chunk in container.logs(stream=True, follow=True):
                    f.write(chunk.decode(errors="replace"))
                    f.flush()
        except Exception as exc:
            try:
                with log_path.open("a") as f:
                    f.write(f"\n[samstack] log streaming failed: {exc}\n")
            except Exception:
                pass

    t = threading.Thread(target=_stream, daemon=True)
    t.start()
    return t


def run_one_shot_container(
    image: str,
    command: str | list[str],
    volumes: dict[str, dict[str, str]],
    working_dir: str = "/var/task",
    network: str | None = None,
    environment: dict[str, str] | None = None,
) -> tuple[str, int]:
    """Run a container to completion. Returns (logs, exit_code)."""
    import docker as docker_sdk

    client = docker_sdk.from_env()
    kwargs: dict[str, Any] = {"network": network} if network else {}
    if environment:
        kwargs["environment"] = environment
    container = client.containers.run(
        image=image,
        command=command,
        volumes=volumes,
        working_dir=working_dir,
        detach=True,
        **kwargs,
    )
    try:
        result = container.wait()
        logs = container.logs().decode(errors="replace")
        return logs, result["StatusCode"]
    finally:
        container.remove(force=True)

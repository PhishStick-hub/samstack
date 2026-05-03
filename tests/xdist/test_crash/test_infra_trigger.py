"""Minimal test that forces gw0 to resolve Docker infrastructure.

Under xdist with the crash conftest (invalid sam_image), gw0's
Docker container startup fails. gw0 writes "error" to shared state.
gw1+ workers detect the error via wait_for_state_key and call pytest.fail().
"""

from __future__ import annotations


def test_trigger_docker_infra(sam_api: str) -> None:
    """Use sam_api to trigger Docker infrastructure resolution on gw0.

    Under the crash conftest with ``sam_image="nonexistent:latest"``,
    gw0's SAM build container fails to start, writing an error key.
    gw1+ workers detect this and exit cleanly via pytest.fail().
    """
    pass  # Never reached — gw0 fails during fixture setup

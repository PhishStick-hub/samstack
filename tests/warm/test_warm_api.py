"""Verify pre-warmed function stays warm across start-api HTTP requests."""

from __future__ import annotations

import pytest
import requests


@pytest.fixture(scope="session")
def warm_api_routes() -> dict[str, str]:
    return {"WarmCheckFunction": "/warm"}


def test_warm_across_http_requests(sam_api: str) -> None:
    """Two consecutive HTTP GET requests return the same instance_id (warm container)."""
    r1 = requests.get(f"{sam_api}/warm", timeout=10)
    assert r1.status_code == 200
    id1 = r1.json()["instance_id"]

    r2 = requests.get(f"{sam_api}/warm", timeout=10)
    assert r2.status_code == 200
    id2 = r2.json()["instance_id"]

    assert id1 == id2, f"Container was not warm: {id1} != {id2}"


def test_warm_api_returns_200(sam_api: str) -> None:
    """Pre-warmed API route responds successfully."""
    resp = requests.get(f"{sam_api}/warm", timeout=10)
    assert resp.status_code == 200
    assert "instance_id" in resp.json()

"""sam local start-api: HTTP requests via API Gateway."""

import requests


def test_get_hello_returns_200(sam_api: str) -> None:
    response = requests.get(f"{sam_api}/hello", timeout=10)
    assert response.status_code == 200


def test_get_hello_returns_message(sam_api: str) -> None:
    response = requests.get(f"{sam_api}/hello", timeout=10)
    body = response.json()
    assert body["message"] == "hello"


def test_unknown_path_returns_4xx(sam_api: str) -> None:
    response = requests.get(f"{sam_api}/nonexistent", timeout=10)
    # SAM local returns 403 (not 404) for routes not defined in the template
    assert response.status_code in (403, 404)

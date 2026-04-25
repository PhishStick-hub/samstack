"""Unit tests for _pre_warm_api_routes helper in sam_api.py."""

from __future__ import annotations

import http.client
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from samstack._errors import SamStartupError
from samstack.fixtures.sam_api import _pre_warm_api_routes


def test_pre_warm_api_empty_routes_is_noop():
    """Call with empty dict returns silently, urlopen never called."""
    mock_urlopen = MagicMock()

    with patch("samstack.fixtures.sam_api.urllib.request.urlopen", mock_urlopen):
        _pre_warm_api_routes("http://127.0.0.1:3000", {})

    mock_urlopen.assert_not_called()


def test_pre_warm_api_sends_get_to_each_route():
    """Each route receives a urlopen() call with correct full URL and timeout."""
    mock_urlopen = MagicMock()

    with patch("samstack.fixtures.sam_api.urllib.request.urlopen", mock_urlopen):
        _pre_warm_api_routes(
            "http://127.0.0.1:3000",
            {"FuncA": "/hello", "FuncB": "/world"},
        )

    assert mock_urlopen.call_count == 2
    mock_urlopen.assert_any_call("http://127.0.0.1:3000/hello", timeout=10.0)
    mock_urlopen.assert_any_call("http://127.0.0.1:3000/world", timeout=10.0)


def test_pre_warm_api_http_error_is_success():
    """HTTPError (4xx, 5xx) is swallowed — any HTTP response means the server is running."""
    mock_urlopen = MagicMock()
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "/hello", 500, "Internal Server Error", http.client.HTTPMessage(), None
    )

    with patch("samstack.fixtures.sam_api.urllib.request.urlopen", mock_urlopen):
        _pre_warm_api_routes("http://127.0.0.1:3000", {"FuncA": "/hello"})


def test_pre_warm_api_urlerror_raises_sam_startup_error():
    """URLError (connection refused, DNS failure) raises SamStartupError."""
    mock_urlopen = MagicMock()
    mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

    with patch("samstack.fixtures.sam_api.urllib.request.urlopen", mock_urlopen):
        with pytest.raises(SamStartupError) as exc_info:
            _pre_warm_api_routes("http://127.0.0.1:3000", {"FuncA": "/hello"})

    error = exc_info.value
    assert error.port == 0
    assert "Pre-warm HTTP request failed for function 'FuncA'" in error.log_tail
    assert "Connection refused" in error.log_tail


def test_pre_warm_api_oserror_raises_sam_startup_error():
    """OSError (socket timeout) raises SamStartupError."""
    mock_urlopen = MagicMock()
    mock_urlopen.side_effect = OSError("timed out")

    with patch("samstack.fixtures.sam_api.urllib.request.urlopen", mock_urlopen):
        with pytest.raises(SamStartupError) as exc_info:
            _pre_warm_api_routes("http://127.0.0.1:3000", {"FuncA": "/hello"})

    error = exc_info.value
    assert error.port == 0
    assert "Pre-warm HTTP request failed for function 'FuncA'" in error.log_tail
    assert "timed out" in error.log_tail


def test_pre_warm_api_logs_summary():
    """Summary line logged at info level before the request loop."""
    mock_urlopen = MagicMock()

    with (
        patch("samstack.fixtures.sam_api.urllib.request.urlopen", mock_urlopen),
        patch("samstack.fixtures.sam_api._logger") as mock_logger,
    ):
        _pre_warm_api_routes(
            "http://127.0.0.1:3000",
            {"FuncA": "/hello", "FuncB": "/world"},
        )

    mock_logger.info.assert_called_once_with("pre-warming %d API route(s)", 2)

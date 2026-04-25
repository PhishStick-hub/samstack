"""Unit tests for sam_api warm-container wiring."""

from __future__ import annotations

from samstack.fixtures.sam_api import _filter_warm_routes


def test_filter_warm_routes_returns_intersection() -> None:
    """Only routes whose function name is in warm_functions are kept."""
    routes = {"FuncA": "/a", "FuncB": "/b", "FuncC": "/c"}
    warm = ["FuncA", "FuncC"]
    assert _filter_warm_routes(routes, warm) == {"FuncA": "/a", "FuncC": "/c"}


def test_filter_warm_routes_empty_functions() -> None:
    """Empty warm_functions yields empty dict regardless of routes."""
    routes = {"FuncA": "/a"}
    assert _filter_warm_routes(routes, []) == {}


def test_filter_warm_routes_empty_routes() -> None:
    """Empty routes yields empty dict regardless of warm_functions."""
    assert _filter_warm_routes({}, ["FuncA"]) == {}


def test_filter_warm_routes_no_overlap() -> None:
    """No matching keys yields empty dict."""
    routes = {"FuncA": "/a"}
    assert _filter_warm_routes(routes, ["FuncB"]) == {}

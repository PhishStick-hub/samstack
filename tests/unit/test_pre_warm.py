"""Unit tests for _pre_warm_functions helper in sam_lambda.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.config import Config

from samstack._constants import LOCALSTACK_ACCESS_KEY, LOCALSTACK_SECRET_KEY
from samstack._errors import SamStartupError
from samstack.fixtures.sam_lambda import _pre_warm_functions


def test_pre_warm_empty_list_is_noop():
    """Call with empty list returns silently, no boto3 client created."""
    with patch("samstack.fixtures.sam_lambda.boto3.client") as mock_client:
        _pre_warm_functions("http://127.0.0.1:3001", [], "us-east-1")
        mock_client.assert_not_called()


def test_pre_warm_invokes_each_function():
    """Each function name receives an invoke() call with RequestResponse and b"{}"."""
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"StatusCode": 200}

    with patch("samstack.fixtures.sam_lambda.boto3.client", return_value=mock_lambda):
        _pre_warm_functions("http://127.0.0.1:3001", ["FuncA", "FuncB"], "us-east-1")

    assert mock_lambda.invoke.call_count == 2
    mock_lambda.invoke.assert_any_call(
        FunctionName="FuncA",
        InvocationType="RequestResponse",
        Payload=b"{}",
    )
    mock_lambda.invoke.assert_any_call(
        FunctionName="FuncB",
        InvocationType="RequestResponse",
        Payload=b"{}",
    )


def test_pre_warm_boto3_exception_raises_sam_startup_error():
    """When invoke() raises, a SamStartupError wraps it with function name."""
    mock_lambda = MagicMock()
    mock_lambda.invoke.side_effect = Exception("Connection refused")

    with patch("samstack.fixtures.sam_lambda.boto3.client", return_value=mock_lambda):
        with pytest.raises(SamStartupError) as exc_info:
            _pre_warm_functions("http://127.0.0.1:3001", ["FuncA"], "us-east-1")

    error = exc_info.value
    assert error.port == 0
    assert "Pre-warm invoke failed for function 'FuncA'" in error.log_tail
    assert "Connection refused" in error.log_tail


def test_pre_warm_function_error_raises_sam_startup_error():
    """When invoke() returns FunctionError, a SamStartupError wraps it."""
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"FunctionError": "Handled"}

    with patch("samstack.fixtures.sam_lambda.boto3.client", return_value=mock_lambda):
        with pytest.raises(SamStartupError) as exc_info:
            _pre_warm_functions("http://127.0.0.1:3001", ["FuncA"], "us-east-1")

    error = exc_info.value
    assert error.port == 0
    assert (
        "Pre-warm function 'FuncA' returned FunctionError='Handled'" in error.log_tail
    )


def test_pre_warm_success_silent_per_function():
    """Successful invoke with no FunctionError raises nothing."""
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"StatusCode": 200}

    with patch("samstack.fixtures.sam_lambda.boto3.client", return_value=mock_lambda):
        _pre_warm_functions("http://127.0.0.1:3001", ["FuncA"], "us-east-1")


def test_pre_warm_boto3_client_config():
    """Boto3 client is constructed with endpoint, region, credentials, and 120s timeout."""
    mock_lambda = MagicMock()
    mock_lambda.invoke.return_value = {"StatusCode": 200}
    mock_client_fn = MagicMock(return_value=mock_lambda)

    with patch("samstack.fixtures.sam_lambda.boto3.client", mock_client_fn):
        _pre_warm_functions("http://127.0.0.1:3001", ["FuncA"], "us-east-1")

    mock_client_fn.assert_called_once()
    call_kwargs = mock_client_fn.call_args.kwargs
    assert call_kwargs["endpoint_url"] == "http://127.0.0.1:3001"
    assert call_kwargs["region_name"] == "us-east-1"
    assert call_kwargs["aws_access_key_id"] == LOCALSTACK_ACCESS_KEY
    assert call_kwargs["aws_secret_access_key"] == LOCALSTACK_SECRET_KEY
    cfg = call_kwargs["config"]
    assert isinstance(cfg, Config)
    assert cfg.read_timeout == 120
    assert cfg.connect_timeout == 120

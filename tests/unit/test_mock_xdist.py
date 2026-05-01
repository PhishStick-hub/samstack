"""Unit tests for xdist-aware make_lambda_mock fixture."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from samstack.mock.fixture import LambdaMock, make_lambda_mock
from samstack.resources.s3 import S3Bucket


# ---------------------------------------------------------------------------
# Helper: invoke the fixture generator to get the _make factory function
# ---------------------------------------------------------------------------


def _get_make(
    make_s3_bucket: MagicMock,
    s3_client: MagicMock,
    sam_env_vars: dict[str, dict[str, str]] | None = None,
):
    """Invoke ``make_lambda_mock`` generator and return the _make factory."""
    if sam_env_vars is None:
        sam_env_vars = {}
    gen = make_lambda_mock(make_s3_bucket, s3_client, sam_env_vars)
    _make = next(gen)
    return _make


# ---------------------------------------------------------------------------
# TestMakeLambdaMockXdist — gw0 and gw1+ behavior
# ---------------------------------------------------------------------------


class TestMakeLambdaMockXdist:
    """gw0 and gw1+ behavior for make_lambda_mock._make inner function."""

    def test_gw0_creates_bucket_and_writes_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw0 worker: make_s3_bucket called, state key written, LambdaMock returned."""
        # Setup: mock make_s3_bucket returns a known bucket
        mock_s3_client = MagicMock()
        mock_bucket = S3Bucket(name="mock-mock-a-abc12345", client=mock_s3_client)

        make_s3_bucket = MagicMock(return_value=mock_bucket)
        sam_env_vars: dict[str, dict[str, str]] = {}

        mock_write = MagicMock()
        mock_wait = MagicMock()

        monkeypatch.setattr("samstack.mock.fixture.get_worker_id", lambda: "gw0")
        monkeypatch.setattr("samstack.mock.fixture.is_controller", lambda w: True)
        monkeypatch.setattr("samstack.mock.fixture.write_state_file", mock_write)
        monkeypatch.setattr("samstack.mock.fixture.wait_for_state_key", mock_wait)

        # Execute
        _make = _get_make(make_s3_bucket, mock_s3_client, sam_env_vars)
        result = _make("TestFunc", alias="mock-a")

        # Assert: make_s3_bucket called with correct name
        make_s3_bucket.assert_called_once_with("mock-mock-a")

        # Assert: state key written
        mock_write.assert_called_once_with(
            "mock_spy_bucket_mock-a", "mock-mock-a-abc12345"
        )

        # Assert: gw1+ wait NOT called
        mock_wait.assert_not_called()

        # Assert: LambdaMock returned with correct name
        assert isinstance(result, LambdaMock)
        assert result.name == "mock-a"
        assert result.bucket is mock_bucket

    def test_gw1_reads_state_and_constructs_s3bucket(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ worker: wait_for_state_key called, S3Bucket constructed from name,
        make_s3_bucket NOT called."""
        # Setup
        mock_s3_client = MagicMock()
        shared_bucket_name = "mock-mock-a-abc12345"

        make_s3_bucket = MagicMock()
        sam_env_vars: dict[str, dict[str, str]] = {}

        mock_write = MagicMock()
        mock_wait = MagicMock(return_value=shared_bucket_name)

        monkeypatch.setattr("samstack.mock.fixture.get_worker_id", lambda: "gw1")
        monkeypatch.setattr("samstack.mock.fixture.is_controller", lambda w: False)
        monkeypatch.setattr("samstack.mock.fixture.write_state_file", mock_write)
        monkeypatch.setattr("samstack.mock.fixture.wait_for_state_key", mock_wait)

        # Execute
        _make = _get_make(make_s3_bucket, mock_s3_client, sam_env_vars)
        result = _make("TestFunc", alias="mock-a")

        # Assert: wait_for_state_key called with correct key and timeout
        mock_wait.assert_called_once_with("mock_spy_bucket_mock-a", timeout=120)

        # Assert: make_s3_bucket NOT called on gw1+
        make_s3_bucket.assert_not_called()

        # Assert: write_state_file NOT called on gw1+
        mock_write.assert_not_called()

        # Assert: LambdaMock returned with shared bucket
        assert isinstance(result, LambdaMock)
        assert result.name == "mock-a"
        assert result.bucket.name == shared_bucket_name

    def test_env_vars_set_on_gw0(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """sam_env_vars[function_name] contains correct mock env vars on gw0."""
        mock_s3_client = MagicMock()
        mock_bucket = S3Bucket(name="mock-mock-a-abc12345", client=mock_s3_client)

        make_s3_bucket = MagicMock(return_value=mock_bucket)
        sam_env_vars: dict[str, dict[str, str]] = {}

        monkeypatch.setattr("samstack.mock.fixture.get_worker_id", lambda: "gw0")
        monkeypatch.setattr("samstack.mock.fixture.is_controller", lambda w: True)
        monkeypatch.setattr("samstack.mock.fixture.write_state_file", MagicMock())
        monkeypatch.setattr("samstack.mock.fixture.wait_for_state_key", MagicMock())

        _make = _get_make(make_s3_bucket, mock_s3_client, sam_env_vars)
        _make("TestFunc", alias="mock-a")

        # Assert: env vars set correctly
        assert "TestFunc" in sam_env_vars
        assert sam_env_vars["TestFunc"]["MOCK_SPY_BUCKET"] == "mock-mock-a-abc12345"
        assert sam_env_vars["TestFunc"]["MOCK_FUNCTION_NAME"] == "mock-a"
        assert (
            sam_env_vars["TestFunc"]["AWS_ENDPOINT_URL_S3"]
            == "http://localstack:4566"
        )

    def test_env_vars_set_on_gw1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """sam_env_vars[function_name] contains correct mock env vars on gw1+."""
        mock_s3_client = MagicMock()
        shared_bucket_name = "mock-mock-a-abc12345"

        make_s3_bucket = MagicMock()
        sam_env_vars: dict[str, dict[str, str]] = {}

        monkeypatch.setattr("samstack.mock.fixture.get_worker_id", lambda: "gw1")
        monkeypatch.setattr("samstack.mock.fixture.is_controller", lambda w: False)
        monkeypatch.setattr("samstack.mock.fixture.write_state_file", MagicMock())
        monkeypatch.setattr(
            "samstack.mock.fixture.wait_for_state_key",
            MagicMock(return_value=shared_bucket_name),
        )

        _make = _get_make(make_s3_bucket, mock_s3_client, sam_env_vars)
        _make("TestFunc", alias="mock-a")

        # Assert: env vars set correctly on gw1+ with shared bucket name
        assert "TestFunc" in sam_env_vars
        assert sam_env_vars["TestFunc"]["MOCK_SPY_BUCKET"] == shared_bucket_name
        assert sam_env_vars["TestFunc"]["MOCK_FUNCTION_NAME"] == "mock-a"
        assert (
            sam_env_vars["TestFunc"]["AWS_ENDPOINT_URL_S3"]
            == "http://localstack:4566"
        )

    def test_gw1_fails_on_error_state_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """gw1+ detects error key in state via wait_for_state_key, raises pytest.fail."""
        mock_s3_client = MagicMock()
        make_s3_bucket = MagicMock()
        sam_env_vars: dict[str, dict[str, str]] = {}

        # wait_for_state_key raises pytest.fail when error key exists
        mock_wait = MagicMock(side_effect=pytest.fail.Exception("gw0 infrastructure startup failed: mock spy bucket creation failed"))
        monkeypatch.setattr("samstack.mock.fixture.get_worker_id", lambda: "gw1")
        monkeypatch.setattr("samstack.mock.fixture.is_controller", lambda w: False)
        monkeypatch.setattr("samstack.mock.fixture.wait_for_state_key", mock_wait)
        monkeypatch.setattr("samstack.mock.fixture.write_state_file", MagicMock())

        _make = _get_make(make_s3_bucket, mock_s3_client, sam_env_vars)

        # wait_for_state_key raises — _make propagates it
        with pytest.raises(pytest.fail.Exception):
            _make("TestFunc", alias="mock-a")

    def test_pre_existing_bucket_bypasses_xdist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When bucket= kwarg is passed, no xdist logic executes — bucket used directly."""
        mock_s3_client = MagicMock()
        pre_existing = S3Bucket(name="my-bucket", client=mock_s3_client)

        make_s3_bucket = MagicMock()
        sam_env_vars: dict[str, dict[str, str]] = {}

        mock_write = MagicMock()
        mock_wait = MagicMock()

        monkeypatch.setattr("samstack.mock.fixture.get_worker_id", lambda: "gw0")
        monkeypatch.setattr("samstack.mock.fixture.is_controller", lambda w: True)
        monkeypatch.setattr("samstack.mock.fixture.write_state_file", mock_write)
        monkeypatch.setattr("samstack.mock.fixture.wait_for_state_key", mock_wait)

        _make = _get_make(make_s3_bucket, mock_s3_client, sam_env_vars)
        result = _make("Func", alias="x", bucket=pre_existing)

        # Assert: no xdist logic executed
        make_s3_bucket.assert_not_called()
        mock_write.assert_not_called()
        mock_wait.assert_not_called()

        # Assert: the provided bucket is used
        assert result.bucket is pre_existing
        assert sam_env_vars["Func"]["MOCK_SPY_BUCKET"] == "my-bucket"

    def test_master_path_preserves_original_behavior(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Master worker_id (non-xdist): make_s3_bucket called, no state read/write."""
        mock_s3_client = MagicMock()
        mock_bucket = S3Bucket(name="mock-mock-a-abc12345", client=mock_s3_client)

        make_s3_bucket = MagicMock(return_value=mock_bucket)
        sam_env_vars: dict[str, dict[str, str]] = {}

        mock_write = MagicMock()
        mock_wait = MagicMock()

        monkeypatch.setattr("samstack.mock.fixture.get_worker_id", lambda: "master")
        monkeypatch.setattr("samstack.mock.fixture.is_controller", lambda w: True)
        monkeypatch.setattr("samstack.mock.fixture.write_state_file", mock_write)
        monkeypatch.setattr("samstack.mock.fixture.wait_for_state_key", mock_wait)

        _make = _get_make(make_s3_bucket, mock_s3_client, sam_env_vars)
        result = _make("TestFunc", alias="mock-a")

        # Assert: make_s3_bucket called (original behavior)
        make_s3_bucket.assert_called_once_with("mock-mock-a")

        # Assert: NO state writes (only gw0 writes state)
        mock_write.assert_not_called()

        # Assert: NO state reads
        mock_wait.assert_not_called()

        # Assert: LambdaMock returned
        assert isinstance(result, LambdaMock)
        assert result.name == "mock-a"

    def test_env_vars_contain_aws_endpoint_url_s3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """sam_env_vars includes AWS_ENDPOINT_URL_S3=http://localstack:4566."""
        mock_s3_client = MagicMock()
        mock_bucket = S3Bucket(name="mock-b-xyz", client=mock_s3_client)

        make_s3_bucket = MagicMock(return_value=mock_bucket)
        sam_env_vars: dict[str, dict[str, str]] = {}

        monkeypatch.setattr("samstack.mock.fixture.get_worker_id", lambda: "gw0")
        monkeypatch.setattr("samstack.mock.fixture.is_controller", lambda w: True)
        monkeypatch.setattr("samstack.mock.fixture.write_state_file", MagicMock())
        monkeypatch.setattr("samstack.mock.fixture.wait_for_state_key", MagicMock())

        _make = _get_make(make_s3_bucket, mock_s3_client, sam_env_vars)
        _make("TestFunc", alias="mock-b")

        assert sam_env_vars["TestFunc"]["AWS_ENDPOINT_URL_S3"] == "http://localstack:4566"

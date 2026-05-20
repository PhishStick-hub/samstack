"""Unit tests for SamServiceConfig frozen dataclass and start_sam() context manager."""

from __future__ import annotations

import dataclasses
from unittest.mock import patch

import pytest

from samstack.fixtures._sam_container import SamServiceConfig, start_sam
from samstack.settings import SamStackSettings


# --- SamServiceConfig tests ---


class TestSamServiceConfig:
    """Tests for the SamServiceConfig frozen dataclass."""

    def test_instantiation_with_all_fields(self) -> None:
        """SamServiceConfig can be instantiated with all required fields."""
        config = SamServiceConfig(
            subcommand="start-api",
            port=3000,
            warm_containers="LAZY",
            settings_extra_args=[],
            fixture_extra_args=[],
            log_filename="test.log",
            wait_mode="http",
            network_alias="sam-api",
        )
        assert config.subcommand == "start-api"
        assert config.port == 3000
        assert config.warm_containers == "LAZY"
        assert config.settings_extra_args == []
        assert config.fixture_extra_args == []
        assert config.log_filename == "test.log"
        assert config.wait_mode == "http"
        assert config.network_alias == "sam-api"

    def test_frozen_prevents_mutation(self) -> None:
        """SamServiceConfig is frozen — mutation raises FrozenInstanceError."""
        config = SamServiceConfig(
            subcommand="start-api",
            port=3000,
            warm_containers="LAZY",
            settings_extra_args=[],
            fixture_extra_args=[],
            log_filename="test.log",
            wait_mode="http",
            network_alias="sam-api",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(config, "port", 4000)

    def test_fields_match_run_sam_service_params(self) -> None:
        """SamServiceConfig fields cover the parameter list of _run_sam_service
        (excluding settings and docker_network, which are passed separately)."""
        config_fields = {f.name for f in dataclasses.fields(SamServiceConfig)}
        # Parameters of _run_sam_service minus settings + docker_network:
        expected_fields = {
            "subcommand",
            "port",
            "warm_containers",
            "settings_extra_args",
            "fixture_extra_args",
            "log_filename",
            "wait_mode",
            "network_alias",
        }
        assert config_fields == expected_fields


# --- start_sam() tests ---


class TestStartSam:
    """Tests for the start_sam() context manager."""

    def test_yields_endpoint_string(self) -> None:
        """start_sam yields the endpoint string from _run_sam_service."""
        config = SamServiceConfig(
            subcommand="start-api",
            port=3000,
            warm_containers="LAZY",
            settings_extra_args=[],
            fixture_extra_args=[],
            log_filename="test.log",
            wait_mode="http",
            network_alias="sam-api",
        )
        settings = SamStackSettings(sam_image="test-image")

        with patch("samstack.fixtures._sam_container._run_sam_service") as mock_run:
            mock_run.return_value.__enter__.return_value = "http://127.0.0.1:3000"
            mock_run.return_value.__exit__.return_value = None

            with start_sam(settings, "test-network", config) as endpoint:
                assert endpoint == "http://127.0.0.1:3000"

    def test_delegates_settings_and_docker_network_unchanged(self) -> None:
        """start_sam passes settings and docker_network to _run_sam_service unchanged."""
        config = SamServiceConfig(
            subcommand="start-lambda",
            port=3001,
            warm_containers="EAGER",
            settings_extra_args=["--debug"],
            fixture_extra_args=["--profile", "test"],
            log_filename="lambda.log",
            wait_mode="port",
            network_alias="sam-lambda",
        )
        settings = SamStackSettings(sam_image="test-image")

        with patch("samstack.fixtures._sam_container._run_sam_service") as mock_run:
            mock_run.return_value.__enter__.return_value = "http://127.0.0.1:3001"
            mock_run.return_value.__exit__.return_value = None

            with start_sam(settings, "my-network", config):
                pass

        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["settings"] is settings
        assert call_kwargs["docker_network"] == "my-network"

    def test_passes_config_fields_to_run_sam_service(self) -> None:
        """start_sam passes each config field to _run_sam_service as the corresponding kwarg."""
        config = SamServiceConfig(
            subcommand="start-lambda",
            port=3001,
            warm_containers="EAGER",
            settings_extra_args=["--debug"],
            fixture_extra_args=["--profile", "test"],
            log_filename="lambda.log",
            wait_mode="port",
            network_alias="sam-lambda",
        )
        settings = SamStackSettings(sam_image="test-image")

        with patch("samstack.fixtures._sam_container._run_sam_service") as mock_run:
            mock_run.return_value.__enter__.return_value = "http://127.0.0.1:3001"
            mock_run.return_value.__exit__.return_value = None

            with start_sam(settings, "net", config):
                pass

        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["subcommand"] == "start-lambda"
        assert call_kwargs["port"] == 3001
        assert call_kwargs["warm_containers"] == "EAGER"
        assert call_kwargs["settings_extra_args"] == ["--debug"]
        assert call_kwargs["fixture_extra_args"] == ["--profile", "test"]
        assert call_kwargs["log_filename"] == "lambda.log"
        assert call_kwargs["wait_mode"] == "port"
        assert call_kwargs["network_alias"] == "sam-lambda"

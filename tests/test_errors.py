from samstack._errors import (
    DockerNetworkError,
    LocalStackStartupError,
    SamBuildError,
    SamStackError,
    SamStartupError,
)


def test_sam_build_error_is_sam_stack_error() -> None:
    err = SamBuildError(logs="build failed output")
    assert isinstance(err, SamStackError)
    assert "build failed output" in str(err)


def test_sam_startup_error_contains_port_and_log() -> None:
    err = SamStartupError(port=3000, log_tail="last 50 lines")
    assert isinstance(err, SamStackError)
    assert "3000" in str(err)
    assert "last 50 lines" in str(err)


def test_localstack_startup_error_is_sam_stack_error() -> None:
    err = LocalStackStartupError(log_tail="ls crashed")
    assert isinstance(err, SamStackError)
    assert "ls crashed" in str(err)


def test_docker_network_error_is_sam_stack_error() -> None:
    err = DockerNetworkError(name="samstack-abc", reason="permission denied")
    assert isinstance(err, SamStackError)
    assert "samstack-abc" in str(err)
    assert "permission denied" in str(err)

class SamStackError(Exception):
    """Base exception for all samstack errors."""


class SamBuildError(SamStackError):
    """sam build container exited with non-zero status."""

    def __init__(self, logs: str) -> None:
        self.logs = logs
        super().__init__(f"sam build failed.\n\nLogs:\n{logs}")


class SamStartupError(SamStackError):
    """SAM process did not bind port within timeout."""

    def __init__(self, port: int, log_tail: str) -> None:
        self.port = port
        self.log_tail = log_tail
        super().__init__(
            f"SAM did not start on port {port} within timeout.\n\nLog tail:\n{log_tail}"
        )


class LocalStackStartupError(SamStackError):
    """LocalStack container did not become healthy."""

    def __init__(self, log_tail: str) -> None:
        self.log_tail = log_tail
        super().__init__(f"LocalStack did not become healthy.\n\nLog tail:\n{log_tail}")


class DockerNetworkError(SamStackError):
    """Failed to create or attach shared Docker network."""

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason
        super().__init__(f"Docker network '{name}' error: {reason}")

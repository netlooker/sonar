"""Structured Sonar errors."""

from __future__ import annotations


class SonarError(Exception):
    status_code = 500
    error_type = "internal_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        retryable: bool | None = None,
        dependency: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = self.retryable if retryable is None else retryable
        self.dependency = dependency
        self.timeout_seconds = timeout_seconds

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "error_type": self.error_type,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.dependency:
            payload["dependency"] = self.dependency
        if self.timeout_seconds is not None:
            payload["timeout_seconds"] = self.timeout_seconds
        return payload


class SonarBadRequestError(SonarError):
    status_code = 400
    error_type = "bad_request"


class SonarForbiddenError(SonarError):
    status_code = 403
    error_type = "forbidden"


class SonarNotFoundError(SonarError):
    status_code = 404
    error_type = "not_found"


class SonarDependencyError(SonarError):
    status_code = 424
    error_type = "dependency_unavailable"
    retryable = True


class SonarUpstreamUnavailableError(SonarError):
    status_code = 503
    error_type = "upstream_unavailable"
    retryable = True


class SonarTimeoutError(SonarError):
    status_code = 504
    error_type = "timeout"
    retryable = True

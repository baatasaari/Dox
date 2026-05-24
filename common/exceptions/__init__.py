from __future__ import annotations


class DoxException(Exception):  # noqa: N818
    def __init__(self, detail: str, code: str = "dox_error") -> None:
        self.detail = detail
        self.code = code
        super().__init__(detail)


class ConfigurationError(DoxException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, code="configuration_error")


class ValidationError(DoxException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, code="validation_error")


class NotFoundError(DoxException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, code="not_found")


class AuthenticationError(DoxException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, code="authentication_error")


class AuthorizationError(DoxException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, code="authorization_error")


class RateLimitError(DoxException):
    def __init__(self, detail: str, retry_after: int = 1) -> None:
        super().__init__(detail=detail, code="rate_limit_exceeded")
        self.retry_after = retry_after


class QuotaExceededError(DoxException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, code="quota_exceeded")


class EntitlementError(DoxException):
    def __init__(self, detail: str, feature: str = "") -> None:
        super().__init__(detail=detail, code="feature_not_available")
        self.feature = feature


class ConflictError(DoxException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, code="conflict")

"""Error taxonomy.

Collapsing everything into HTTP 500 would make a scientific guard failure look
like a transient bug. These classes keep the distinction visible all the way to
the browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorClass(StrEnum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    POLICY_DENIED = "POLICY_DENIED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    SCIENTIFIC_GUARD_FAILURE = "SCIENTIFIC_GUARD_FAILURE"
    ARTIFACT_INTEGRITY_FAILURE = "ARTIFACT_INTEGRITY_FAILURE"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"


#: HTTP status per class. Scientific guard failures are 409 Conflict rather than
#: 500: the request was understood and deliberately refused.
HTTP_STATUS: dict[ErrorClass, int] = {
    ErrorClass.CONFIGURATION_ERROR: 503,
    ErrorClass.POLICY_DENIED: 403,
    ErrorClass.PROVIDER_UNAVAILABLE: 503,
    ErrorClass.RATE_LIMITED: 429,
    ErrorClass.TRANSPORT_ERROR: 502,
    ErrorClass.SCIENTIFIC_GUARD_FAILURE: 409,
    ErrorClass.ARTIFACT_INTEGRITY_FAILURE: 409,
    ErrorClass.NOT_FOUND: 404,
    ErrorClass.VALIDATION_ERROR: 422,
}

#: Classes that must never be retried automatically. Retrying a guard failure or
#: a policy denial would be an attempt to get a different scientific answer.
NON_RETRYABLE: frozenset[ErrorClass] = frozenset(
    {
        ErrorClass.SCIENTIFIC_GUARD_FAILURE,
        ErrorClass.ARTIFACT_INTEGRITY_FAILURE,
        ErrorClass.POLICY_DENIED,
        ErrorClass.CONFIGURATION_ERROR,
        ErrorClass.VALIDATION_ERROR,
        ErrorClass.NOT_FOUND,
    }
)


@dataclass(frozen=True, slots=True)
class AppError(Exception):
    error_class: ErrorClass
    message: str
    detail: str = ""
    run_id: str | None = None

    def __str__(self) -> str:
        return f"[{self.error_class.value}] {self.message}"

    @property
    def http_status(self) -> int:
        return HTTP_STATUS[self.error_class]

    @property
    def retryable(self) -> bool:
        return self.error_class not in NON_RETRYABLE

    def to_dict(self) -> dict[str, object]:
        # No stack trace, no internal path: this shape is what reaches a client.
        return {
            "error_class": self.error_class.value,
            "message": self.message,
            "detail": self.detail,
            "run_id": self.run_id,
            "retryable": self.retryable,
        }

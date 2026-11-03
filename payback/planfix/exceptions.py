"""Domain errors raised for unsuccessful ПланФикс REST operations."""


class PlanfixError(RuntimeError):
    """ПланФикс could not complete a requested operation."""


class PlanfixScopeDenied(PlanfixError):  # noqa: N818 - public name follows the project specification.
    """The API token lacks the scope required for an operation."""


class PlanfixNotFound(PlanfixError):  # noqa: N818 - public name follows the project specification.
    """The requested ПланФикс resource does not exist or is inaccessible."""


class PlanfixSchemaError(PlanfixError):
    """The configured expense-card fields do not match the ПланФикс account."""


class PlanfixIdempotencyConflict(PlanfixError):  # noqa: N818 - public API name
    """ПланФикс rejected a create because the Idempotency-Key was already consumed.

    Unlike standard HTTP idempotency, ПланФикс does not replay the original success
    body — only this error. ``task_id`` is set when the fail payload still carries it.
    """

    def __init__(self, message: str, *, task_id: int | None = None) -> None:
        super().__init__(message)
        self.task_id = task_id


__all__ = [
    "PlanfixError",
    "PlanfixIdempotencyConflict",
    "PlanfixNotFound",
    "PlanfixSchemaError",
    "PlanfixScopeDenied",
]

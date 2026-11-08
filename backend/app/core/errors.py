from __future__ import annotations


class AppError(Exception):
    """A controlled application error with a stable machine-readable code.

    The frontend translates ``code``; ``message`` is an English fallback for
    logs and API consumers that do not have a translation.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_found(code: str = "not_found", message: str = "The requested item was not found."):
    return AppError(404, code, message)


def bad_request(code: str, message: str):
    return AppError(400, code, message)

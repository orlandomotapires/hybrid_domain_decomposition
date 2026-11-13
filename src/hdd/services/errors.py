"""Errors raised by the application layer. ``status`` is the HTTP status the web adapter uses."""

from __future__ import annotations


class ServiceError(Exception):
    status = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInput(ServiceError):
    """The request is malformed or fails validation."""

    status = 400


class NotFound(ServiceError):
    status = 404


class Conflict(ServiceError):
    """The request is valid but collides with existing state."""

    status = 409

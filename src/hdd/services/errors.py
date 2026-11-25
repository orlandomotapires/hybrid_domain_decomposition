"""Errors raised by the application layer; ``str(error)`` is a message fit to show the user."""

from __future__ import annotations


class ServiceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInput(ServiceError):
    """The request is malformed or fails validation."""


class NotFound(ServiceError):
    """The simulation, matrix, preset, study or run does not exist."""


class Conflict(ServiceError):
    """The request is valid but collides with existing state."""

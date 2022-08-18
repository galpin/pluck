# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

from __future__ import annotations

from typing import List

from ._json import JsonValue


class PluckError(Exception):
    """Raised when an error occurs executing a GraphQL request."""

    pass


class HTTPError(PluckError):
    """Raised when an HTTP error occurs executing a GraphQL request."""

    pass


class HTTPStatusError(PluckError):
    """Raised when an HTTP response had an error status (4xx or 5xx)."""

    def __init__(
        self, *, code: int
    ) -> None:
        super().__init__(f"HTTP status {code}")
        self.code = code


class GraphQLError(PluckError):
    """Raised when an error occurs executing a GraphQL request."""

    @classmethod
    def from_errors(cls, errors: List[JsonValue]) -> PluckError:
        lines = [
            f"The GraphQL response contained {len(errors)} errors:",
        ]
        for error in errors:
            lines.append(f"- {error}")
        message = "\n".join(lines)
        return cls(message)

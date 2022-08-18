# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import dataclasses
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ._errors import PluckError, HTTPStatusError
from ._json import JsonSerializer, JsonValue


@dataclass(frozen=True)
class GraphQLRequest:
    """
    A GraphQL request.

    Attributes
    ----------
    url: The GraphQL URL against which to execute the query.
    query: The GraphQL query.
    variables: The optional variables for the query.
    headers: The optional headers for the request.
    """

    url: str
    query: str
    variables: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None

    def __post_init__(self):
        assert self.url, "url must be specified."
        assert self.query, "query must be specified."

    def replace(self, *, query: str) -> "GraphQLRequest":
        """
        :returns: A new GraphQLRequest with the given query.
        """
        return dataclasses.replace(self, query=query)


@dataclass(frozen=True)
class GraphQLResponse:
    """
    A GraphQL response.

    Attributes
    ----------
    data: The data returned by the query.
    errors: The errors returned by the query.
    """

    data: JsonValue
    errors: Optional[Dict]

    @classmethod
    def from_dict(cls, body: Dict) -> "GraphQLResponse":
        if body is None:
            raise PluckError("Response is null.")
        data = body.get("data")
        errors = body.get("errors")
        if data is None and errors is None:
            raise PluckError("Response contains neither data nor errors.")
        return cls(data, errors)


class GraphQLClient(ABC):
    """
    A GraphQL client.
    """

    @abstractmethod
    def execute(self, request: GraphQLRequest) -> GraphQLResponse:
        """
        Executes the given GraphQL request.

        :param request: The GraphQL request.
        :return: The GraphQL response.
        """
        raise NotImplementedError()


class UrllibGraphQLClient(GraphQLClient):
    """
    A GraphQL client that uses urllib to execute requests.
    """

    headers = {"Content-Type": "application/json"}

    def __init__(self):
        self._serializer = JsonSerializer.create_fastest()

    def execute(self, request: GraphQLRequest) -> GraphQLResponse:
        """
        Executes the given GraphQL request.

        :param request: The GraphQL request.
        :return: The GraphQL response.
        """
        body = {"query": request.query}
        if request.variables:
            body["variables"] = request.variables
        response = self._post(request, body)
        return GraphQLResponse.from_dict(response)

    def _post(self, request, body):
        data = self._serializer.serialize(body, encoding="utf-8")
        headers = self.headers.copy()
        if request.headers:
            headers.update(request.headers)
        request = urllib.request.Request(
            request.url,
            method="POST",
            headers=headers,
            data=data,
        )
        try:
            with urllib.request.urlopen(request) as fp:
                return self._serializer.deserialize(fp)
        except urllib.error.HTTPError as error:
            raise HTTPStatusError(code=error.code) from error
        except Exception as error:
            raise PluckError from error


__all__ = [
    "GraphQLRequest",
    "GraphQLResponse",
    "GraphQLClient",
    "UrllibGraphQLClient",
]

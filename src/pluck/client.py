# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import dataclasses
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ._exceptions import PluckError
from ._json import JsonSerializer, JsonValue


@dataclass(frozen=True)
class GraphQLRequest:
    url: str
    query: str
    variables: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None

    def __post_init__(self):
        assert self.url, "url must be specified."
        assert self.query, "query must be specified."

    def replace(self, *, query: str) -> "GraphQLRequest":
        return dataclasses.replace(self, query=query)


@dataclass(frozen=True)
class GraphQLResponse:
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
    @abstractmethod
    def execute(self, request: GraphQLRequest) -> GraphQLResponse:
        raise NotImplementedError()


class UrllibGraphQLClient(GraphQLClient):
    headers = {"Content-Type": "application/json"}

    def __init__(self):
        self._serializer = JsonSerializer.create_fastest()

    def execute(self, request: GraphQLRequest) -> GraphQLResponse:
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
        with urllib.request.urlopen(request) as fp:
            return self._serializer.deserialize(fp)


__all__ = [
    "GraphQLRequest",
    "GraphQLResponse",
    "GraphQLClient",
    "UrllibGraphQLClient",
]

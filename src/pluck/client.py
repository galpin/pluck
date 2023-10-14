import dataclasses
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from ._json import JsonSerializer

__all__ = ("GraphQLRequest", "GraphQLResponse", "GraphQLClient", "UrllibGraphQLClient")


@dataclass(frozen=True)
class GraphQLRequest:
    """
    A GraphQL request.

    Args:
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
        Returns a new GraphQLRequest with the given query.
        """
        return dataclasses.replace(self, query=query)


@dataclass(frozen=True)
class GraphQLResponse:
    """
    A GraphQL response.

    Args:
        data: The data returned by the query.
        errors: The errors returned by the query.
    """

    data: Union[Dict, List, int, str, bool, None]
    errors: Optional[Dict]

    @classmethod
    def from_dict(cls, response: Dict) -> "GraphQLResponse":
        return cls(response.get("data"), response.get("errors"))


class GraphQLClient(ABC):
    """
    A GraphQL client.
    """

    @abstractmethod
    def execute(self, request: GraphQLRequest) -> GraphQLResponse:
        """
        Executes the given GraphQL request.

        Args:
            request: The GraphQL request.

        Returns:
            The GraphQL response.
        """
        raise NotImplementedError()


class UrllibGraphQLClient(GraphQLClient):
    """
    A GraphQL client that uses urllib to execute requests.
    """

    def __init__(self):
        self._serializer = JsonSerializer.create_fastest()

    def execute(self, request: GraphQLRequest) -> GraphQLResponse:
        """
        Executes the given GraphQL request.

        Args:
            request: The GraphQL request.

        Returns:
            The GraphQL response.
        """
        body = {"query": request.query}
        if request.variables:
            body["variables"] = request.variables
        response = self._post(request, body)
        return GraphQLResponse.from_dict(response)

    def _post(self, request, body):
        data = self._serializer.serialize(body, encoding="utf-8")
        headers = {"Content-Type": "application/json"}
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

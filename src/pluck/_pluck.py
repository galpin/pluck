from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ._execution import Executor, ExecutorOptions
from ._libraries import DataFrame
from .client import GraphQLClient, GraphQLRequest

Url = str
Headers = Optional[Dict[str, Any]]
Query = str
Variables = Optional[Dict[str, Any]]
Pluck = Callable[[str, Variables], "Response"]


@dataclass(frozen=True)
class Response:
    """
    A response from a pluck query.

    Attributes
    ----------
    data: The data returned from the query.
    errors: The optional errors returned from the query.
    frames: The optional dictionary of data frames returned from the query.
    """

    data: Dict
    errors: Optional[List]
    frames: Optional[Dict[str, DataFrame]]

    def __iter__(self):
        """
        Iterate over the data frames.
        """
        return self.frames.values().__iter__()


def create(
    url: Url,
    headers: Headers = None,
    separator: str = ".",
    client: GraphQLClient = None,
) -> Pluck:
    """
    Create a pluck function equivalent to `read_graphql` that is pre-configured with the specified options.

    :param url: The GraphQL URL against which to execute the query.
    :param headers: The HTTP headers to set when executing the query.
    :param client: An optional GqlClient instance to use for executing the query.
    :param separator: An optional separator for nested record names (the default is '.').
    :return: A Pluck function.
    """

    def pluck(query: Query, variables: Variables = None) -> Response:
        return read_graphql(
            query,
            variables,
            url=url,
            headers=headers,
            separator=separator,
            client=client,
        )

    return pluck


def read_graphql(
    query: Query,
    variables: Variables = None,
    *,
    url: Url,
    headers: Headers = None,
    separator: str = ".",
    client: GraphQLClient = None,
) -> Response:
    """
    Execute a GraphQL query and return a Response object.

    :param query: The GraphQL query to execute.
    :param variables: The optional dictionary of variables to pass to the query.
    :param url: The GraphQL URL against which to execute the query.
    :param headers: The HTTP headers to set when executing the query.
    :param client: An optional GqlClient instance to use for executing the query.
    :param separator: An optional separator for nested record names (the default is '.').
    :return: A Response object.
    """
    request = GraphQLRequest(url, query, variables, headers)
    options = ExecutorOptions(separator, client)
    executor = Executor(options)
    data, errors, frames = executor.execute(request)
    return Response(data, errors, frames)

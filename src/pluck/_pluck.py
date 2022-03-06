from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Callable

from ._execution import Executor, ExecutorOptions
from .client import GraphQLClient, GraphQLRequest
from .libraries import DataFrame, DataFrameLibrary


Url = str
Headers = Optional[Dict[str, Any]]
Query = str
Variables = Optional[Dict[str, Any]]
Pluck = Callable[[str, Variables], "Response"]


@dataclass(frozen=True)
class Response:
    """
    A response from a pluck query.

    :attr data: The data returned from the query.
    :attr errors: The errors returned from the query.
    :attr frame: The dictionary of data frames returned from the query.
    """

    data: Dict
    errors: Optional[List]
    frames: Dict[str, DataFrame]

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
    library: DataFrameLibrary = None,
) -> Pluck:
    """
    Create a pluck function equivalent to `read_graphql` that is pre-configured with the specified options.

    :param url: The GraphQL URL against which to execute the query.
    :param headers: The HTTP headers to set when executing the query.
    :param client: An optional GqlClient instance to use for executing the query.
    :param separator: An optional separator for nested record names (the default is '.').
    :param library: An optional data frame library to use (the default is pandas).
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
            library=library,
        )

    return pluck


def read_graphql(
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    *,
    url: Url,
    headers: Optional[Headers] = None,
    separator: str = ".",
    client: GraphQLClient = None,
    library: DataFrameLibrary = None,
) -> Response:
    """
    Execute a GraphQL query and return a Response object.

    :param query: The GraphQL query to execute.
    :param variables: The optional dictionary of variables to pass to the query.
    :param url: The GraphQL URL against which to execute the query.
    :param headers: The HTTP headers to set when executing the query.
    :param client: An optional GqlClient instance to use for executing the query.
    :param separator: An optional separator for nested record names (the default is '.').
    :param library: An optional data frame library to use (the default is pandas).
    :return: A Response object.
    """
    request = GraphQLRequest(url, query, variables, headers)
    options = ExecutorOptions(separator, client, library)
    executor = Executor(options)
    data, errors, frames = executor.execute(request)
    return Response(data, errors, frames)

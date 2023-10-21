from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Callable, Literal, Union

from ._execution import Executor, ExecutorOptions
from .client import GraphQLClient, GraphQLRequest
from ._libraries import DataFrame


UrlType = str
HeadersType = Optional[Dict[str, Any]]
QueryType = str
VariablesType = Optional[Dict[str, Any]]
PluckType = Callable[[str, VariablesType], "Response"]
ColumnNames = Literal["full", "short"]
ColumnNamesType = Union[ColumnNames, dict[str, ColumnNames]]


@dataclass(frozen=True)
class Response:
    """
    A response from a pluck query.

    Iterating over the response will yield the data-frames.

    Args:
        data: The data returned from the query.
        errors: The errors returned from the query.
        frames: The dictionary of data frames returned from the query.
    """

    data: Dict
    errors: Optional[List]
    frames: Dict[str, DataFrame]

    def __iter__(self):
        """
        Iterate over the data-frames.
        """
        return self.frames.values().__iter__()


def create(
    url: UrlType,
    headers: HeadersType = None,
    separator: str = ".",
    client: GraphQLClient = None,
) -> PluckType:
    """
    Create a pluck function equivalent to `execute` that is pre-configured with the specified options.

    Args:
        url:
            The GraphQL URL against which to execute the query.
        headers:
            The HTTP headers to set when executing the query.
        separator:
            An optional separator for nested record names (the default is `.`).
        client:
            An optional GqlClient instance to use for executing the query.

    Returns:
        A Response object. Iterating over the response will yield the data frames.
    """

    def pluck(
        query: QueryType,
        variables: VariablesType = None,
        *,
        column_names: ColumnNamesType = None,
    ) -> Response:
        return execute(
            query,
            variables,
            url=url,
            headers=headers,
            separator=separator,
            column_names=column_names,
            client=client,
        )

    pluck.__doc__ = execute.__doc__
    return pluck


def execute(
    query: QueryType,
    variables: VariablesType = None,
    *,
    url: UrlType,
    headers: HeadersType = None,
    separator: str = ".",
    column_names: ColumnNamesType = None,
    client: GraphQLClient = None,
) -> Response:
    """
    Execute a GraphQL query and return a Response object.

    Args:
        query:
            The GraphQL query to execute.
        variables:
            The optional dictionary of variables to pass to the query.
        url:
            The GraphQL URL against which to execute the query.
        headers:
            The HTTP headers to set when executing the query.
        separator:
            An optional separator for nested record names (the default is `.`).
        column_names:
            An optional specifier for how to format column names (the default is `full`).

            `full` means the column names will be the full path to the field in the GraphQL query.
            `short` means the column names will be the last part of the path to the field in the GraphQL query.
            If a conflict between fields is detected, all names will be prefixed with the name of their parent.

            Different modes can be specified using a dictionary (the key is the name of the frame).
        client:
            An optional GqlClient instance to use for executing the query.

    Returns:
        A Response object. Iterating over the response will yield the data frames.
    """
    request = GraphQLRequest(url, query, variables, headers)
    options = ExecutorOptions(separator, client, column_names)
    executor = Executor(options)
    data, errors, frames = executor.execute(request)
    return Response(data, errors, frames)

from __future__ import annotations

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
    url: UrlType,
    headers: HeadersType = None,
    separator: str = ".",
    column_names: Literal["full", "short"] = "full",
    client: GraphQLClient = None,
) -> PluckType:
    """
    Create a pluck function equivalent to `execute` that is pre-configured with the specified options.

    :param url: The GraphQL URL against which to execute the query.
    :param headers: The HTTP headers to set when executing the query.
    :param client: An optional GqlClient instance to use for executing the query.
    :param separator: An optional separator for nested record names (the default is '.').
    :param column_names: An optional specifier for how to format column names (the default is `full`).
        When `full`, the column names will be the full path to the field in the GraphQL query.
        When `short`, the column names will be the last part of the path to the field in the GraphQL query.
    :return: A Pluck function.
    """

    def pluck(query: QueryType, variables: VariablesType = None) -> Response:
        return execute(
            query,
            variables,
            url=url,
            headers=headers,
            separator=separator,
            column_names=column_names,
            client=client,
        )

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

    :param query: The GraphQL query to execute.
    :param variables: The optional dictionary of variables to pass to the query.
    :param url: The GraphQL URL against which to execute the query.
    :param headers: The HTTP headers to set when executing the query.
    :param separator: An optional separator for nested record names (the default is `.`).
    :param column_names: An optional specifier for how to format column names (the default is `full`).
        When `full`, the column names will be the full path to the field in the GraphQL query.
        When `short`, the column names will be the last part of the path to the field in the GraphQL query. If a
        conflict between fields is detected, all names will be prefixed with the name of their parent.
        Different modes can be specified using a dictionary (the key is the name of the frame).
    :param client: An optional GqlClient instance to use for executing the query.
    :return: A Response object.
    """
    request = GraphQLRequest(url, query, variables, headers)
    options = ExecutorOptions(separator, client, column_names)
    executor = Executor(options)
    data, errors, frames = executor.execute(request)
    return Response(data, errors, frames)

import dataclasses
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional, Union

import graphql

from ._execution import Executor, ExecutorOptions
from ._introspection import introspect_schema
from ._libraries import DataFrame
from ._parser import QueryParser
from .client import (
    GraphQLClient,
    GraphQLRequest,
    GraphQLResponse,
    UrllibGraphQLClient,
)
from .generator import GenerateRequest, QueryGenerator, SmolagentsQueryGenerator

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
        query: The GraphQL query that produced the response. This is set by
            `ask` to the query generated from the natural-language question.
    """

    data: Dict
    errors: Optional[List]
    frames: Dict[str, DataFrame]
    query: Optional[str] = None

    def __iter__(self):
        """
        Iterate over the data-frames.
        """
        return self.frames.values().__iter__()


def create(
    url: UrlType,
    headers: HeadersType = None,
    separator: str = ".",
    client: Optional[GraphQLClient] = None,
    generator: Optional[QueryGenerator] = None,
) -> PluckType:
    """
    Create a pluck function equivalent to `execute` that is pre-configured with the specified options.

    The returned function also has an `ask` attribute, equivalent to `ask`, that
    is pre-configured with the same options.

    Args:
        url:
            The GraphQL URL against which to execute the query.
        headers:
            The HTTP headers to set when executing the query.
        separator:
            An optional separator for nested record names (the default is `.`).
        client:
            An optional GqlClient instance to use for executing the query.
        generator:
            An optional QueryGenerator used by `ask` to generate queries from
            natural language.

    Returns:
        A Response object. Iterating over the response will yield the data frames.
    """

    def pluck(
        query: QueryType,
        variables: VariablesType = None,
        *,
        column_names: Optional[ColumnNamesType] = None,
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

    def pluck_ask(
        question: str,
        *,
        column_names: Optional[ColumnNamesType] = None,
        generator: Optional[QueryGenerator] = generator,
    ) -> Response:
        return ask(
            question,
            url=url,
            headers=headers,
            separator=separator,
            column_names=column_names,
            client=client,
            generator=generator,
        )

    pluck.__doc__ = execute.__doc__
    setattr(pluck, "ask", pluck_ask)
    return pluck


def execute(
    query: QueryType,
    variables: VariablesType = None,
    *,
    url: UrlType,
    headers: HeadersType = None,
    separator: str = ".",
    column_names: Optional[ColumnNamesType] = None,
    client: Optional[GraphQLClient] = None,
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


def ask(
    question: str,
    *,
    url: UrlType,
    headers: HeadersType = None,
    separator: str = ".",
    column_names: Optional[ColumnNamesType] = None,
    client: Optional[GraphQLClient] = None,
    generator: Optional[QueryGenerator] = None,
) -> Response:
    """
    Answer a natural-language question by generating and executing a GraphQL query.

    The target API is introspected for its schema, a `QueryGenerator` turns the
    question into a GraphQL query and that query is then executed (exactly like
    `execute`, so the `@frame` directive and `column_names` still apply). The
    generated query is available on the returned response as `Response.query`.

    Args:
        question:
            The natural-language question to answer.
        url:
            The GraphQL URL against which to execute the query.
        headers:
            The HTTP headers to set when executing the query.
        separator:
            An optional separator for nested record names (the default is `.`).
        column_names:
            An optional specifier for how to format column names (see `execute`).
        client:
            An optional GqlClient instance to use for executing the query.
        generator:
            An optional QueryGenerator used to generate the query from the
            question. The default is an agentic `SmolagentsQueryGenerator`, which
            requires the optional `smolagents` dependency
            (`pip install "pluck-graphql[agent]"`).

    Returns:
        A Response object. Iterating over the response will yield the data frames.
    """
    client = client or UrllibGraphQLClient()
    generator = generator or SmolagentsQueryGenerator()
    schema = introspect_schema(client, url, headers)

    def run_query(raw_query: str) -> GraphQLResponse:
        try:
            server_query = QueryParser(raw_query).parse().query
        except graphql.GraphQLError as e:
            return GraphQLResponse(None, [{"message": f"Invalid GraphQL: {e}"}])
        return client.execute(GraphQLRequest(url, server_query, None, headers))

    generated = generator.generate(GenerateRequest(question, schema, run_query))
    response = execute(
        generated,
        url=url,
        headers=headers,
        separator=separator,
        column_names=column_names,
        client=client,
    )
    return dataclasses.replace(response, query=generated)

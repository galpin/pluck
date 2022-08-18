# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

from __future__ import annotations

import functools
from typing import Any, Callable, Dict, List, Optional

from . import PluckError
from ._execution import Executor, ExecutorOptions
from ._libraries import DataFrame
from .client import GraphQLClient, GraphQLRequest

Url = str
Headers = Optional[Dict[str, Any]]
Query = str
Variables = Optional[Dict[str, Any]]
Pluck = Callable[[str, Variables], "Response"]


class PluckResponse:
    """
    A response from a pluck query.

    :param data: The optional data returned from the query.
    :param errors: The optional errors returned from the query.
    :param frames: The optional dictionary of data frames returned from the query.
    """

    def __init__(
        self,
        data: Optional[Dict],
        errors: Optional[List],
        frames: Optional[Dict[str, DataFrame]],
    ):
        self._data = data
        self._errors = errors
        self._frames = frames or {}

    @property
    def data(self) -> Optional[Dict]:
        """
        :returns: The optional data returned from the query.
        """
        return self._data

    @property
    def errors(self) -> Optional[List]:
        """
        :returns: The optional errors returned from the query.
        """
        return self._errors

    @property
    def frames(self) -> Dict[str, DataFrame]:
        """
        :returns: The dictionary of data frames returned from the query. If the query was frameless,
                  this will be an empty dict.
        """
        return self._frames

    def raise_for_errors(self):
        """
        :raises PluckError: If the response contains errors.
        """
        if self.errors:
            raise PluckError.from_errors(self.errors)

    def __iter__(self):
        """
        Iterate over the data frames.
        """
        assert self.frames, "No data frames were returned."
        return self.frames.values().__iter__()


def create(
    url: Url,
    headers: Headers = None,
    separator: str = ".",
    client: GraphQLClient = None,
) -> Pluck:
    """
    Create a partial function equivalent to `read_graphql` with the specified options.

    :param url: The GraphQL URL against which to execute the query.
    :param headers: The HTTP headers to set when executing the query.
    :param client: The optional GqlClient instance to use for executing the query.
    :param separator: The optional separator for nested record names (the default is '.').
    :return: A Pluck function.
    """
    return functools.partial(
        read_graphql,
        url=url,
        headers=headers,
        separator=separator,
        client=client,
    )


def read_graphql(
    query: Query,
    variables: Variables = None,
    *,
    url: Url,
    headers: Headers = None,
    separator: str = ".",
    client: GraphQLClient = None,
) -> PluckResponse:
    """
    Execute a GraphQL query and return a Response object.

    :param query: The GraphQL query to execute.
    :param variables: The optional dictionary of variables to pass to the query.
    :param url: The GraphQL URL against which to execute the query.
    :param headers: The HTTP headers to set when executing the query.
    :param client: The optional GqlClient instance to use for executing the query.
    :param separator: The optional separator for nested record names (the default is '.').
    :return: A Response object.
    :rtype: PluckResponse
    :raises PluckError: Occurs when the query execution failed or an HTTP error is encountered.
    """
    request = GraphQLRequest(url, query, variables, headers)
    options = ExecutorOptions(separator, client)
    executor = Executor(options)
    response = PluckResponse(*executor.execute(request))
    return response

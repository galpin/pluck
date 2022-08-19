# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

from __future__ import annotations

import functools
from typing import Any, Callable, Dict, List, Optional

from . import GraphQLError
from ._execution import Executor, ExecutorOptions
from ._libraries import DataFrame
from .client import GraphQLClient, GraphQLRequest

Url = str
Headers = Optional[Dict[str, Any]]
Query = str
Variables = Optional[Dict[str, Any]]
Pluck = Callable[[str, Variables], "Response"]


class Response:
    """
    Contains a response from a GraphQL server.

    This object contains the :meth:`data` and :meth:`error` fields from the
    response plus any data-frames  (:meth:`frames`) that have been plucked from
    the result.

    :meth:`frames` is a dictionary whose keys are correspond to either the name
    of the field on which the ``@frame`` directive was placed, or as specified
    by the name argument of the directive.

    This object also acts an iterator that returns the data-frames. The order
    matches the order they are declared in the query.
    """

    def __init__(
        self,
        data: Optional[Dict],
        errors: Optional[List],
        frames: Dict[str, DataFrame],
    ):
        """
        Create a new instance.

        Parameters
        ----------
        data : dict, optional
            The data returned from the query.
        errors : dict, optional
            The optional errors returned from the query.
        frames : dict{str, DataFrame}
            The dictionary of data-frames returned from the query.
        """
        assert frames is not None
        self._data = data
        self._errors = errors
        self._frames = frames

    @property
    def data(self) -> Optional[Dict]:
        """
        Returns the data returned from the query (optional).
        """
        return self._data

    @property
    def errors(self) -> Optional[List]:
        """
        Returns the errors returned from the query (optional).
        """
        return self._errors

    @property
    def frames(self) -> Dict[str, DataFrame]:
        """
        Returns the dictionary of data-frames returned from the query. If there
        are no data-frames in the response, this will be an empty dict.
        """
        return self._frames

    def raise_for_errors(self):
        """
        Raises a :class:`GraphQLError` if the response contains errors.
        """
        if self.errors:
            raise GraphQLError.from_errors(self.errors)

    def __iter__(self):
        """
        Iterate over the data frames. The order matches the order they are
        declared in the query.

        Raises :class:`AssertionError` when the response contains no data-frames.
        """
        assert self.frames, "The response contains no data-frames."
        return self.frames.values().__iter__()


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
    Execute a GraphQL query and return a :class:`Response` object.

    Parameters
    ----------
    query : str
        The GraphQL query to execute.
    variables : dict{str, Any}, optional
        The dictionary of variables to pass to the query.
    url : str
        The GraphQL URL against which to execute the query.
    headers : dict{str, Any}, optional
        The HTTP headers to set when executing the query.
    separator : str, optional
        The separator for nested record names (the default is '.').
    client : GraphQLClient, optional
        The client instance to use for executing the query (the default uses
        ``urllib``).

    Returns
    -------
    A :class:`Response` object containing the result of the query.

    Examples
-   --------

    >>> query = '''
    {
        launches(limit: 5) @frame {
            mission_name
            launch_date_local
        }
    }
    '''
    >>> df, = pluck.read_graphql(query, url="https://api.spacex.land/graphql")
    """
    request = GraphQLRequest(url, query, variables, headers)
    options = ExecutorOptions(separator, client)
    executor = Executor(options)
    response = Response(*executor.execute(request))
    return response


def create(
    url: Url,
    headers: Headers = None,
    separator: str = ".",
    client: GraphQLClient = None,
) -> Pluck:
    """
    Create a partial function equivalent to :func:`read_graphql` with the
    specified options.

    Parameters
    ----------
    url : str
        The GraphQL URL against which to execute the query.
    headers : dict{str, Any}, optional
        The HTTP headers to set when executing the query.
    separator : str, optional
        The separator for nested record names (the default is '.').
    client : GraphQLClient, optional
        The client instance to use for executing the query (the default uses
        ``urllib``).

    Returns
    -------
    A function equivalent to :func:`read_graphql`.

    Examples
-   --------

    >>> read_graphql = pluck.create(url="https://api.spacex.land/graphql")
    >>> query = '''
    {
        launches(limit: 5) @frame {
            mission_name
            launch_date_local
        }
    }
    '''
    >>> df, = read_graphql(query)
    """
    return functools.partial(
        read_graphql,
        url=url,
        headers=headers,
        separator=separator,
        client=client,
    )

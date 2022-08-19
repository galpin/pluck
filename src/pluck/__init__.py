# Copyright (c) 2022 Martin Galpin. See LICENSE for details.
"""
Pluck is a GraphQL client that transforms queries into Pandas data-frames.

For full documentation see: https://github.com/galpin/pluck

Examples
--------

**Basic Usage**

>>> import pluck
>>> query = '''
{
  launches(limit: 5) @frame {
    mission_name
    launch_date_local
    rocket {
      rocket_name
    }
  }
}
'''
>>> df, = pluck.read_graphql(query, url="https://api.spacex.land/graphql")
>>> df
"""

from . import client
from ._exceptions import PluckError, GraphQLError
from ._pluck import Response, create, read_graphql

__all__ = [
    "client",
    "create",
    "GraphQLError",
    "PluckError",
    "Response",
    "read_graphql",
]

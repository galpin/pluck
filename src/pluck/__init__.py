"""
Pluck is a GraphQL client that transforms queries into Pandas data-frames.

The easiest way to get started is to run `pluck.execute` with a query.

>>> import pluck
>>>
>>> SpaceX = "https://api.spacex.land/graphql"
>>>
>>> query = '''
>>> {
>>>   launches(limit: 5) {
>>>     mission_name
>>>     launch_date_local
>>>     rocket {
>>>       rocket_name
>>>     }
>>>   }
>>> }'''
>>> df, = pluck.execute(query, url=SpaceX)
>>> df

See the README.md on GitHub for more information.
"""

from . import client
from ._pluck import create, execute, Response

__all__ = (
    "create",
    "execute",
    "Response",
    "client",
)

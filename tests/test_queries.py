# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import pytest

from pluck import GraphQLError


def test_multiple_frames_with_same_name_raises_error(ctx):
    with pytest.raises(GraphQLError):
        ctx.read_graphql(
            query="""
            {
              launches @frame {
                id
              }
              launches @frame {
                id
              }
            }
            """,
        )

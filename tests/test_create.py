# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import pluck
from pluck import PluckResponse
from .conftest import StubGraphQLClient


def test_create_delegates_to_read_graphql(monkeypatch):
    expected_query = """
        query ($id: ID!) {
          launch(id: $id) {
            id
          }
        }
    """
    expected_variables = {"id": 1}
    expected_url = "http://localhost/graphql"
    expected_headers = {
        "token1": "secret1",
        "token2": "secret2",
    }
    expected_separator = "!"
    expected_client = StubGraphQLClient({"data": {}})
    expected_response = PluckResponse({}, None, {})
    actual_args = []
    actual_kwargs = {}

    def read_graphql(*args, **kwargs):
        actual_args.extend(args)
        actual_kwargs.update(**kwargs)
        return expected_response

    monkeypatch.setattr("pluck._pluck.read_graphql", read_graphql)

    sut = pluck.create(
        url=expected_url,
        headers=expected_headers,
        separator=expected_separator,
        client=expected_client,
    )
    actual = sut(expected_query, expected_variables)

    assert actual is expected_response
    assert actual_args[0] == expected_query
    assert actual_args[1] == expected_variables
    assert actual_kwargs["url"] == expected_url
    assert actual_kwargs["headers"] == expected_headers
    assert actual_kwargs["separator"] == expected_separator
    assert actual_kwargs["client"] is expected_client

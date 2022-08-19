# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import json
import urllib.error

import pandas as pd
import pytest

from .conftest import StubGraphQLClient


def test_url(ctx):
    expected = "http://localhost/graphql"

    ctx.read_graphql(
        query="{ launches { id } }",
        url=expected,
    )

    assert ctx.last_request().url == expected


def test_query_variables(ctx):
    expected = {"id": 1}

    ctx.read_graphql(
        query="""
            query ($id: ID!) {
              launch(id: $id) {
                id
              }
            }
        """,
        variables=expected,
    )

    body = json.loads(ctx.last_request().body)
    assert body["variables"] == expected


def test_headers(ctx):
    expected = {
        "token1": "secret1",
        "token2": "secret2",
    }

    ctx.read_graphql(
        query="{ launches { id } }",
        headers=expected,
    )

    actual = ctx.last_request().headers
    for header, value in expected.items():
        assert header in actual
        assert actual[header] == value


def test_separator(ctx):
    ctx.setup_response(
        data={
            "launches": [
                {
                    "id": "9",
                    "ships": [
                        {"id": "AMERICANISLANDER"},
                    ],
                }
            ]
        }
    )
    expected = pd.DataFrame(
        {
            "id": ["9"],
            "ships/id": ["AMERICANISLANDER"],
        }
    )

    (df,) = ctx.read_graphql(
        query="""
            {
              launches @frame {
                id
                ships {
                  id
                }
              }
            }
        """,
        separator="/",
    )

    assert df.equals(expected)


def test_client(ctx):
    expected = {"data": {"launches": [{"id": "1"}]}}
    client = StubGraphQLClient(expected)

    actual = ctx.read_graphql(
        query="{ launches { id } }",
        client=client,
    )

    assert actual.data == {"launches": [{"id": "1"}]}


def test_when_query_is_none(ctx):
    with pytest.raises(AssertionError):
        ctx.read_graphql(query=None)


def test_when_url_is_none(ctx):
    with pytest.raises(AssertionError):
        ctx.read_graphql(
            query="{ launches { id } }",
            url=None,
        )


@pytest.mark.parametrize("status_code", [400, 500])
def test_when_http_status_is_non_2xx(ctx, status_code):
    ctx.setup_response(status_code=status_code)

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        ctx.read_graphql(
            query="{ launches { id } }",
        )

    assert excinfo.value.code == status_code

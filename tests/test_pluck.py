import json
from typing import Callable, Dict, Optional

import httpretty
import pytest
from httpretty.core import HTTPrettyRequest

import pluck
from pluck.client import GraphQLClient, GraphQLRequest, GraphQLResponse


class MockGraphQLClient(GraphQLClient):
    def __init__(self, response: Dict):
        self.response = GraphQLResponse.from_dict(response)

    def execute(self, request: GraphQLRequest) -> GraphQLResponse:
        return self.response


def test_when_url():
    expected = "http://spacex/graphql"

    def verify(request, _, __, ___):
        assert request.url == expected

    _test_execute(verify=verify, url=expected)


def test_when_query_variables():
    query = "query ($id: Int) { field(id: $id) { value } }"
    expected = {"id": 1}

    def verify(_, body, __, ___):
        assert body["variables"] == expected

    _test_execute(verify=verify, query=query, variables=expected)


def test_when_custom_headers():
    expected = {"token": "secret"}

    def verify(request, _, __, ___):
        assert request.headers["token"] == expected["token"]

    _test_execute(verify=verify, headers=expected)


def test_when_custom_client():
    expected = {"data": {"field": "value"}}
    client = MockGraphQLClient(expected)

    actual = pluck.execute(
        "{ field }",
        client=client,
        url="http://spacex/graphql",
    )

    assert actual.data == {"field": "value"}


def test_url_must_be_specified():
    with pytest.raises(AssertionError):
        pluck.execute("{ field }", url=None)


def test_query_must_be_specified():
    with pytest.raises(AssertionError):
        pluck.execute(None, url="http://spacex/graphql")


def test_create():
    expected_url = "http://spacex/graphql"
    expected_headers = {"token": "secret"}

    execute = pluck.create(
        url=expected_url,
        headers=expected_headers,
    )

    def verify(request, _, __, ___):
        assert request.url == expected_url
        assert request.headers["token"] == expected_headers["token"]

    _test_execute(
        verify=verify,
        url=expected_url,
        headers=expected_headers,
        execute=execute,
    )


@httpretty.activate
def _test_execute(
    query: Optional[str] = None,
    variables: Optional[dict] = None,
    response: Optional[dict] = None,
    headers: Optional[dict] = None,
    verify: Optional[Callable[[HTTPrettyRequest, dict, str, dict], None]] = None,
    url: str = "http://spacex/graphql",
    execute=None,
):
    query = query or "{ launch { id } }"
    variables = variables or {}
    response = response or {"data": {"launch": {"id": "1"}}}

    def callback(request_, uri, headers_):
        body = json.loads(request_.body)
        if verify:
            verify(request_, body, uri, headers_)
        return 200, {}, json.dumps(response)

    httpretty.register_uri(httpretty.POST, url, body=callback)

    if not execute:
        response = pluck.execute(query, variables, url=url, headers=headers)
    else:
        response = execute(query, variables)

    assert httpretty.has_request()
    assert response is not None
    return response

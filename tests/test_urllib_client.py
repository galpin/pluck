import json
from typing import Optional, Callable

import httpretty
import pytest
from httpretty.core import HTTPrettyRequest

from pluck.client import GraphQLRequest, UrllibGraphQLClient

pytestmark = pytest.mark.skip(reason="httpretty is incompatible with this environment")


def test_request_url():
    expected = "http://spacex/graphql"

    def verify(request, _, __, ___):
        assert request.url == expected

    _test_execute(verify=verify, url=expected)


def test_request_method_is_post():
    def verify(request, _, __, ___):
        assert request.method == "POST"

    _test_execute(verify=verify)


def test_request_content_type_is_application_json():
    def verify(request, _, __, ___):
        assert request.headers["Content-Type"] == "application/json"

    _test_execute(verify=verify)


def test_request_when_custom_headers():
    expected = {
        "token": "12345",
    }

    def verify(request, _, __, ___):
        assert request.headers["token"] == expected["token"]

    _test_execute(verify=verify, headers=expected)


def test_request_body_contains_query_and_variables():
    query = "query(id: ID!) { launch(id: id) }"
    variables = {"id": "1"}

    def verify(_, body, __, ___):
        assert body["query"] == query
        assert body["variables"] == variables

    _test_execute(query, variables, verify=verify)


def test_request_variables_are_optional():
    def verify(_, body, __, ___):
        assert "query" in body
        assert "variables" not in body

    _test_execute(verify=verify)


def test_request_response_when_only_data():
    expected = {"data": {"launch": {"id": "1"}}}

    actual = _test_execute(response=expected)

    assert actual.data == expected["data"]
    assert actual.errors is None


def test_request_response_when_data_and_errors():
    expected = {
        "data": {"launch": {"id": "1"}},
        "errors": [{"message": "error"}],
    }

    actual = _test_execute(response=expected)

    assert actual.data == expected["data"]
    assert actual.errors == expected["errors"]


@httpretty.activate
def _test_execute(
    query: Optional[str] = None,
    variables: Optional[dict] = None,
    response: Optional[dict] = None,
    headers: Optional[dict] = None,
    verify: Optional[Callable[[HTTPrettyRequest, dict, str, dict], None]] = None,
    url: str = "http://spacex/graphql",
):
    query = query or "{ launch { id } }"
    variables = variables or {}
    request = GraphQLRequest(url, query, variables, headers)
    response = response or {"data": {"launch": {"id": "1"}}}
    sut = UrllibGraphQLClient()

    def callback(request_, uri, headers_):
        body = json.loads(request_.body)
        if verify:
            verify(request_, body, uri, headers_)
        return 200, {}, json.dumps(response)

    httpretty.register_uri(httpretty.POST, url, body=callback)

    response = sut.execute(request)
    assert httpretty.has_request()
    assert response is not None
    return response

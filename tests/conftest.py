# Copyright (c) 2022 Martin Galpin. See LICENSE for details.

import json
from dataclasses import dataclass
from typing import Dict, Optional

import httpretty
import pytest
from httpretty.core import HTTPrettyRequest

import pluck
from pluck.client import GraphQLClient, GraphQLRequest, GraphQLResponse


@pytest.fixture
def ctx():
    with httpretty.enabled(verbose=True, allow_net_connect=False):
        yield TestContext()


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: Optional[Dict]
    headers: Optional[Dict]

    @classmethod
    def success(cls):
        return cls(status_code=200, body=None, headers=None)


_NONE = object()


class TestContext:
    response: HttpResponse

    def __init__(self):
        self.response = HttpResponse.success()
        self.sut = pluck.read_graphql
        self.setup_empty_response()

    def setup_response(
        self,
        data=None,
        errors=None,
        body=_NONE,
        status_code=200,
        headers=None,
    ):
        if body is _NONE:
            body = self._build_body(data, errors)
        self.response = HttpResponse(status_code, body, headers)

    def setup_empty_response(self):
        self.setup_response(data={})

    def last_request(self) -> HTTPrettyRequest:
        return httpretty.last_request()

    def read_graphql(
        self,
        query: Optional[str] = None,
        variables: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        url: str = "https://api.spacex.land/graphql",
        **kwargs,
    ):
        httpretty.register_uri(
            httpretty.POST,
            url,
            body=json.dumps(self.response.body),
            status=self.response.status_code,
        )

        actual = self.sut(
            query,
            variables=variables,
            url=url,
            headers=headers,
            **kwargs,
        )

        assert actual is not None
        return actual

    @staticmethod
    def _build_body(data, errors):
        body = {}
        if data is not None:
            body["data"] = data
        if errors is not None:
            body["errors"] = errors
        return body


class StubGraphQLClient(GraphQLClient):
    def __init__(self, body: Dict):
        self.response = GraphQLResponse.from_dict(body)

    def execute(self, request: GraphQLRequest) -> GraphQLResponse:
        return self.response

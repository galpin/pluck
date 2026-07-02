import importlib.util

import pytest
from graphql import build_schema, get_introspection_query, graphql_sync

import pluck
from pluck.client import GraphQLClient, GraphQLRequest, GraphQLResponse
from pluck.generator import (
    GenerateRequest,
    QueryGenerator,
    _build_agentic_task,
    _extract_query,
    _render_root_fields,
    _schema_file,
    _search_schema,
    _show_type,
)

URL = "http://api/graphql"
QUESTION = "the latest launches and their rockets"

SCHEMA = """
type Query {
  launches(limit: Int): [Launch!]
}

type Launch {
  mission_name: String
  rocket: Rocket
}

type Rocket {
  rocket_name: String
}
"""

DATA = {
    "data": {
        "launches": [
            {"mission_name": "FalconSat", "rocket": {"rocket_name": "Falcon 1"}},
            {"mission_name": "DemoSat", "rocket": {"rocket_name": "Falcon 1"}},
        ]
    }
}

GENERATED_QUERY = (
    "{ launches(limit: 5) @frame { mission_name rocket { rocket_name } } }"
)


class MockGraphQLClient(GraphQLClient):
    """
    Answers introspection requests by running them against a real schema, and
    answers every other request with canned data. Records every request. If
    `error_on` is set, any data query containing that marker returns an error.
    """

    def __init__(
        self,
        schema_sdl: str = SCHEMA,
        data_response: dict = DATA,
        error_on: str | None = None,
    ):
        self._schema = build_schema(schema_sdl)
        self._data_response = data_response
        self._error_on = error_on
        self.requests: list[GraphQLRequest] = []

    def execute(self, request: GraphQLRequest) -> GraphQLResponse:
        self.requests.append(request)
        if "__schema" in request.query:
            result = graphql_sync(self._schema, get_introspection_query())
            errors = [e.formatted for e in result.errors] if result.errors else None
            return GraphQLResponse(result.data, errors)
        if self._error_on is not None and self._error_on in request.query:
            return GraphQLResponse(None, [{"message": "boom"}])
        return GraphQLResponse.from_dict(self._data_response)

    @property
    def data_requests(self) -> list[GraphQLRequest]:
        return [r for r in self.requests if "__schema" not in r.query]

    @property
    def introspection_requests(self) -> list[GraphQLRequest]:
        return [r for r in self.requests if "__schema" in r.query]


class FakeQueryGenerator(QueryGenerator):
    """
    Captures the GenerateRequest, optionally probes the endpoint, and returns a
    canned query.
    """

    def __init__(self, query: str = GENERATED_QUERY, probe: str | None = None):
        self._query = query
        self._probe = probe
        self.request: GenerateRequest | None = None
        self.probe_result: GraphQLResponse | None = None

    def generate(self, request: GenerateRequest) -> str:
        self.request = request
        if self._probe is not None:
            self.probe_result = request.execute(self._probe)
        return self._query


def test_ask_returns_frames():
    client = MockGraphQLClient()
    response = pluck.ask(
        QUESTION, url=URL, client=client, generator=FakeQueryGenerator()
    )

    assert list(response.frames.keys()) == ["launches"]
    frame = response.frames["launches"]
    assert list(frame["mission_name"]) == ["FalconSat", "DemoSat"]
    assert list(frame["rocket.rocket_name"]) == ["Falcon 1", "Falcon 1"]


def test_ask_sets_query():
    response = pluck.ask(
        QUESTION,
        url=URL,
        client=MockGraphQLClient(),
        generator=FakeQueryGenerator(),
    )

    assert response.query == GENERATED_QUERY


def test_ask_passes_sdl_to_generator():
    generator = FakeQueryGenerator()

    pluck.ask(QUESTION, url=URL, client=MockGraphQLClient(), generator=generator)

    assert generator.request is not None
    schema = generator.request.schema
    assert "type Launch" in schema
    assert "mission_name" in schema
    assert "rocket_name" in schema


def test_ask_probe_executes_raw_query():
    generator = FakeQueryGenerator(probe="{ launches { mission_name } }")

    pluck.ask(QUESTION, url=URL, client=MockGraphQLClient(), generator=generator)

    assert generator.probe_result is not None
    assert generator.probe_result.data == DATA["data"]


def test_ask_probe_strips_frame_directive():
    generator = FakeQueryGenerator(probe="{ launches @frame { mission_name } }")
    client = MockGraphQLClient()

    pluck.ask(QUESTION, url=URL, client=client, generator=generator)

    assert client.data_requests, "expected at least one data request"
    for request in client.data_requests:
        assert "@frame" not in request.query


def test_ask_probe_handles_invalid_query():
    generator = FakeQueryGenerator(probe="{ this is ! invalid")
    client = MockGraphQLClient()

    # Must not raise: the invalid query is reported back as an observation.
    pluck.ask(QUESTION, url=URL, client=client, generator=generator)

    assert generator.probe_result is not None
    assert generator.probe_result.data is None
    assert generator.probe_result.errors
    # The invalid query never reached the server.
    assert all("invalid" not in r.query for r in client.data_requests)


def test_ask_passes_headers():
    headers = {"token": "secret"}
    client = MockGraphQLClient()

    pluck.ask(
        QUESTION,
        url=URL,
        headers=headers,
        client=client,
        generator=FakeQueryGenerator(),
    )

    assert len(client.requests) >= 2
    assert all(r.headers == headers for r in client.requests)


def test_ask_reuses_client_and_introspects_once():
    client = MockGraphQLClient()

    pluck.ask(QUESTION, url=URL, client=client, generator=FakeQueryGenerator())

    # Exactly one introspection + one data query (the fake generator never probes).
    assert len(client.introspection_requests) == 1
    assert len(client.data_requests) == 1


def test_ask_implicit_mode_query():
    generator = FakeQueryGenerator(query="{ launches { mission_name } }")

    response = pluck.ask(
        QUESTION, url=URL, client=MockGraphQLClient(), generator=generator
    )

    assert list(response.frames.keys()) == ["default"]


def test_ask_returns_errors_when_query_fails():
    # The generator returns a query the server rejects; ask surfaces the errors on
    # the response instead of raising (there is no fallback).
    generator = FakeQueryGenerator(query="{ launches { mission_name MARKER } }")
    client = MockGraphQLClient(error_on="MARKER")

    response = pluck.ask(QUESTION, url=URL, client=client, generator=generator)

    assert response.errors
    assert response.query == "{ launches { mission_name MARKER } }"


def test_ask_introspection_error_raises():
    class IntrospectionErrorClient(GraphQLClient):
        def execute(self, request: GraphQLRequest) -> GraphQLResponse:
            return GraphQLResponse(None, [{"message": "introspection disabled"}])

    with pytest.raises(ValueError, match="introspect"):
        pluck.ask(
            QUESTION,
            url=URL,
            client=IntrospectionErrorClient(),
            generator=FakeQueryGenerator(),
        )


def test_create_ask_binds_options():
    client = MockGraphQLClient()
    created = pluck.create(url=URL, client=client, generator=FakeQueryGenerator())

    response = created.ask(QUESTION)

    assert list(response.frames.keys()) == ["launches"]
    assert response.query == GENERATED_QUERY


def test_extract_query_strips_graphql_fence():
    assert (
        _extract_query("```graphql\n{ launches { id } }\n```") == "{ launches { id } }"
    )


def test_extract_query_strips_plain_fence():
    assert _extract_query("```\n{ launches { id } }\n```") == "{ launches { id } }"


def test_extract_query_passthrough_when_no_fence():
    assert _extract_query("  { launches { id } }  ") == "{ launches { id } }"


# --- schema-exploration tools (the agent's window into the schema file) ---


def test_search_schema_finds_type_and_field():
    schema = build_schema(SCHEMA)

    result = _search_schema(schema, "rocket")

    assert "Rocket" in result  # type-name match
    assert "Launch.rocket" in result  # field match on another type
    assert "Rocket.rocket_name" in result


def test_search_schema_reports_no_match():
    schema = build_schema(SCHEMA)

    assert "No types or fields match" in _search_schema(schema, "spaceship")


def test_show_type_returns_sdl():
    schema = build_schema(SCHEMA)

    result = _show_type(schema, "Launch")

    assert result.startswith("type Launch")
    assert "mission_name" in result
    assert "rocket: Rocket" in result


def test_show_type_reports_unknown_name():
    schema = build_schema(SCHEMA)

    assert "No type named 'Nope'" in _show_type(schema, "Nope")


def test_render_root_fields_lists_query_fields_with_types():
    schema = build_schema(SCHEMA)

    result = _render_root_fields(schema)

    assert "Query:" in result
    assert "launches(limit: Int): [Launch!]" in result


def test_build_agentic_task_is_schema_free():
    schema = build_schema(SCHEMA)

    task = _build_agentic_task(QUESTION, schema)

    # Contains the question, the @frame docs, and the root-field seed...
    assert QUESTION in task
    assert "@frame" in task
    assert "launches(limit: Int): [Launch!]" in task
    # ...but NOT the full schema: type definitions are only reachable via tools.
    assert "type Launch" not in task
    assert "type Rocket" not in task
    assert "rocket_name" not in task  # a deep field, reachable only via show_type


def test_schema_file_writes_sdl_and_cleans_up():
    with _schema_file(SCHEMA) as path:
        assert path.exists()
        assert path.read_text() == SCHEMA

    assert not path.exists()


# --- schema reuse ---


def test_ask_uses_supplied_schema_without_introspecting():
    generator = FakeQueryGenerator()
    client = MockGraphQLClient()

    response = pluck.ask(
        QUESTION, url=URL, client=client, generator=generator, schema=SCHEMA
    )

    assert client.introspection_requests == []  # no introspection round-trip
    assert generator.request is not None
    assert generator.request.schema == SCHEMA
    assert list(response.frames.keys()) == ["launches"]


def test_create_ask_introspects_schema_once_across_calls():
    client = MockGraphQLClient()
    created = pluck.create(url=URL, client=client, generator=FakeQueryGenerator())

    created.ask(QUESTION)
    created.ask(QUESTION)

    assert len(client.introspection_requests) == 1  # introspected once, then reused
    assert len(client.data_requests) == 2  # one execution per call


def test_default_generator_raises_without_dependency():
    if importlib.util.find_spec("smolagents") is not None:
        pytest.skip("smolagents is installed")
    request = GenerateRequest(QUESTION, SCHEMA, lambda q: GraphQLResponse(None, None))

    with pytest.raises(ImportError, match=r"pluck-graphql\[llm\]"):
        pluck.generator.AgenticQueryGenerator().generate(request)


def test_smolagents_import_surface_when_installed():
    pytest.importorskip("smolagents")
    from pluck.generator import _import_smolagents

    smol = _import_smolagents()

    assert smol.ToolCallingAgent is not None
    assert callable(smol.tool)
    assert callable(smol.make_default_model)

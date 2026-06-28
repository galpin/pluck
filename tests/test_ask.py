import importlib.util

import pytest
from graphql import build_schema, get_introspection_query, graphql_sync

import pluck
from pluck.client import GraphQLClient, GraphQLRequest, GraphQLResponse
from pluck.generator import (
    GenerateRequest,
    QueryGenerator,
    SingleShotQueryGenerator,
    _build_single_shot_system,
    _build_single_shot_user,
    _extract_query,
    _generate_single_shot,
    _validate_query,
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
    answers every other request with canned data. Records every request.
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
        self.call_count = 0

    def generate(self, request: GenerateRequest) -> str:
        self.call_count += 1
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


def test_single_shot_system_holds_schema_and_frame_docs():
    # The schema lives in the stable system message (the cacheable prefix), not
    # the user message.
    system = _build_single_shot_system("type Query { a: Int }")

    assert "type Query { a: Int }" in system
    assert "@frame" in system
    assert "execute_graphql" not in system  # single-shot must not mention the tool


def test_single_shot_user_holds_question_not_schema():
    user = _build_single_shot_user("my question")

    assert "my question" in user
    assert "type Query" not in user  # the schema is not duplicated into the user turn


def test_single_shot_user_includes_errors_on_retry():
    user = _build_single_shot_user("q", ["Cannot query field 'nope'."])

    assert "Cannot query field 'nope'." in user


# --- local validation ---


def test_validate_query_accepts_valid():
    assert _validate_query(SCHEMA, "{ launches { mission_name } }") == []


def test_validate_query_rejects_unknown_field():
    assert _validate_query(SCHEMA, "{ launches { nope } }")


def test_validate_query_rejects_syntax_error():
    assert _validate_query(SCHEMA, "{ this is ! invalid")


def test_validate_query_ignores_frame_directive():
    assert _validate_query(SCHEMA, "{ launches @frame { mission_name } }") == []


# --- single-shot generation ---


def test_single_shot_returns_first_valid():
    calls = []

    def complete(system, user):
        calls.append((system, user))
        return "{ launches { mission_name } }"

    query = _generate_single_shot(complete, QUESTION, SCHEMA, max_attempts=2)

    assert query == "{ launches { mission_name } }"
    assert len(calls) == 1


def test_single_shot_retries_with_stable_system_and_errors_in_user():
    calls = []

    def complete(system, user):
        calls.append((system, user))
        if len(calls) == 1:
            return "{ launches { nope } }"  # invalid -> triggers a retry
        return "{ launches { mission_name } }"

    query = _generate_single_shot(complete, QUESTION, SCHEMA, max_attempts=2)

    assert query == "{ launches { mission_name } }"
    assert len(calls) == 2
    # The system message (cacheable prefix) is identical across attempts; only the
    # user message changes, carrying the validation errors.
    assert calls[0][0] == calls[1][0]
    assert "previous attempt was invalid" in calls[1][1]


def test_single_shot_gives_up_after_max_attempts():
    calls = []

    def complete(system, user):
        calls.append((system, user))
        return "{ launches { nope } }"  # always invalid

    query = _generate_single_shot(complete, QUESTION, SCHEMA, max_attempts=3)

    assert len(calls) == 3
    assert query == "{ launches { nope } }"


# --- staged escalation in ask ---

BAD_MARKER = "MARKER"
GOOD_FALLBACK_QUERY = "{ launches @frame { mission_name } }"


def test_ask_falls_back_on_server_errors():
    primary = FakeQueryGenerator(query="{ launches { mission_name MARKER } }")
    fallback = FakeQueryGenerator(query=GOOD_FALLBACK_QUERY)
    client = MockGraphQLClient(error_on=BAD_MARKER)

    response = pluck.ask(
        QUESTION, url=URL, client=client, generator=primary, fallback=fallback
    )

    assert list(response.frames.keys()) == ["launches"]
    assert response.query == GOOD_FALLBACK_QUERY
    assert primary.call_count == 1
    assert fallback.call_count == 1


def test_ask_no_fallback_when_primary_succeeds():
    primary = FakeQueryGenerator()
    fallback = FakeQueryGenerator()
    client = MockGraphQLClient()

    pluck.ask(QUESTION, url=URL, client=client, generator=primary, fallback=fallback)

    assert fallback.call_count == 0
    assert len(client.introspection_requests) == 1
    assert len(client.data_requests) == 1


def test_ask_fallback_on_invalid_query():
    primary = FakeQueryGenerator(query="{ this is ! invalid")
    fallback = FakeQueryGenerator(query=GOOD_FALLBACK_QUERY)
    client = MockGraphQLClient()

    response = pluck.ask(
        QUESTION, url=URL, client=client, generator=primary, fallback=fallback
    )

    assert list(response.frames.keys()) == ["launches"]
    assert fallback.call_count == 1


def test_ask_fallback_disabled():
    primary = FakeQueryGenerator(query="{ launches { mission_name MARKER } }")
    client = MockGraphQLClient(error_on=BAD_MARKER)

    response = pluck.ask(
        QUESTION, url=URL, client=client, generator=primary, fallback=False
    )

    assert response.errors
    assert primary.call_count == 1


def test_ask_returns_last_errors_when_all_fail():
    primary = FakeQueryGenerator(query="{ launches { mission_name MARKER } }")
    fallback = FakeQueryGenerator(query="{ launches { mission_name MARKER } }")
    client = MockGraphQLClient(error_on=BAD_MARKER)

    response = pluck.ask(
        QUESTION, url=URL, client=client, generator=primary, fallback=fallback
    )

    assert response.errors
    assert primary.call_count == 1
    assert fallback.call_count == 1


def test_create_ask_forwards_fallback():
    primary = FakeQueryGenerator(query="{ launches { mission_name MARKER } }")
    fallback = FakeQueryGenerator(query=GOOD_FALLBACK_QUERY)
    client = MockGraphQLClient(error_on=BAD_MARKER)
    created = pluck.create(url=URL, client=client, generator=primary, fallback=fallback)

    response = created.ask(QUESTION)

    assert response.query == GOOD_FALLBACK_QUERY
    assert fallback.call_count == 1


# --- schema reuse (prompt caching) ---


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


def test_default_generators_raise_without_dependency():
    if importlib.util.find_spec("smolagents") is not None:
        pytest.skip("smolagents is installed")
    request = GenerateRequest(QUESTION, SCHEMA, lambda q: GraphQLResponse(None, None))

    for generator in (
        SingleShotQueryGenerator(),
        pluck.generator.AgenticQueryGenerator(),
    ):
        with pytest.raises(ImportError, match=r"pluck-graphql\[llm\]"):
            generator.generate(request)


def test_smolagents_import_surface_when_installed():
    pytest.importorskip("smolagents")
    from pluck.generator import _import_smolagents

    smol = _import_smolagents()

    assert smol.ToolCallingAgent is not None
    assert callable(smol.tool)
    assert callable(smol.make_default_model)

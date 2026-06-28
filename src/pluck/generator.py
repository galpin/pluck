import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

import graphql

from ._parser import QueryParser
from .client import GraphQLResponse

__all__ = (
    "GenerateRequest",
    "QueryGenerator",
    "SingleShotQueryGenerator",
    "AgenticQueryGenerator",
)

# Cap the size of a probe response embedded in the agent's observation so that a
# large result set does not blow up the prompt (and token cost).
_MAX_RESPONSE_CHARS = 4_000

_FENCE_RE = re.compile(r"```(?:[a-zA-Z]*)\n(.*?)```", re.DOTALL)

# Shared explanation of pluck's `@frame` directive, embedded in every prompt.
_FRAME_PRIMER = """\
The query is executed by `pluck`, which transforms the GraphQL response into
Pandas data-frames. `pluck` adds one custom directive, `@frame`, that you MAY use
to mark the parts of the response that should become data-frames:
  - Place `@frame` on a field whose value (or list of values) should become a
    data-frame, e.g. `launches(limit: 5) @frame { ... }`.
  - It can be placed on object fields, list fields or leaf fields.
  - Nested `@frame` directives within a list are combined into one data-frame.
  - `@frame` is a pluck-only directive and is removed before the query is sent to
    the server, so it never causes a server-side error.
  - If you use no `@frame` directive, the whole response becomes one data-frame."""


@dataclass(frozen=True)
class GenerateRequest:
    """
    A request to generate a GraphQL query from a natural-language question.

    Args:
        question: The natural-language question to answer.
        schema: The schema of the target GraphQL API, as SDL.
        execute: A callable that executes a (raw) GraphQL query against the API
            and returns the response. The pluck-only `@frame` directive is
            stripped before the query is sent, so an implementation can use this
            to test candidate queries and self-correct.
    """

    question: str
    schema: str
    execute: Callable[[str], GraphQLResponse]


class QueryGenerator(ABC):
    """
    Generates a GraphQL query that answers a natural-language question.
    """

    @abstractmethod
    def generate(self, request: GenerateRequest) -> str:
        """
        Generate a GraphQL query for the given request.

        Args:
            request: The request describing the question and target API.

        Returns:
            A GraphQL query (which may include the pluck `@frame` directive).
        """
        raise NotImplementedError()


class SingleShotQueryGenerator(QueryGenerator):
    """
    A `QueryGenerator` that writes the query with a single LLM call.

    The model is given the API schema and asked for a query. The query is then
    validated locally against the schema (no network call); if it is invalid, the
    validation errors are fed back for one corrective attempt. This is the cheap,
    default strategy used by `pluck.ask` (which escalates to an agent only if the
    generated query actually fails).

    `smolagents` is an optional dependency. Install it with::

        pip install "pluck-graphql[llm]"

    Args:
        model:
            The language model to use. This may be any `smolagents` model instance
            (for example ``LiteLLMModel(model_id="gpt-4o")``). If ``None``, a
            default ``smolagents.InferenceClientModel`` is used (which requires a
            Hugging Face token, e.g. via the ``HF_TOKEN`` environment variable).
        max_attempts:
            The maximum number of LLM calls. ``1`` disables the validate-and-retry
            behaviour (a pure single-shot prompt).
    """

    def __init__(self, model: Any = None, *, max_attempts: int = 2):
        self._model = model
        self._max_attempts = max_attempts

    def generate(self, request: GenerateRequest) -> str:
        complete = _resolve_complete(self._model)
        return _generate_single_shot(
            complete, request.question, request.schema, self._max_attempts
        )


class AgenticQueryGenerator(QueryGenerator):
    """
    A `QueryGenerator` that uses a `smolagents` agent to write the query.

    The agent is given the API schema and a tool to execute candidate queries
    against the live endpoint, so it can iterate until it produces a query that is
    valid and answers the question. This is more robust than
    `SingleShotQueryGenerator` but makes several LLM calls and queries the API
    while generating.

    `smolagents` is an optional dependency. Install it with::

        pip install "pluck-graphql[llm]"

    Args:
        model:
            The language model to use (see `SingleShotQueryGenerator`).
        max_steps:
            The maximum number of reasoning steps the agent may take.
    """

    def __init__(self, model: Any = None, *, max_steps: int = 6):
        self._model = model
        self._max_steps = max_steps

    def generate(self, request: GenerateRequest) -> str:
        smol = _import_smolagents()
        model = self._model if self._model is not None else smol.make_default_model()
        agent = smol.ToolCallingAgent(
            tools=[_make_execute_tool(smol.tool, request)],
            model=model,
            max_steps=self._max_steps,
        )
        result = agent.run(_build_agentic_task(request.question, request.schema))
        return _extract_query(str(result))


def _generate_single_shot(
    complete: Callable[[str, str], str],
    question: str,
    schema: str,
    max_attempts: int = 2,
) -> str:
    # The system message (instructions + schema) is identical on every attempt and
    # across calls, so it forms a stable prefix that LLM providers can cache. Only
    # the user message (the question and any validation errors) varies.
    system = _build_single_shot_system(schema)
    errors: Optional[List[str]] = None
    query = ""
    for _ in range(max(1, max_attempts)):
        user = _build_single_shot_user(question, errors)
        query = _extract_query(complete(system, user))
        errors = _validate_query(schema, query)
        if not errors:
            return query
    return query


def _validate_query(schema_sdl: str, query: str) -> List[str]:
    """
    Validate a query against the schema locally, returning a list of error
    messages (empty if the query is valid). The pluck `@frame` directive is
    stripped first. Validation never raises: any internal failure returns no
    errors so that generation is never blocked by validation.
    """
    try:
        server_query = QueryParser(query).parse().query
        schema = graphql.build_schema(schema_sdl)
        document = graphql.parse(server_query)
        return [error.message for error in graphql.validate(schema, document)]
    except graphql.GraphQLError as e:
        return [str(e)]
    except Exception:
        return []


def _make_execute_tool(tool_decorator: Callable, request: GenerateRequest):
    @tool_decorator
    def execute_graphql(query: str) -> str:
        """
        Execute a GraphQL query against the API and return the JSON response.

        Use this to test a query and inspect the data that is returned. If the
        query is invalid, the errors are returned so that you can fix the query
        and try again. The pluck `@frame` directive is ignored when testing.

        Args:
            query: The GraphQL query to execute.
        """
        try:
            response = request.execute(query)
        except Exception as e:  # noqa: BLE001 - reported to the agent as an observation
            return json.dumps({"data": None, "errors": [{"message": str(e)}]})
        return _format_response(response)

    return execute_graphql


def _format_response(response: GraphQLResponse) -> str:
    payload = {"data": response.data, "errors": response.errors}
    text = json.dumps(payload, default=str)
    if len(text) > _MAX_RESPONSE_CHARS:
        text = text[:_MAX_RESPONSE_CHARS] + "... (truncated)"
    return text


def _build_single_shot_system(schema: str) -> str:
    # Stable, cache-friendly prefix: instructions + the (large) schema only.
    return f"""\
You are an expert at writing GraphQL queries. Write a single GraphQL query that
answers the user's question using the schema below.

{_FRAME_PRIMER}

Return ONLY the final GraphQL query, with no explanation or commentary.

# Schema (SDL)
{schema}"""


def _build_single_shot_user(question: str, errors: Optional[List[str]] = None) -> str:
    # Variable part of the prompt: the question and any validation errors.
    user = f"# Question\n{question}"
    if errors:
        joined = "\n".join(f"  - {error}" for error in errors)
        user += (
            "\n\n# Your previous attempt was invalid\n"
            "Fix these validation errors and return a corrected query:\n"
            f"{joined}"
        )
    return user


def _build_agentic_task(question: str, schema: str) -> str:
    return f"""\
You are an expert at writing GraphQL queries. Write a single GraphQL query that
answers the user's question using the schema below.

{_FRAME_PRIMER}

Use the `execute_graphql` tool to run candidate queries against the live API and
inspect the data. Iterate until the query is valid and returns the data needed to
answer the question (the `@frame` directive is ignored when testing).

When you are done, return ONLY the final GraphQL query as your answer, with no
explanation or commentary.

# Schema (SDL)
{schema}

# Question
{question}
"""


def _extract_query(text: str) -> str:
    """
    Extract a GraphQL query from a model's answer, stripping any code fences.
    """
    text = text.strip()
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text


def _resolve_complete(model: Any) -> Callable[[str, str], str]:
    resolved = _resolve_model(model)
    return lambda system, user: _smol_complete(resolved, system, user)


def _resolve_model(model: Any) -> Any:
    if model is not None:
        return model
    return _import_smolagents().make_default_model()


def _smol_complete(model: Any, system: str, user: str) -> str:
    # Send the schema-bearing instructions as a separate system message so the
    # provider can cache it as a stable prefix across attempts and calls.
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    result = model.generate(messages) if hasattr(model, "generate") else model(messages)
    content = getattr(result, "content", result)
    return content if isinstance(content, str) else str(content)


@dataclass(frozen=True)
class _Smolagents:
    ToolCallingAgent: Any
    tool: Any
    make_default_model: Callable[[], Any]


def _import_smolagents() -> _Smolagents:
    """
    Import `smolagents` lazily, raising a friendly error if it is not installed.

    All `smolagents` imports are funnelled through here so that version drift in
    the library's public API is isolated to a single place.
    """
    try:
        from smolagents import InferenceClientModel, ToolCallingAgent, tool
    except ImportError as e:
        raise ImportError(
            "The default generators require the optional 'smolagents' dependency. "
            "Install it with: pip install 'pluck-graphql[llm]'. Alternatively, "
            "pass your own QueryGenerator to pluck.ask()."
        ) from e

    def make_default_model() -> Any:
        return InferenceClientModel()

    return _Smolagents(
        ToolCallingAgent=ToolCallingAgent,
        tool=tool,
        make_default_model=make_default_model,
    )

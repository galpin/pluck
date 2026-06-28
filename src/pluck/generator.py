import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from .client import GraphQLResponse

__all__ = ("GenerateRequest", "QueryGenerator", "SmolagentsQueryGenerator")

# Cap the size of a probe response embedded in the agent's observation so that a
# large result set does not blow up the prompt (and token cost).
_MAX_RESPONSE_CHARS = 4_000

_FENCE_RE = re.compile(r"```(?:[a-zA-Z]*)\n(.*?)```", re.DOTALL)


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


class SmolagentsQueryGenerator(QueryGenerator):
    """
    A `QueryGenerator` that uses a `smolagents` agent to write the query.

    The agent is given the API schema and a tool to execute candidate queries
    against the live endpoint, so it can iterate until it produces a query that
    is valid and answers the question.

    `smolagents` is an optional dependency. Install it with::

        pip install "pluck-graphql[agent]"

    Args:
        model:
            The language model to use. This may be any `smolagents` model
            instance (for example ``LiteLLMModel(model_id="gpt-4o")`` or
            ``OpenAIServerModel(...)``). If ``None``, a default
            ``smolagents.InferenceClientModel`` is used (which requires a
            Hugging Face token, e.g. via the ``HF_TOKEN`` environment variable).
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
        result = agent.run(_build_task(request.question, request.schema))
        return _extract_query(str(result))


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


def _build_task(question: str, schema: str) -> str:
    return f"""\
You are an expert at writing GraphQL queries. Write a single GraphQL query that \
answers the user's question using the schema below.

The query is executed by `pluck`, which transforms the GraphQL response into \
Pandas data-frames. `pluck` adds one custom directive, `@frame`, that you MAY \
use to mark the parts of the response that should become data-frames:
  - Place `@frame` on a field whose value (or list of values) should become a \
data-frame, e.g. `launches(limit: 5) @frame {{ ... }}`.
  - It can be placed on object fields, list fields or leaf fields.
  - Nested `@frame` directives within a list are combined into one data-frame.
  - `@frame` is a pluck-only directive and is removed before the query is sent \
to the server, so it never causes a server-side error.
  - If you use no `@frame` directive, the whole response becomes one data-frame.

Use the `execute_graphql` tool to run candidate queries against the live API \
and inspect the data. Iterate until the query is valid and returns the data \
needed to answer the question (the `@frame` directive is ignored when testing).

When you are done, return ONLY the final GraphQL query as your answer, with no \
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
            "SmolagentsQueryGenerator requires the optional 'smolagents' "
            "dependency. Install it with: pip install 'pluck-graphql[agent]'. "
            "Alternatively, pass your own QueryGenerator to pluck.ask()."
        ) from e

    def make_default_model() -> Any:
        return InferenceClientModel()

    return _Smolagents(
        ToolCallingAgent=ToolCallingAgent,
        tool=tool,
        make_default_model=make_default_model,
    )

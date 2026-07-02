import contextlib
import json
import os
import re
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, List

import graphql

from .client import GraphQLResponse

__all__ = (
    "GenerateRequest",
    "QueryGenerator",
    "AgenticQueryGenerator",
)

# Cap the size of a probe response embedded in the agent's observation so that a
# large result set does not blow up the prompt (and token cost).
_MAX_RESPONSE_CHARS = 4_000

# Cap the number of root fields seeded into the task, so a huge root type does not
# defeat the point of keeping the schema out of the prompt.
_MAX_ROOT_FIELDS = 50

_FENCE_RE = re.compile(r"```(?:[a-zA-Z]*)\n(.*?)```", re.DOTALL)

# Built-in scalars and object/interface/input types, used when walking the schema.
_BUILTIN_SCALARS = frozenset({"String", "Int", "Float", "Boolean", "ID"})
_FIELDED_TYPES = (
    graphql.GraphQLObjectType,
    graphql.GraphQLInterfaceType,
    graphql.GraphQLInputObjectType,
)

# Shared explanation of pluck's `@frame` directive, embedded in the agent's task.
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


class AgenticQueryGenerator(QueryGenerator):
    """
    A `QueryGenerator` that uses a `smolagents` agent to write the query.

    Rather than placing the whole schema in the prompt, the schema is written to a
    file and the agent is given tools to explore it on demand — `search_schema` to
    find relevant types and fields, `show_type` to read a single type's
    definition — plus `execute_graphql` to run candidate queries. The agent works
    in a test-and-fix feedback loop, the way a coding agent navigates a codebase.
    This keeps even very large schemas out of the context window.

    `smolagents` is an optional dependency. Install it with::

        pip install "pluck-graphql[llm]"

    Args:
        model:
            The language model to use. This may be any `smolagents` model instance
            (for example ``LiteLLMModel(model_id="gpt-4o")``). If ``None``, a
            default ``smolagents.InferenceClientModel`` is used (which requires a
            Hugging Face token, e.g. via the ``HF_TOKEN`` environment variable).
        max_steps:
            The maximum number of reasoning steps the agent may take.
    """

    def __init__(self, model: Any = None, *, max_steps: int = 12):
        self._model = model
        self._max_steps = max_steps

    def generate(self, request: GenerateRequest) -> str:
        smol = _import_smolagents()
        model = self._model if self._model is not None else smol.make_default_model()
        with _schema_file(request.schema) as path:
            # Load and index the schema once, from disk: the file is the source the
            # tools serve slices from, so the full schema never enters the prompt.
            schema = graphql.build_schema(path.read_text())
            tools = [
                _make_search_tool(smol.tool, schema),
                _make_show_type_tool(smol.tool, schema),
                _make_execute_tool(smol.tool, request),
            ]
            agent = smol.ToolCallingAgent(
                tools=tools,
                model=model,
                max_steps=self._max_steps,
            )
            result = agent.run(_build_agentic_task(request.question, schema))
            return _extract_query(str(result))


@contextlib.contextmanager
def _schema_file(sdl: str) -> Iterator[Path]:
    """
    Write the schema (SDL) to a temporary file, yield its path, and remove it on
    exit. The agent reaches the schema only through its tools, which read it here.
    """
    fd, name = tempfile.mkstemp(prefix="pluck-schema-", suffix=".graphql")
    path = Path(name)
    try:
        with os.fdopen(fd, "w") as file:
            file.write(sdl)
        yield path
    finally:
        path.unlink(missing_ok=True)


def _make_search_tool(tool_decorator: Callable, schema: graphql.GraphQLSchema):
    @tool_decorator
    def search_schema(keyword: str) -> str:
        """
        Search the GraphQL schema for types and fields matching a keyword.

        Returns matching type names and `Type.field` entries. Use this to discover
        which parts of the schema are relevant, then call show_type for details.

        Args:
            keyword: A word to search for in type and field names.
        """
        return _search_schema(schema, keyword)

    return search_schema


def _make_show_type_tool(tool_decorator: Callable, schema: graphql.GraphQLSchema):
    @tool_decorator
    def show_type(name: str) -> str:
        """
        Show the full definition of a single named type from the GraphQL schema.

        Args:
            name: The exact name of a type (for example, one returned by
                search_schema).
        """
        return _show_type(schema, name)

    return show_type


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


def _search_schema(schema: graphql.GraphQLSchema, keyword: str) -> str:
    kw = keyword.lower()
    matches: List[str] = []
    for name, type_ in schema.type_map.items():
        if name.startswith("__") or name in _BUILTIN_SCALARS:
            continue
        if kw in name.lower():
            matches.append(name)
        if isinstance(type_, _FIELDED_TYPES):
            for field_name in type_.fields:
                if kw in field_name.lower():
                    matches.append(f"{name}.{field_name}")
    if not matches:
        return f"No types or fields match '{keyword}'. Try a different keyword."
    return "\n".join(matches)


def _show_type(schema: graphql.GraphQLSchema, name: str) -> str:
    type_ = schema.get_type(name)
    if type_ is None:
        return f"No type named '{name}'. Use search_schema to find valid type names."
    return graphql.print_type(type_)


def _render_root_fields(schema: graphql.GraphQLSchema) -> str:
    lines: List[str] = []
    roots = (
        ("Query", schema.query_type),
        ("Mutation", schema.mutation_type),
        ("Subscription", schema.subscription_type),
    )
    for label, root in roots:
        if root is None:
            continue
        lines.append(f"{label}:")
        for index, (field_name, field) in enumerate(root.fields.items()):
            if index >= _MAX_ROOT_FIELDS:
                lines.append("  ... (more — use search_schema to find them)")
                break
            lines.append(f"  {_render_field_signature(field_name, field)}")
    return "\n".join(lines)


def _render_field_signature(name: str, field: Any) -> str:
    args = ", ".join(f"{arg_name}: {arg.type}" for arg_name, arg in field.args.items())
    args = f"({args})" if args else ""
    return f"{name}{args}: {field.type}"


def _format_response(response: GraphQLResponse) -> str:
    payload = {"data": response.data, "errors": response.errors}
    text = json.dumps(payload, default=str)
    if len(text) > _MAX_RESPONSE_CHARS:
        text = text[:_MAX_RESPONSE_CHARS] + "... (truncated)"
    return text


def _build_agentic_task(question: str, schema: graphql.GraphQLSchema) -> str:
    return f"""\
You are an expert at writing GraphQL queries. Write a single GraphQL query that
answers the user's question.

The schema is large and is NOT included here. Explore it with your tools:
  - search_schema(keyword): find types and fields whose names match a keyword.
  - show_type(name): show the full definition of a single type.
  - execute_graphql(query): run a candidate query and inspect the data or errors.

Start from these root fields:
{_render_root_fields(schema)}

{_FRAME_PRIMER}

Work iteratively: explore the schema with search_schema and show_type, write a
query, run it with execute_graphql to check it works, and fix any errors. When you
are done, return ONLY the final GraphQL query, with no explanation or commentary.

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
            "The default generator requires the optional 'smolagents' dependency. "
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

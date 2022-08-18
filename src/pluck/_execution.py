import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ._json import (
    STOP,
    JsonArray,
    JsonObject,
    JsonPath,
    JsonScalar,
    JsonValue,
    JsonVisitor,
    visit,
)
from ._client import GraphQLClient, GraphQLRequest, GraphQLResponse, UrllibGraphQLClient
from ._normalization import normalize
from ._parser import ParsedQuery, QueryParser
from ._decorators import timeit
from ._libraries import DataFrame, DataFrameLibrary, PandasDataFrameLibrary

ExecutorResult = Tuple[JsonValue, Optional[List], Optional[Dict[str, DataFrame]]]
EMPTY = tuple()


@dataclass
class ExecutorOptions:
    separator: str
    client: Optional[GraphQLClient]
    library: Optional[DataFrameLibrary] = field(default=None)

    def __post_init__(self):
        assert self.separator, "separator must be specified"
        if self.client is None:
            self.client = UrllibGraphQLClient()
        if self.library is None:
            self.library = PandasDataFrameLibrary()


class Executor:
    def __init__(self, options: ExecutorOptions):
        self._options = options

    @timeit
    def execute(self, request: GraphQLRequest) -> ExecutorResult:
        parsed_query = QueryParser(request.query).parse()
        new_request = request.replace(query=parsed_query.query)
        response = self._execute(new_request)
        if not parsed_query.frames:
            frames = None
        else:
            frame_data = self._extract(parsed_query, response)
            frames = self._normalize(frame_data)
        return response.data, response.errors, frames

    @timeit
    def _execute(self, new_request):
        return self._options.client.execute(new_request)

    @staticmethod
    @timeit
    def _extract(query: ParsedQuery, response: GraphQLResponse) -> Dict[str, JsonValue]:
        context = FrameExtractorContext(query)
        visit(response.data, FrameExtractor(context))
        found = context.frame_data
        return {f.name: found.get(f.name, EMPTY) for f in query.frames}

    @timeit
    def _normalize(self, frame_data: Dict[str, JsonValue]) -> Dict[str, Any]:
        separator = self._options.separator
        frames = {}
        for name, data in frame_data.items():
            data = itertools.chain(
                *[normalize(x, separator, fallback=name) for x in data]
            )
            frames[name] = self._create_data_frame(data)
        return frames

    @timeit
    def _create_data_frame(self, data):
        return self._options.library.create(data)


class FrameExtractorContext:
    def __init__(self, query: ParsedQuery):
        self._query = query
        self._frame_data = defaultdict(list)

    @property
    def frame_data(self) -> Dict[str, List[JsonValue]]:
        return self._frame_data

    def is_frame_at(self, path: JsonPath) -> bool:
        return self._query.is_frame_at(path)

    def has_nested_frame(self, path: JsonPath) -> bool:
        return self._query.has_nested_frame(path)

    def add_data(self, path: JsonPath, value: JsonValue):
        name = path[-1]
        self._frame_data[name].append(value)


class FrameExtractor(JsonVisitor):
    def __init__(self, context: FrameExtractorContext):
        self._ctx = context
        self._captured = {}

    def enter_array(self, path: JsonPath, value: JsonArray):
        return self._enter(path, value)

    def enter_object(self, path: JsonPath, value: JsonObject):
        return self._enter(path, value)

    def on_scalar(self, path: JsonPath, value: JsonScalar):
        self._enter(path, value)
        self.leave(path, value)

    def _enter(self, path: JsonPath, value: JsonValue):
        if path not in self._captured and self._ctx.is_frame_at(path):
            self._ctx.add_data(path, value)
            if not self._ctx.has_nested_frame(path):
                return STOP
            self._captured[path] = value

    def leave(self, path: JsonPath, value: JsonValue):
        captured = self._captured.get(path)
        if captured is value:
            del self._captured[path]

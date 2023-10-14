import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

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
from ._normalization import normalize
from ._parser import ParsedQuery, QueryParser
from ._decorators import timeit
from .client import GraphQLClient, GraphQLRequest, GraphQLResponse, UrllibGraphQLClient
from ._libraries import DataFrame, DataFrameLibrary, PandasDataFrameLibrary

ExecutorResult = Tuple[Dict, List, Dict[str, DataFrame]]
EMPTY = tuple()


@dataclass
class ExecutorOptions:
    separator: str
    client: Optional[GraphQLClient]
    column_names: Optional[str]
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
        extracted = self._extract(parsed_query, response)
        frames = self._normalize(extracted)
        frames = self._rename_columns(frames)
        return response.data, response.errors, frames

    @timeit
    def _execute(self, new_request):
        return self._options.client.execute(new_request)

    @staticmethod
    @timeit
    def _extract(query: ParsedQuery, response: GraphQLResponse) -> Dict[str, JsonValue]:
        if query.is_implicit_mode:
            return {"default": [response.data]}
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
    def _create_data_frame(self, data) -> DataFrame:
        return self._options.library.create(data)

    @timeit
    def _rename_columns(self, frames: Dict[str, DataFrame]) -> Dict[str, DataFrame]:
        mode = self._options.column_names
        modes = mode if isinstance(mode, dict) else defaultdict(lambda: mode)
        return {
            name: get_column_names(modes[name])(self._options, df)
            for name, df in frames.items()
        }


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


def get_column_names(mode):
    match mode:
        case None | "full" | "FULL":
            return rename_long
        case "short" | "SHORT":
            return rename_short
        case _:
            raise ValueError(f"{mode} is not a valid value")


def rename_long(_, df):
    return df


# TODO Replace with implementation that does not require splitting.
def rename_short(options: ExecutorOptions, df: DataFrame) -> pd.DataFrame:
    separator = options.separator
    original = df.columns
    renamed = {}
    for name in original:
        parts = name.split(separator)
        new_name = parts[-1]
        try:
            # Name conflict: qualify conflicts with their parents.
            existing_parts = renamed.pop(new_name)
            existing_name = ".".join(existing_parts[-2:])
            renamed[existing_name] = existing_parts
            new_name = ".".join(parts[-2:])
        except KeyError:
            pass
        renamed[new_name] = parts
    return options.library.rename(df, columns=dict(zip(original, renamed.keys())))

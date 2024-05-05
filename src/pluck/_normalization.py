from __future__ import annotations

import itertools
from dataclasses import dataclass, replace
from typing import Dict, Generator, Iterable, List, Optional, Set, Tuple

from ._json import STOP, JsonArray, JsonPath, JsonScalar, JsonValue, JsonVisitor, visit

NormalizeResult = List[Dict[str, JsonValue]]


def normalize(
    obj: JsonValue,
    separator: str = ".",
    fallback: Optional[str] = "?",
    selection_set: Optional[Set[JsonPath]] = None,
) -> NormalizeResult:
    assert separator
    options = JsonNormalizerOptions(separator, fallback, selection_set=selection_set)
    result = JsonNormalizer(options).normalize(obj)
    return result.rows


@dataclass(frozen=True)
class JsonNormalizerOptions:
    separator: str
    fallback: str
    initial_path: Optional[JsonPath] = None
    selection_set: Optional[Set[JsonPath]] = None

    def replace(self, **kwargs) -> JsonNormalizerOptions:
        return replace(self, **kwargs)


@dataclass(frozen=True)
class JsonNormalizerResult:
    rows: List[Dict[str, JsonValue]]
    paths: Set[JsonPath]


class JsonNormalizer:
    def __init__(self, options: JsonNormalizerOptions):
        self._options = options

    def normalize(self, obj: JsonValue) -> JsonNormalizerResult:
        ctx = JsonNormalizerContext(self._options)
        visitor = JsonNormalizerVisitor(ctx)
        visit(obj, visitor, self._options.initial_path)
        return JsonNormalizerResult(ctx.rows, ctx.paths)


class JsonNormalizerContext:
    def __init__(self, options: JsonNormalizerOptions):
        self._options = options
        self._rows: List[JsonValue] = [{}]
        self._paths: Set[JsonPath] = set()

    @property
    def options(self) -> JsonNormalizerOptions:
        return self._options

    @property
    def rows(self) -> List[JsonValue]:
        return self._rows

    @property
    def paths(self) -> Set[JsonPath]:
        return self._paths

    def set(self, path: JsonPath, value: JsonValue):
        for row in reversed(self._rows):
            name = self._generate_name(path)
            row[name] = value
        self._paths.add(path)

    def _generate_name(self, path: JsonPath) -> str:
        separator = self._options.separator
        fallback = self._options.fallback
        name = separator.join(path)
        return fallback if not name and fallback else name

    def normalize(self, path: JsonPath, other: JsonValue):
        normalizer = JsonNormalizer(self._options.replace(initial_path=path))
        result = normalizer.normalize(other)
        self._paths.update(result.paths)
        return result

    def cross_join(self, other: Generator):
        if other := _spy(other):
            self._rows = [x | y for x, y in itertools.product(self._rows, other)]


class JsonNormalizerVisitor(JsonVisitor):
    def __init__(self, ctx):
        self._ctx = ctx

    def on_scalar(self, path: JsonPath, value: JsonScalar):
        self._set(path, value)

    def on_null(self, path: JsonPath):
        self._set(path, None)

    def _set(self, path: JsonPath, value: JsonValue):
        selection_set = self._ctx.options.selection_set
        if not selection_set or path in selection_set:
            self._ctx.set(path, value)

    def enter_array(self, path: JsonPath, value: JsonArray):
        rows = (
            self._ctx.normalize(path, item).rows for item in value if item is not None
        )
        other = itertools.chain(*rows)
        self._ctx.cross_join(other)
        return STOP


def _spy(generator: Generator) -> Optional[Iterable]:
    try:
        head = next(generator)
        return itertools.chain((head,), generator)
    except StopIteration:
        return None

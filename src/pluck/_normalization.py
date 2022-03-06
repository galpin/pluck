import itertools
from dataclasses import dataclass
from typing import Dict, Generator, Iterable, List, Optional

from ._json import STOP, JsonArray, JsonPath, JsonScalar, JsonValue, JsonVisitor, visit

NormalizeResult = List[Dict[str, JsonValue]]


def normalize(
    obj: JsonValue,
    separator: str = ".",
    fallback: Optional[str] = "?",
) -> NormalizeResult:
    assert separator
    options = JsonNormalizerOptions(separator, fallback)
    return JsonNormalizer(options).normalize(obj)


@dataclass
class JsonNormalizerOptions:
    separator: str
    fallback: str


class JsonNormalizer:
    def __init__(
        self,
        options: JsonNormalizerOptions,
        initial_path: Optional[JsonPath] = None,
    ):
        self._options = options
        self._initial_path = initial_path

    def normalize(self, obj: JsonValue) -> NormalizeResult:
        ctx = JsonNormalizerContext(self._options)
        visitor = JsonNormalizerVisitor(ctx)
        visit(obj, visitor, self._initial_path)
        return ctx.rows


class JsonNormalizerContext:
    def __init__(self, options: JsonNormalizerOptions):
        self._options = options
        self._rows = [{}]

    @property
    def rows(self):
        return self._rows

    def set(self, path: JsonPath, value: JsonValue):
        for row in reversed(self._rows):
            name = self._generate_name(path)
            row[name] = value

    def _generate_name(self, path: JsonPath) -> str:
        separator = self._options.separator
        fallback = self._options.fallback
        name = separator.join(path)
        return fallback if not name and fallback else name

    def normalize(self, path: JsonPath, other: JsonValue):
        normalizer = JsonNormalizer(self._options, path)
        return normalizer.normalize(other)

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
        self._ctx.set(path, value)

    def enter_array(self, path: JsonPath, value: JsonArray):
        rows = (self._ctx.normalize(path, item) for item in value if item is not None)
        other = itertools.chain(*rows)
        self._ctx.cross_join(other)
        return STOP


def _spy(generator: Generator) -> Optional[Iterable]:
    try:
        head = next(generator)
        return itertools.chain((head,), generator)
    except StopIteration:
        return None

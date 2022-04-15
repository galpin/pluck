from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Dict, List, Optional, Union, TextIO

JsonObject = Dict[str, Any]
JsonArray = List[Any]
JsonScalar = Union[str, float, int, bool]
JsonValue = Union[JsonObject, JsonArray, JsonScalar, None]


class JsonPath(tuple):
    def add(self, value: str):
        return JsonPath(self + (value,))


class JsonVisitorAction(enum.Enum):
    STOP = 1


STOP = JsonVisitorAction.STOP


class JsonVisitor:
    def enter_object(
        self,
        path: JsonPath,
        value: JsonObject,
    ) -> Optional[JsonVisitorAction]:
        pass

    def enter_array(
        self,
        path: JsonPath,
        value: JsonArray,
    ) -> Optional[JsonVisitorAction]:
        pass

    def leave(self, path: JsonPath, value: JsonValue):
        pass

    def on_scalar(self, path: JsonPath, value: JsonScalar):
        pass

    def on_null(self, path: JsonPath):
        pass


def visit(root, visitor: JsonVisitor, initial_path: JsonPath = None):
    JsonWalker(visitor).walk(root, initial_path)


class JsonWalker:
    def __init__(self, visitor: JsonVisitor):
        self._visitor = visitor

    def walk(self, root: JsonValue, initial_path: JsonPath = None):
        stack = deque()
        visitor = self._visitor

        def put(path, obj, leave=False):
            stack.appendleft((path, obj, leave))

        path = initial_path or JsonPath()
        put(path, root)

        while stack:
            path, current, leave = stack.popleft()

            if leave:
                visitor.leave(path, current)
                continue

            if self._is_scalar_value(current):
                visitor.on_scalar(path, current)

            elif current is None:
                visitor.on_null(path)

            elif self._is_object_value(current):
                if visitor.enter_object(path, current) != STOP:
                    put(path, current, leave=True)
                    for key, value in reversed(current.items()):
                        put(path.add(key), value)

            elif self._is_array_value(current):
                if visitor.enter_array(path, current) != STOP:
                    put(path, current, leave=True)
                    for value in reversed(current):
                        put(path, value)

    @staticmethod
    def _is_scalar_value(obj) -> bool:
        return isinstance(obj, (str, float, int, bool))

    @staticmethod
    def _is_object_value(obj) -> bool:
        return isinstance(obj, dict)

    @staticmethod
    def _is_array_value(obj) -> bool:
        return isinstance(obj, list)


class JsonSerializer(ABC):
    @staticmethod
    def create_fastest() -> JsonSerializer:
        try:
            import orjson
            return OrJsonSerializer()
        except ImportError:
            import json
            return BuiltinJsonSerializer()

    @abstractmethod
    def serialize(self, obj: JsonValue, encoding: str) -> bytes:
        raise NotImplementedError()

    @abstractmethod
    def deserialize(self, fp: TextIO) -> JsonValue:
        raise NotImplementedError()


class BuiltinJsonSerializer(JsonSerializer):
    def serialize(self, obj: JsonValue, encoding: str) -> bytes:
        import json
        return json.dumps(obj).encode(encoding)

    def deserialize(self, fp: TextIO) -> JsonValue:
        import json
        return json.load(fp)


class OrJsonSerializer(JsonSerializer):
    def serialize(self, obj: JsonValue, encoding: str) -> bytes:
        import orjson
        return orjson.dumps(obj)

    def deserialize(self, fp: TextIO) -> JsonValue:
        import orjson
        return orjson.loads(fp.read())

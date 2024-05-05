from collections import deque
from dataclasses import dataclass
from typing import List, Set

import graphql
from graphql.language import REMOVE, DirectiveNode, FieldNode, Node, Visitor

from ._json import JsonPath


@dataclass(frozen=True)
class FrameInfo:
    path: JsonPath
    name: str
    selection_set: Set[JsonPath]


@dataclass(frozen=True)
class ParsedQuery:
    query: str
    frames: List[FrameInfo]
    selection_set: Set[JsonPath]

    @property
    def is_implicit_mode(self):
        return not self.frames

    def is_frame_at(self, path: JsonPath):
        return any(f.path == path for f in self.frames)

    def frame(self, name: str):
        return next(f for f in self.frames if f.name == name)

    def has_nested_frame(self, path: JsonPath):
        length = len(path)
        return any(
            len(f.path) > length and f.path[:length] == path for f in self.frames
        )


class FrameInfoBuilder:
    def __init__(self, path: JsonPath, name: str):
        self.path = path
        self.name = name
        self.selection_set = set()

    def add_field(self, path: JsonPath):
        assert path[: len(self.path)] == self.path
        self.selection_set.add(path[len(self.path) :])

    def add_self(self):
        self.selection_set.add(self.path[-1])

    def build(self) -> FrameInfo:
        return FrameInfo(self.path, self.name, self.selection_set)


class ParsedQueryBuilder:
    def __init__(self):
        self._query = None
        self._frames = []
        self._current_frames = deque()
        self._frame_names = set()
        self._selection_set = set()

    def is_current_frame(self, path: JsonPath):
        current = self._current_frames[0] if self._current_frames else None
        return current and current.path == path

    def add_path(self, path: JsonPath):
        self._selection_set.add(path)
        for frame in self._current_frames:
            frame.add_field(path)

    def begin_frame(self, path: JsonPath):
        name = path[-1]
        if name in self._frame_names:
            raise ValueError(f"Duplicate frame name: '{name}'!")
        self._add_frame(FrameInfoBuilder(path, name))

    def end_frame(self):
        self._current_frames.popleft()

    def set_query(self, query: str):
        self._query = query

    def build(self) -> ParsedQuery:
        return ParsedQuery(
            self._query,
            [f.build() for f in self._frames],
            self._selection_set,
        )

    def _add_frame(self, frame: FrameInfoBuilder):
        self._current_frames.appendleft(frame)
        self._frames.append(frame)


class QueryVisitor(Visitor):
    def __init__(self, builder: ParsedQueryBuilder):
        super().__init__()
        self._path = JsonPath()
        self._builder = builder

    def enter(self, node: Node, _, __, ___, ____):
        if isinstance(node, FieldNode):
            name = (node.alias or node.name).value
            self._path = self._path.add(name)
            if node.selection_set is None:
                self._builder.add_path(self._path)

        elif self._is_frame_directive_node(node):
            self._builder.begin_frame(self._path)
            return REMOVE

    def leave(self, node: Node, _, __, ___, ____):
        if isinstance(node, FieldNode):
            if self._builder.is_current_frame(self._path):
                self._builder.end_frame()
            self._path = self._path.pop_right()

    @staticmethod
    def _is_frame_directive_node(node: Node):
        return isinstance(node, DirectiveNode) and node.name.value == "frame"


class QueryParser:
    def __init__(self, query: str):
        self._query = query

    def parse(self) -> ParsedQuery:
        document = graphql.language.parse(self._query)
        builder = ParsedQueryBuilder()
        visitor = QueryVisitor(builder)
        new_document = graphql.visit(document, visitor)
        new_query = graphql.language.print_ast(new_document)
        builder.set_query(new_query)
        return builder.build()

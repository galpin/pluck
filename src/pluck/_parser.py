from dataclasses import dataclass
from typing import List

import graphql
from graphql.language import REMOVE, DirectiveNode, FieldNode, Node, Visitor

from ._json import JsonPath


@dataclass(frozen=True)
class FrameInfo:
    path: JsonPath
    name: str


@dataclass(frozen=True)
class ParsedQuery:
    query: str
    frames: List[FrameInfo]

    @property
    def is_implicit_mode(self):
        return not self.frames

    def is_frame_at(self, path: JsonPath):
        return any(f.path == path for f in self.frames)

    def has_nested_frame(self, path: JsonPath):
        length = len(path)
        return any(
            len(f.path) > length and f.path[:length] == path for f in self.frames
        )


class ParsedQueryBuilder:
    def __init__(self):
        self._query = None
        self._frames = {}

    def add_frame(self, path: JsonPath):
        info = FrameInfo(path, path[-1])
        if info.name in self._frames:
            raise ValueError(f"Duplicate frame name: '{info.name}'.")
        self._frames[info.name] = info

    def set_query(self, query: str):
        self._query = query

    def build(self) -> ParsedQuery:
        return ParsedQuery(self._query, list(self._frames.values()))


class QueryVisitor(Visitor):
    def __init__(self, builder: ParsedQueryBuilder):
        super().__init__()
        self._path = []
        self._builder = builder

    def enter(self, node: Node, _, __, ___, ____):
        if isinstance(node, FieldNode):
            name = (node.alias or node.name).value
            self._path.append(name)
        elif self._is_frame_directive_node(node):
            path = JsonPath(self._path)
            self._builder.add_frame(path)
            return REMOVE

    def leave(self, node: Node, _, __, ___, ____):
        if isinstance(node, FieldNode):
            self._path.pop()

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

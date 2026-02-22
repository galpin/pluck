"""Engine selection: uses Rust extension when available, falls back to Python."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._json import JsonValue
    from ._parser import ParsedQuery

try:
    from pluck._pluck_engine import extract_frames as _rust_extract_frames
    from pluck._pluck_engine import normalize as _rust_normalize
    from pluck._pluck_engine import normalize_columnar as _rust_normalize_columnar
    from pluck._pluck_engine import (
        normalize_columnar_batch as _rust_normalize_columnar_batch,
    )

    _USE_RUST = True
except ImportError:
    _USE_RUST = False


def has_rust_engine() -> bool:
    return _USE_RUST


def normalize(
    obj: JsonValue,
    separator: str = ".",
    fallback: str = "?",
    selection_set: Any = None,
) -> list[dict[str, JsonValue]]:
    if _USE_RUST:
        ss = [list(p) for p in selection_set] if selection_set else None
        return _rust_normalize(obj, separator, fallback, ss)
    from ._normalization import normalize as _py_normalize

    return _py_normalize(
        obj, separator, fallback=fallback, selection_set=selection_set
    )


def normalize_columnar(
    obj: JsonValue,
    separator: str = ".",
    fallback: str = "?",
    selection_set: Any = None,
) -> dict[str, list[Any]]:
    """Normalize and return columnar data {col: [values...]} for fast DataFrame creation."""
    if _USE_RUST:
        ss = [list(p) for p in selection_set] if selection_set else None
        return _rust_normalize_columnar(obj, separator, fallback, ss)
    # Fallback: use row-oriented normalize and pivot to columnar
    from ._normalization import normalize as _py_normalize

    rows = _py_normalize(
        obj, separator, fallback=fallback, selection_set=selection_set
    )
    if not rows:
        return {}
    columns: dict[str, list[Any]] = {k: [] for k in rows[0]}
    for row in rows:
        for k, v in row.items():
            columns[k].append(v)
    return columns


def normalize_columnar_batch(
    objects: list[Any],
    separator: str = ".",
    fallback: str = "?",
    selection_set: Any = None,
) -> dict[str, list[Any]]:
    """Batch normalize: normalizes all objects and returns a single merged columnar dict."""
    if _USE_RUST:
        ss = [list(p) for p in selection_set] if selection_set else None
        return _rust_normalize_columnar_batch(objects, separator, fallback, ss)
    # Fallback: use single-item normalize_columnar and merge in Python
    from ._normalization import normalize as _py_normalize

    merged: dict[str, list[Any]] = {}
    for obj in objects:
        rows = _py_normalize(
            obj, separator, fallback=fallback, selection_set=selection_set
        )
        for row in rows:
            for k, v in row.items():
                if k not in merged:
                    merged[k] = []
                merged[k].append(v)
    return merged


def extract_frames(
    data: dict[str, Any],
    query: ParsedQuery,
) -> dict[str, list[Any]]:
    if _USE_RUST:
        frame_paths = [list(f.path) for f in query.frames]
        nested_frame_paths = []
        for f in query.frames:
            for other in query.frames:
                if len(other.path) > len(f.path) and other.path[: len(f.path)] == f.path:
                    nested_frame_paths.append(list(f.path))
                    break
        return _rust_extract_frames(data, frame_paths, nested_frame_paths)

    from ._execution import FrameExtractor, FrameExtractorContext
    from ._json import visit

    context = FrameExtractorContext(query)
    visit(data, FrameExtractor(context))
    found = context.frame_data
    return {f.name: found.get(f.name, ()) for f in query.frames}

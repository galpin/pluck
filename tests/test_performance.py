"""Performance comparison between Python and Rust normalization engines.

Run with: uv run pytest tests/test_performance.py -m benchmark -s
"""

import time

import pandas as pd
import pytest

from pluck._normalization import normalize as py_normalize

# Generate synthetic nested JSON data for benchmarking.


def _make_item(i, sub_count, sub_sub_count):
    return {
        "id": i,
        "name": f"item_{i}",
        "active": i % 2 == 0,
        "children": [
            {
                "child_id": j,
                "label": f"child_{i}_{j}",
                "score": float(i * 100 + j),
                "tags": [
                    {"tag_id": k, "value": f"tag_{k}"}
                    for k in range(sub_sub_count)
                ],
            }
            for j in range(sub_count)
        ],
    }


def generate_large_response(items=100, sub_items=10, sub_sub_items=5):
    return {
        "data": [_make_item(i, sub_items, sub_sub_items) for i in range(items)],
    }


@pytest.mark.benchmark
def test_normalize_performance_python():
    """Benchmark the pure-Python normalize engine."""
    response = generate_large_response(items=50, sub_items=20, sub_sub_items=5)

    start = time.perf_counter()
    result = py_normalize(response, ".")
    elapsed = time.perf_counter() - start

    assert len(result) > 0
    print(f"\nPython normalize: {elapsed:.4f}s, {len(result)} rows")


@pytest.mark.benchmark
def test_normalize_performance_rust():
    """Benchmark the Rust normalize engine."""
    try:
        from pluck._pluck_engine import normalize as rs_normalize
    except ImportError:
        pytest.skip("Rust engine not available")

    response = generate_large_response(items=50, sub_items=20, sub_sub_items=5)

    start = time.perf_counter()
    result = rs_normalize(response, ".", "?", None)
    elapsed = time.perf_counter() - start

    assert len(result) > 0
    print(f"\nRust normalize: {elapsed:.4f}s, {len(result)} rows")


@pytest.mark.benchmark
def test_normalize_correctness_comparison():
    """Verify Rust and Python engines produce identical results."""
    try:
        from pluck._pluck_engine import normalize as rs_normalize
    except ImportError:
        pytest.skip("Rust engine not available")

    response = generate_large_response(items=10, sub_items=5, sub_sub_items=3)

    py_result = py_normalize(response, ".")
    rs_result = rs_normalize(response, ".", "?", None)

    assert len(py_result) == len(rs_result), (
        f"Row count mismatch: Python={len(py_result)}, Rust={len(rs_result)}"
    )
    for i, (py_row, rs_row) in enumerate(zip(py_result, rs_result)):
        assert py_row == rs_row, f"Row {i} differs:\nPython: {py_row}\nRust: {rs_row}"


@pytest.mark.benchmark
def test_normalize_columnar_correctness():
    """Verify columnar Rust output matches row-oriented output."""
    try:
        from pluck._pluck_engine import normalize as rs_normalize
        from pluck._pluck_engine import normalize_columnar as rs_normalize_col
    except ImportError:
        pytest.skip("Rust engine not available")

    response = generate_large_response(items=10, sub_items=5, sub_sub_items=3)

    rs_rows = rs_normalize(response, ".", "?", None)
    rs_cols = rs_normalize_col(response, ".", "?", None)

    df_rows = pd.DataFrame(rs_rows)
    df_cols = pd.DataFrame(rs_cols)

    pd.testing.assert_frame_equal(df_rows, df_cols)


@pytest.mark.benchmark
def test_normalize_columnar_batch_correctness():
    """Verify batch columnar output matches individual columnar calls merged."""
    try:
        from pluck._pluck_engine import normalize_columnar as rs_normalize_col
        from pluck._pluck_engine import (
            normalize_columnar_batch as rs_normalize_col_batch,
        )
    except ImportError:
        pytest.skip("Rust engine not available")

    response = generate_large_response(items=10, sub_items=5, sub_sub_items=3)
    data_items = response["data"]

    # Individual calls merged in Python
    merged = {}
    for item in data_items:
        cols = rs_normalize_col(item, ".", "?", None)
        for k, v in cols.items():
            if k not in merged:
                merged[k] = []
            merged[k].extend(v)
    df_individual = pd.DataFrame(merged)

    # Batch call
    batch_cols = rs_normalize_col_batch(data_items, ".", "?", None)
    df_batch = pd.DataFrame(batch_cols)

    pd.testing.assert_frame_equal(df_individual, df_batch)


@pytest.mark.benchmark
def test_normalize_arrow_batch_correctness():
    """Verify Arrow batch output matches columnar batch output."""
    try:
        from pluck._pluck_engine import (
            normalize_arrow_batch as rs_normalize_arrow,
        )
        from pluck._pluck_engine import (
            normalize_columnar_batch as rs_normalize_col_batch,
        )
    except ImportError:
        pytest.skip("Rust engine not available")

    response = generate_large_response(items=10, sub_items=5, sub_sub_items=3)
    data_items = response["data"]

    # Columnar batch → DataFrame
    batch_cols = rs_normalize_col_batch(data_items, ".", "?", None)
    df_columnar = pd.DataFrame(batch_cols)

    # Arrow batch → DataFrame
    arrow_batch = rs_normalize_arrow(data_items, ".", "?", None)
    df_arrow = arrow_batch.to_pandas()

    # Compare: columns should match
    assert list(df_columnar.columns) == list(df_arrow.columns)
    assert len(df_columnar) == len(df_arrow)
    for col in df_columnar.columns:
        for i in range(len(df_columnar)):
            py_val = df_columnar.iloc[i][col]
            arrow_val = df_arrow.iloc[i][col]
            if pd.isna(py_val) and pd.isna(arrow_val):
                continue
            assert py_val == arrow_val, (
                f"Row {i}, col {col}: columnar={py_val!r}, arrow={arrow_val!r}"
            )


@pytest.mark.benchmark
def test_normalize_performance_comparison():
    """Side-by-side timing comparison of Python vs Rust (row, columnar, batch, arrow)."""
    try:
        from pluck._pluck_engine import normalize as rs_normalize
        from pluck._pluck_engine import (
            normalize_arrow_batch as rs_normalize_arrow,
        )
        from pluck._pluck_engine import normalize_columnar as rs_normalize_col
        from pluck._pluck_engine import (
            normalize_columnar_batch as rs_normalize_col_batch,
        )
    except ImportError:
        pytest.skip("Rust engine not available")

    for items, sub_items, sub_sub_items in [(50, 20, 5), (200, 20, 5), (600, 20, 5)]:
        response = generate_large_response(
            items=items, sub_items=sub_items, sub_sub_items=sub_sub_items
        )
        data_items = response["data"]

        # Python: normalize + DataFrame
        start = time.perf_counter()
        py_result = py_normalize(response, ".")
        py_df = pd.DataFrame(py_result)
        py_time = time.perf_counter() - start

        # Rust row: normalize + DataFrame
        start = time.perf_counter()
        rs_result = rs_normalize(response, ".", "?", None)
        rs_df = pd.DataFrame(rs_result)
        rs_time = time.perf_counter() - start

        # Rust batch columnar: single call + DataFrame
        start = time.perf_counter()
        batch_cols = rs_normalize_col_batch(data_items, ".", "?", None)
        rs_batch_df = pd.DataFrame(batch_cols)
        rs_batch_time = time.perf_counter() - start

        # Rust Arrow: single call + zero-copy → DataFrame
        start = time.perf_counter()
        arrow_batch = rs_normalize_arrow(data_items, ".", "?", None)
        rs_arrow_df = arrow_batch.to_pandas()
        rs_arrow_time = time.perf_counter() - start

        assert len(py_df) == len(rs_df) == len(rs_batch_df) == len(rs_arrow_df)

        speedup_row = py_time / rs_time if rs_time > 0 else float("inf")
        speedup_batch = py_time / rs_batch_time if rs_batch_time > 0 else float("inf")
        speedup_arrow = py_time / rs_arrow_time if rs_arrow_time > 0 else float("inf")
        print(
            f"\nEnd-to-end (normalize + DataFrame, {len(py_df)} rows):"
            f"\n  Python:             {py_time:.4f}s"
            f"\n  Rust row:           {rs_time:.4f}s ({speedup_row:.1f}x)"
            f"\n  Rust batch columnar:{rs_batch_time:.4f}s ({speedup_batch:.1f}x)"
            f"\n  Rust Arrow:         {rs_arrow_time:.4f}s ({speedup_arrow:.1f}x)"
        )

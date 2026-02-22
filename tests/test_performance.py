"""Performance comparison between Python and Rust normalization engines.

Run with: uv run pytest tests/test_performance.py -m benchmark -s
"""

import time

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
    data = response

    start = time.perf_counter()
    result = py_normalize(data, ".")
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
    data = response

    start = time.perf_counter()
    result = rs_normalize(data, ".", "?", None)
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
    data = response

    py_result = py_normalize(data, ".")
    rs_result = rs_normalize(data, ".", "?", None)

    assert len(py_result) == len(rs_result), (
        f"Row count mismatch: Python={len(py_result)}, Rust={len(rs_result)}"
    )
    for i, (py_row, rs_row) in enumerate(zip(py_result, rs_result)):
        assert py_row == rs_row, f"Row {i} differs:\nPython: {py_row}\nRust: {rs_row}"


@pytest.mark.benchmark
def test_normalize_performance_comparison():
    """Side-by-side timing comparison of Python vs Rust."""
    try:
        from pluck._pluck_engine import normalize as rs_normalize
    except ImportError:
        pytest.skip("Rust engine not available")

    response = generate_large_response(items=50, sub_items=20, sub_sub_items=5)
    data = response

    # Python
    start = time.perf_counter()
    py_result = py_normalize(data, ".")
    py_time = time.perf_counter() - start

    # Rust
    start = time.perf_counter()
    rs_result = rs_normalize(data, ".", "?", None)
    rs_time = time.perf_counter() - start

    assert len(py_result) == len(rs_result)

    speedup = py_time / rs_time if rs_time > 0 else float("inf")
    print(
        f"\nPython: {py_time:.4f}s, Rust: {rs_time:.4f}s, "
        f"Speedup: {speedup:.1f}x ({len(py_result)} rows)"
    )

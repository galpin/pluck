# Plan: Rust Engine for Pluck

## Overview

Implement a compatible Rust engine for Pluck using **PyO3 + maturin** to accelerate
the most expensive operations while preserving the public Python API with zero breaking
changes. The Rust engine is an optional accelerator — when unavailable, the library
falls back transparently to the existing pure-Python implementation.

## Architecture

### What Gets Rust-ified (and Why)

After profiling the execution pipeline (`_execution.py:48-55`), the bottlenecks are:

| Operation | File | Complexity | Rust Benefit |
|---|---|---|---|
| **JSON normalization** | `_normalization.py` | O(response × ∏ array_lengths) | **High** — cross-join dict merging is allocation-heavy in Python |
| **JSON tree walking** | `_json.py` (JsonWalker) | O(response_size) | **Medium** — eliminates per-node Python function call overhead |
| **Frame extraction** | `_execution.py` (FrameExtractor) | O(response_size) | **Medium** — visitor over JSON response, currently pure Python |

**Not Rust-ified** (already fast or depend on Python libraries):
- Query parsing — depends on `graphql-core` (Python library), queries are small
- HTTP execution — I/O-bound, uses urllib/custom client
- DataFrame creation — delegates to Pandas (compiled C/NumPy)
- Column renaming — O(num_columns), negligible

### Project Structure

```
pluck/
├── Cargo.toml                          # NEW — Rust crate configuration
├── pyproject.toml                      # MODIFIED — maturin build backend (replaces uv_build)
├── .pre-commit-config.yaml             # EXISTING — ruff + ty hooks (unchanged)
├── rust/                               # NEW — Rust source directory
│   ├── lib.rs                          #   PyO3 module entry point
│   ├── normalize.rs                    #   Core normalization algorithm
│   ├── walker.rs                       #   JSON tree walking
│   └── extract.rs                      #   Frame extraction
├── src/pluck/                          # EXISTING — Python package
│   ├── __init__.py                     #   Unchanged (public API preserved)
│   ├── _pluck.py                       #   Unchanged
│   ├── _execution.py                   #   MODIFIED — delegates to engine
│   ├── _normalization.py               #   Unchanged (Python fallback)
│   ├── _json.py                        #   Unchanged (Python fallback)
│   ├── _engine.py                      #   NEW — engine selection + fallback
│   ├── _parser.py                      #   Unchanged
│   ├── _libraries.py                   #   Unchanged
│   ├── _decorators.py                  #   Unchanged
│   └── client.py                       #   Unchanged
├── tests/
│   ├── test_normalize.py               #   Unchanged (passes with both engines)
│   ├── test_pluck.py                   #   Unchanged
│   ├── test_scenarios.py               #   Unchanged
│   ├── test_json_path.py               #   Unchanged
│   ├── test_urllib_client.py           #   Unchanged
│   └── test_performance.py             #   NEW — benchmark Rust vs Python
```

### Engine Selection and Fallback

A new `_engine.py` module handles engine selection:

```python
# src/pluck/_engine.py
try:
    from pluck._pluck_engine import normalize as rust_normalize
    from pluck._pluck_engine import extract_frames as rust_extract_frames
    _USE_RUST = True
except ImportError:
    _USE_RUST = False
```

The `_execution.py` module is modified to call `_engine.normalize()` and
`_engine.extract_frames()` instead of directly calling the Python implementations.
When Rust is available, these delegate to the compiled extension. When Rust is
unavailable, they delegate to the existing Python code in `_normalization.py` and
the `FrameExtractor` in `_execution.py`.

## Implementation Steps

### Step 1: Rust Crate Setup

**Files created:**

1. `Cargo.toml` — Root crate configuration:
   - `name = "pluck-engine"`
   - `crate-type = ["cdylib"]` (for PyO3 dynamic library)
   - `lib.path = "rust/lib.rs"`
   - Dependencies: `pyo3` (with `extension-module` feature)

2. `rust/lib.rs` — PyO3 module entry point:
   - Declares `#[pymodule] fn _pluck_engine`
   - Registers `normalize` and `extract_frames` functions

### Step 2: Implement `normalize()` in Rust

**File: `rust/normalize.rs`**

Port the algorithm from `_normalization.py` + `_json.py` (JsonWalker):

```
normalize(obj, separator, fallback, selection_set) -> List[Dict[str, PyObject]]
```

The Rust implementation:
1. Accepts Python objects directly via PyO3 (`Bound<'_, PyAny>`)
2. Walks the Python dict/list/scalar tree using PyO3's API (avoids serialization)
3. Builds `Vec<HashMap<String, PyObject>>` as rows
4. Performs cross-joins using `Vec::with_capacity` + direct iteration (no Python
   `itertools.product` overhead)
5. Filters by selection_set (converted from Python set of tuples to Rust `HashSet<Vec<String>>`)
6. Returns results as Python `list[dict[str, Any]]`

Key optimizations vs Python:
- **Cross-join**: Avoids Python dict merging overhead (`x | y`); uses pre-allocated
  Vecs and direct HashMap cloning in Rust
- **Path generation**: String joining with separator done in Rust (no Python string
  allocation per node)
- **Stack-based walking**: No Python function call overhead per visitor method
- **Memory**: Rust's allocator is more efficient than Python's for many small dicts

**File: `rust/walker.rs`**

Shared JSON tree walking logic used by both normalize and extract:
- Stack-based iteration (mirrors `JsonWalker` in `_json.py`)
- Works directly with `PyDict`, `PyList`, `PyString`, etc. via PyO3
- Type dispatch using PyO3's `downcast` methods

### Step 3: Implement `extract_frames()` in Rust

**File: `rust/extract.rs`**

Port the `FrameExtractor` visitor from `_execution.py`:

```
extract_frames(data, frame_paths, has_nested_frames_fn) -> Dict[str, List[PyObject]]
```

The Rust implementation:
1. Accepts the JSON response data as a Python dict
2. Accepts frame paths as a list of tuples (converted to `Vec<Vec<String>>`)
3. Walks the tree, collecting data at frame paths
4. Returns `dict[str, list[Any]]` mapping frame names to extracted values

### Step 4: Python Integration (`_engine.py`)

**File: `src/pluck/_engine.py`** (new)

```python
try:
    from pluck._pluck_engine import normalize as _rust_normalize
    from pluck._pluck_engine import extract_frames as _rust_extract_frames
    _USE_RUST = True
except ImportError:
    _USE_RUST = False

def normalize(obj, separator=".", fallback="?", selection_set=None):
    if _USE_RUST:
        ss = [list(p) for p in selection_set] if selection_set else None
        return _rust_normalize(obj, separator, fallback, ss)
    from ._normalization import normalize as _py_normalize
    return _py_normalize(obj, separator, fallback, selection_set)

def extract_frames(data, query):
    if _USE_RUST:
        frame_paths = [list(f.path) for f in query.frames]
        nested_frame_set = ... # derive from query
        return _rust_extract_frames(data, frame_paths, nested_frame_set)
    # Fall back to existing Python FrameExtractor
    from ._execution import FrameExtractorContext, FrameExtractor
    from ._json import visit
    context = FrameExtractorContext(query)
    visit(data, FrameExtractor(context))
    found = context.frame_data
    return {f.name: found.get(f.name, ()) for f in query.frames}
```

**File: `src/pluck/_execution.py`** (modified)

Modify `Executor._extract()` and `Executor._normalize()` to delegate to `_engine`:

```python
from ._engine import normalize as engine_normalize, extract_frames as engine_extract

class Executor:
    @staticmethod
    @timeit
    def _extract(query, response):
        if query.is_implicit_mode:
            return {"default": [response.data]}
        return engine_extract(response.data, query)

    @timeit
    def _normalize(self, frame_data, query):
        separator = self._options.separator
        frames = {}
        for name, data in frame_data.items():
            selection_set = (
                query.selection_set if query.is_implicit_mode
                else query.frame(name).selection_set
            )
            data = itertools.chain(
                *[engine_normalize(x, separator, fallback=name,
                                   selection_set=selection_set) for x in data]
            )
            frames[name] = self._create_data_frame(data)
        return frames
```

### Step 5: Build System Updates

**File: `pyproject.toml`** (modified)

The project currently uses **uv** for dependency management and **uv_build** as the
build backend. We replace only the build backend with maturin (uv continues to manage
dependencies and run commands):

```toml
[build-system]
requires = ["maturin>=1.0,<2.0"]
build-backend = "maturin"

[tool.maturin]
python-source = "src"
module-name = "pluck._pluck_engine"
features = ["pyo3/extension-module"]
```

The `[tool.uv.build-backend]` section is removed (maturin handles this). All other
sections remain unchanged: `[project]`, `[dependency-groups]`, `[tool.ruff.lint]`,
`[tool.ty.rules]`.

Development workflow:
- `uv sync` — install Python dependencies
- `maturin develop` — compile Rust extension into the current venv
- `uv run pytest` — run tests as before
- `maturin build --release` — build optimized wheels for distribution

### Step 6: CI Updates

**File: `.github/workflows/CI.yml`** (modified)

The CI currently uses uv (via `astral-sh/setup-uv@v5`). Add Rust toolchain and
maturin steps before the test step:

```yaml
steps:
- uses: actions/checkout@v4
- name: Install uv
  uses: astral-sh/setup-uv@v5
- name: Setup Python
  run: uv python install ${{ matrix.python-version }}
- name: Setup Rust
  uses: dtolnay/rust-toolchain@stable
- name: Install dependencies
  run: uv sync
- name: Build Rust extension
  run: uv run maturin develop --release
- name: Test
  run: uv run pytest
  working-directory: tests
  env:
    PYTHONPATH: ../src
- name: Build
  if: matrix.os == 'ubuntu-latest' && matrix.python-version == '3.10'
  run: uv run maturin build --release
- name: Upload
  uses: actions/upload-artifact@v3
  if: matrix.os == 'ubuntu-latest' && matrix.python-version == '3.10'
  with:
    name: packages
    path: target/wheels/*
```

### Step 7: Pre-commit Compatibility

The existing `.pre-commit-config.yaml` runs:
1. `ruff-check` — linting (with `--fix`)
2. `ruff-format` — formatting
3. `ty check src/` — type checking

New Python files (`_engine.py`) must pass all three. The `ty` checker already has
`unresolved-import = "warn"` configured in `pyproject.toml`, which handles the
optional `_pluck_engine` import gracefully (it's a compiled extension that may not
exist at type-check time).

No changes needed to `.pre-commit-config.yaml`.

### Step 8: Performance Test

**File: `tests/test_performance.py`** (new)

A benchmark test that:
1. Generates large synthetic JSON responses with multiple nested arrays
   (e.g., 100 items × 50 sub-items × 20 sub-sub-items = 100k rows)
2. Runs `normalize()` using the Python engine
3. Runs `normalize()` using the Rust engine
4. Asserts both produce identical results
5. Reports timing comparison using `time.perf_counter`
6. Marked with `@pytest.mark.benchmark` so it doesn't run in normal CI
   (run explicitly with `pytest -m benchmark`)

```python
@pytest.mark.benchmark
def test_normalize_performance_comparison():
    data = generate_large_response(items=100, sub_items=50, depth=3)

    # Force Python engine
    from pluck._normalization import normalize as py_normalize
    start = time.perf_counter()
    py_result = py_normalize(data)
    py_time = time.perf_counter() - start

    # Force Rust engine
    from pluck._pluck_engine import normalize as rs_normalize
    start = time.perf_counter()
    rs_result = rs_normalize(data, ".", "?", None)
    rs_time = time.perf_counter() - start

    # Results must be identical
    assert py_result == rs_result

    # Report
    print(f"Python: {py_time:.3f}s, Rust: {rs_time:.3f}s, "
          f"Speedup: {py_time/rs_time:.1f}x")
```

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Rust extension fails to compile on some platforms | Graceful fallback to pure Python — no breakage |
| PyO3 overhead for small responses negates gains | Benchmark with realistic payloads; Rust engine may add a min-size threshold |
| `httpretty` test failures in CI | These are environment-specific (sandboxed networking); tests pass in standard CI |
| Cross-join produces huge intermediate results | Same as Python — this is inherent to the algorithm, not the engine |
| maturin replaces uv_build | uv still manages deps; only the wheel-building backend changes |
| `ty` can't resolve `_pluck_engine` import | Already handled: `unresolved-import = "warn"` in `[tool.ty.rules]` |

## Files Changed Summary

| File | Action | Description |
|---|---|---|
| `Cargo.toml` | **Create** | Rust crate configuration |
| `rust/lib.rs` | **Create** | PyO3 module entry point |
| `rust/normalize.rs` | **Create** | Normalization algorithm in Rust |
| `rust/walker.rs` | **Create** | JSON tree walking in Rust |
| `rust/extract.rs` | **Create** | Frame extraction in Rust |
| `src/pluck/_engine.py` | **Create** | Engine selection with fallback |
| `src/pluck/_execution.py` | **Modify** | Delegate to engine module |
| `pyproject.toml` | **Modify** | Replace uv_build with maturin build backend |
| `.github/workflows/CI.yml` | **Modify** | Add Rust toolchain + maturin steps |
| `tests/test_performance.py` | **Create** | Performance comparison benchmark |

**No changes to:**
- `src/pluck/__init__.py` — public API unchanged
- `src/pluck/_pluck.py` — Response class and execute/create unchanged
- `src/pluck/_normalization.py` — kept as Python fallback
- `src/pluck/_json.py` — kept as Python fallback
- `src/pluck/_parser.py` — query parsing stays in Python
- `src/pluck/client.py` — HTTP client stays in Python
- `src/pluck/_libraries.py` — DataFrame abstraction stays in Python
- `.pre-commit-config.yaml` — existing hooks work as-is
- All existing test files — all existing tests continue to pass

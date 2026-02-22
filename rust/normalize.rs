use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString};
use std::collections::{HashMap, HashSet};
use std::rc::Rc;

/// A native Rust representation of a JSON value.
/// Converted from Python objects once at the boundary to avoid per-node GIL overhead.
#[derive(Clone, Debug)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(Rc<str>),
    List(Vec<Value>),
    Object(Vec<(Rc<str>, Value)>),
}

/// Convert a Python object tree into a native Rust Value tree.
/// This is done once at the boundary — all subsequent work is pure Rust.
pub fn py_to_value(obj: &Bound<'_, PyAny>) -> Value {
    if obj.is_none() {
        Value::Null
    } else if let Ok(b) = obj.downcast::<PyBool>() {
        Value::Bool(b.is_true())
    } else if let Ok(i) = obj.downcast::<PyInt>() {
        Value::Int(i.extract().unwrap_or(0))
    } else if let Ok(f) = obj.downcast::<PyFloat>() {
        Value::Float(f.extract().unwrap_or(0.0))
    } else if let Ok(s) = obj.downcast::<PyString>() {
        let st: String = s.extract().unwrap_or_default();
        Value::Str(Rc::from(st.as_str()))
    } else if let Ok(dict) = obj.downcast::<PyDict>() {
        let entries: Vec<(Rc<str>, Value)> = dict
            .iter()
            .map(|(k, v)| {
                let key: String = k.extract().unwrap_or_default();
                (Rc::from(key.as_str()), py_to_value(&v))
            })
            .collect();
        Value::Object(entries)
    } else if let Ok(list) = obj.downcast::<PyList>() {
        let items: Vec<Value> = list.iter().map(|v| py_to_value(&v)).collect();
        Value::List(items)
    } else {
        Value::Null
    }
}

/// Convert a native Rust Value back to a Python object.
fn value_to_py(py: Python<'_>, val: &Value) -> PyObject {
    match val {
        Value::Null => py.None(),
        Value::Bool(b) => (*b).into_pyobject(py).unwrap().to_owned().into_any().unbind(),
        Value::Int(i) => (*i).into_pyobject(py).unwrap().into_any().unbind(),
        Value::Float(f) => (*f).into_pyobject(py).unwrap().into_any().unbind(),
        Value::Str(s) => s.as_ref().into_pyobject(py).unwrap().to_owned().into_any().unbind(),
        Value::List(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(value_to_py(py, item)).unwrap();
            }
            list.unbind().into()
        }
        Value::Object(entries) => {
            let dict = PyDict::new(py);
            for (k, v) in entries {
                dict.set_item(k.as_ref(), value_to_py(py, v)).unwrap();
            }
            dict.unbind().into()
        }
    }
}

/// Row = list of (column_name, value) pairs. Rc<str> avoids cloning strings during cross-join.
pub type Row = Vec<(Rc<str>, Value)>;

/// Normalize a JSON-like Python object into a list of flat dicts (records).
/// Kept for compatibility — prefer `normalize_columnar_batch` for better performance.
#[pyfunction]
#[pyo3(signature = (obj, separator=".", fallback="?", selection_set=None))]
pub fn normalize(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
    separator: &str,
    fallback: &str,
    selection_set: Option<Vec<Vec<String>>>,
) -> PyResult<Py<PyList>> {
    let (opts, value) = prepare(obj, separator, fallback, selection_set);
    let mut path_stack: Vec<Rc<str>> = Vec::new();
    let rows = normalize_value(&value, &opts, &mut path_stack, &mut HashMap::new());
    rows_to_py(py, &rows)
}

/// Normalize and return columnar data: {col_name: [values...]}.
/// This is much faster for Pandas consumption since it avoids creating N Python dicts.
#[pyfunction]
#[pyo3(signature = (obj, separator=".", fallback="?", selection_set=None))]
pub fn normalize_columnar(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
    separator: &str,
    fallback: &str,
    selection_set: Option<Vec<Vec<String>>>,
) -> PyResult<Py<PyDict>> {
    let (opts, value) = prepare(obj, separator, fallback, selection_set);
    let mut path_stack: Vec<Rc<str>> = Vec::new();
    let rows = normalize_value(&value, &opts, &mut path_stack, &mut HashMap::new());
    rows_to_columnar_py(py, &rows)
}

/// Batch normalize: accepts a list of Python objects, normalizes all of them,
/// and returns a single merged columnar dict. Eliminates per-item Python↔Rust
/// round-trips and the Python-side merge loop.
///
/// Strategy: for each item, normalize to rows (cache-friendly small working set),
/// then immediately append values as PyObjects to Python lists. This avoids any
/// intermediate Rust columnar accumulator and its associated cloning.
#[pyfunction]
#[pyo3(signature = (objects, separator=".", fallback="?", selection_set=None))]
pub fn normalize_columnar_batch(
    py: Python<'_>,
    objects: &Bound<'_, PyList>,
    separator: &str,
    fallback: &str,
    selection_set: Option<Vec<Vec<String>>>,
) -> PyResult<Py<PyDict>> {
    let ss: Option<HashSet<Vec<Rc<str>>>> = selection_set.map(|v| {
        v.into_iter()
            .map(|p| p.into_iter().map(|s| Rc::from(s.as_str())).collect())
            .collect()
    });
    let opts = NormalizeOpts {
        separator: Rc::from(separator),
        fallback: Rc::from(fallback),
        selection_set: ss,
    };

    let mut path_stack: Vec<Rc<str>> = Vec::new();
    let mut name_cache: HashMap<Vec<Rc<str>>, Rc<str>> = HashMap::new();

    // Column layout: discovered lazily from first item
    let mut col_order: Vec<Rc<str>> = Vec::new();
    // Accumulate PyObjects in Rust Vecs, then build Python lists in one shot at end
    let mut col_data: Vec<Vec<PyObject>> = Vec::new();

    for obj in objects.iter() {
        let value = py_to_value(&obj);
        let rows = normalize_value(&value, &opts, &mut path_stack, &mut name_cache);

        if rows.is_empty() {
            continue;
        }

        // Discover column layout from first non-empty result
        if col_order.is_empty() {
            for (k, _) in &rows[0] {
                col_order.push(k.clone());
                col_data.push(Vec::new());
            }
        }

        // Use direct indexed access — columns are always in consistent order
        for row in &rows {
            for (col_idx, (_k, v)) in row.iter().enumerate() {
                col_data[col_idx].push(value_to_py(py, v));
            }
        }
    }

    // Build result dict: create PyLists from slices (fast bulk creation)
    let result = PyDict::new(py);
    for (i, col_name) in col_order.iter().enumerate() {
        let py_list = PyList::new(py, &col_data[i])?;
        result.set_item(col_name.as_ref(), py_list)?;
    }

    Ok(result.unbind())
}

fn prepare(
    obj: &Bound<'_, PyAny>,
    separator: &str,
    fallback: &str,
    selection_set: Option<Vec<Vec<String>>>,
) -> (NormalizeOpts, Value) {
    let value = py_to_value(obj);

    let ss: Option<HashSet<Vec<Rc<str>>>> = selection_set.map(|v| {
        v.into_iter()
            .map(|p| p.into_iter().map(|s| Rc::from(s.as_str())).collect())
            .collect()
    });

    let opts = NormalizeOpts {
        separator: Rc::from(separator),
        fallback: Rc::from(fallback),
        selection_set: ss,
    };

    (opts, value)
}

pub struct NormalizeOpts {
    pub separator: Rc<str>,
    pub fallback: Rc<str>,
    pub selection_set: Option<HashSet<Vec<Rc<str>>>>,
}

/// Pure Rust normalization. No Python interaction.
/// Uses a mutable path_stack (push/pop) instead of allocating new Vecs per level.
/// Uses a name_cache to avoid recomputing generate_name for the same path.
pub fn normalize_value(
    val: &Value,
    opts: &NormalizeOpts,
    path_stack: &mut Vec<Rc<str>>,
    name_cache: &mut HashMap<Vec<Rc<str>>, Rc<str>>,
) -> Vec<Row> {
    match val {
        Value::Object(entries) => {
            let mut rows: Vec<Row> = vec![vec![]];
            for (key, child) in entries {
                path_stack.push(key.clone());
                normalize_into(&mut rows, child, opts, path_stack, name_cache);
                path_stack.pop();
            }
            rows
        }
        _ => {
            let mut rows: Vec<Row> = vec![vec![]];
            normalize_into(&mut rows, val, opts, path_stack, name_cache);
            rows
        }
    }
}

/// Normalize a value and merge results into existing rows.
fn normalize_into(
    rows: &mut Vec<Row>,
    val: &Value,
    opts: &NormalizeOpts,
    path_stack: &mut Vec<Rc<str>>,
    name_cache: &mut HashMap<Vec<Rc<str>>, Rc<str>>,
) {
    match val {
        Value::Object(entries) => {
            for (key, child) in entries {
                path_stack.push(key.clone());
                normalize_into(rows, child, opts, path_stack, name_cache);
                path_stack.pop();
            }
        }
        Value::List(items) => {
            let mut all_sub_rows: Vec<Row> = Vec::new();
            for item in items {
                if matches!(item, Value::Null) {
                    continue;
                }
                let sub = normalize_value(item, opts, path_stack, name_cache);
                all_sub_rows.extend(sub);
            }
            if !all_sub_rows.is_empty() {
                cross_join(rows, &all_sub_rows);
            }
        }
        Value::Null => {
            if should_include(path_stack, &opts.selection_set) {
                let name = cached_name(path_stack, &opts.separator, &opts.fallback, name_cache);
                for row in rows.iter_mut() {
                    row.push((name.clone(), Value::Null));
                }
            }
        }
        scalar => {
            if should_include(path_stack, &opts.selection_set) {
                let name = cached_name(path_stack, &opts.separator, &opts.fallback, name_cache);
                for row in rows.iter_mut() {
                    row.push((name.clone(), scalar.clone()));
                }
            }
        }
    }
}

#[inline]
fn should_include(path: &[Rc<str>], selection_set: &Option<HashSet<Vec<Rc<str>>>>) -> bool {
    match selection_set {
        None => true,
        Some(ss) => ss.contains(path),
    }
}

/// Look up or compute the column name for the given path.
#[inline]
fn cached_name(
    path: &[Rc<str>],
    separator: &str,
    fallback: &Rc<str>,
    cache: &mut HashMap<Vec<Rc<str>>, Rc<str>>,
) -> Rc<str> {
    if let Some(name) = cache.get(path) {
        return name.clone();
    }
    let name = generate_name(path, separator, fallback);
    cache.insert(path.to_vec(), name.clone());
    name
}

fn generate_name(path: &[Rc<str>], separator: &str, fallback: &Rc<str>) -> Rc<str> {
    if path.is_empty() {
        return fallback.clone();
    }
    let mut result = String::with_capacity(path.iter().map(|s| s.len() + 1).sum());
    for (i, part) in path.iter().enumerate() {
        if i > 0 {
            result.push_str(separator);
        }
        result.push_str(part);
    }
    if result.is_empty() {
        fallback.clone()
    } else {
        Rc::from(result.as_str())
    }
}

/// Cross-join: existing_rows × other_rows. Pure Rust, no GIL.
fn cross_join(rows: &mut Vec<Row>, other: &[Row]) {
    let mut result = Vec::with_capacity(rows.len() * other.len());
    for existing in rows.iter() {
        for other_row in other {
            let mut merged = Vec::with_capacity(existing.len() + other_row.len());
            merged.extend(existing.iter().map(|(k, v)| (k.clone(), v.clone())));
            merged.extend(other_row.iter().map(|(k, v)| (k.clone(), v.clone())));
            result.push(merged);
        }
    }
    *rows = result;
}

/// Convert Vec<Row> into a Python list of dicts. Done once at the boundary.
fn rows_to_py(py: Python<'_>, rows: &[Row]) -> PyResult<Py<PyList>> {
    let list = PyList::empty(py);
    for row in rows {
        let dict = PyDict::new(py);
        for (key, value) in row {
            dict.set_item(key.as_ref(), value_to_py(py, value))?;
        }
        list.append(dict)?;
    }
    Ok(list.unbind())
}

/// Convert Vec<Row> into columnar format: {col_name: [val1, val2, ...]}.
/// This creates only 1 dict + N_cols lists instead of N_rows dicts.
fn rows_to_columnar_py(py: Python<'_>, rows: &[Row]) -> PyResult<Py<PyDict>> {
    if rows.is_empty() {
        return Ok(PyDict::new(py).unbind());
    }

    // Discover column order from the first row (all rows have same columns in same order)
    let columns: Vec<Rc<str>> = rows[0].iter().map(|(k, _)| k.clone()).collect();
    let num_cols = columns.len();
    let num_rows = rows.len();

    // Build column arrays
    let mut col_values: Vec<Vec<PyObject>> = Vec::with_capacity(num_cols);
    for _ in 0..num_cols {
        col_values.push(Vec::with_capacity(num_rows));
    }

    for row in rows {
        for (col_idx, (_key, value)) in row.iter().enumerate() {
            col_values[col_idx].push(value_to_py(py, value));
        }
    }

    // Build result dict: {col_name: [values...]}
    let result = PyDict::new(py);
    for (col_idx, col_name) in columns.iter().enumerate() {
        let py_list = PyList::new(py, &col_values[col_idx])?;
        result.set_item(col_name.as_ref(), py_list)?;
    }

    Ok(result.unbind())
}

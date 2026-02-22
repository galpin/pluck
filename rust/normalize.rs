use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString};
use std::collections::HashSet;
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
        // PyBool must be checked before PyInt (bool is a subclass of int in Python)
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
type Row = Vec<(Rc<str>, Value)>;

/// Normalize a JSON-like Python object into a list of flat dicts (records).
/// Kept for compatibility — prefer `normalize_columnar` for better performance.
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
    let rows = normalize_value(&value, &opts, &[]);
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
    let rows = normalize_value(&value, &opts, &[]);
    rows_to_columnar_py(py, &rows)
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

struct NormalizeOpts {
    separator: Rc<str>,
    fallback: Rc<str>,
    selection_set: Option<HashSet<Vec<Rc<str>>>>,
}

/// Pure Rust normalization. No Python interaction.
fn normalize_value(val: &Value, opts: &NormalizeOpts, path: &[Rc<str>]) -> Vec<Row> {
    match val {
        Value::Object(entries) => {
            let mut rows: Vec<Row> = vec![vec![]];
            for (key, child) in entries {
                let mut child_path = path.to_vec();
                child_path.push(key.clone());
                normalize_into(&mut rows, child, opts, &child_path);
            }
            rows
        }
        _ => {
            let mut rows: Vec<Row> = vec![vec![]];
            normalize_into(&mut rows, val, opts, path);
            rows
        }
    }
}

/// Normalize a value and merge results into existing rows.
fn normalize_into(rows: &mut Vec<Row>, val: &Value, opts: &NormalizeOpts, path: &[Rc<str>]) {
    match val {
        Value::Object(entries) => {
            for (key, child) in entries {
                let mut child_path = path.to_vec();
                child_path.push(key.clone());
                normalize_into(rows, child, opts, &child_path);
            }
        }
        Value::List(items) => {
            let mut all_sub_rows: Vec<Row> = Vec::new();
            for item in items {
                if matches!(item, Value::Null) {
                    continue;
                }
                let sub = normalize_value(item, opts, path);
                all_sub_rows.extend(sub);
            }
            if !all_sub_rows.is_empty() {
                cross_join(rows, &all_sub_rows);
            }
        }
        Value::Null => {
            if should_include(path, &opts.selection_set) {
                let name = generate_name(path, &opts.separator, &opts.fallback);
                for row in rows.iter_mut() {
                    row.push((name.clone(), Value::Null));
                }
            }
        }
        scalar => {
            if should_include(path, &opts.selection_set) {
                let name = generate_name(path, &opts.separator, &opts.fallback);
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

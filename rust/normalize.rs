use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashSet;

use crate::walker::{self, JsonPath, JsonVisitor, VisitorAction};

/// Row is a list of (column_name, value) pairs.
/// We use Vec instead of HashMap to preserve insertion order and avoid hashing overhead.
type Row = Vec<(String, PyObject)>;

/// Normalize a JSON-like Python object into a list of flat dicts (records).
///
/// This is the Rust equivalent of `_normalization.normalize()`.
#[pyfunction]
#[pyo3(signature = (obj, separator=".", fallback="?", selection_set=None))]
pub fn normalize(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
    separator: &str,
    fallback: &str,
    selection_set: Option<Vec<Vec<String>>>,
) -> PyResult<Py<PyList>> {
    let ss: Option<HashSet<Vec<String>>> = selection_set.map(|v| v.into_iter().collect());

    let opts = NormalizeOptions {
        separator: separator.to_string(),
        fallback: fallback.to_string(),
        selection_set: ss,
    };

    let rows = normalize_value(py, obj, &opts, None)?;
    rows_to_py(py, &rows)
}

struct NormalizeOptions {
    separator: String,
    fallback: String,
    selection_set: Option<HashSet<Vec<String>>>,
}

/// Core normalization: walk a Python object tree, producing flat rows.
fn normalize_value(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
    opts: &NormalizeOptions,
    initial_path: Option<JsonPath>,
) -> PyResult<Vec<Row>> {
    let mut visitor = NormalizerVisitor {
        opts,
        rows: vec![vec![]],
        py,
    };
    walker::walk(py, obj, &mut visitor, initial_path);
    Ok(visitor.rows)
}

struct NormalizerVisitor<'a> {
    opts: &'a NormalizeOptions,
    rows: Vec<Row>,
    py: Python<'a>,
}

impl<'a> NormalizerVisitor<'a> {
    fn set_value(&mut self, path: &JsonPath, value: PyObject) {
        if let Some(ref ss) = self.opts.selection_set {
            if !ss.contains(path) {
                return;
            }
        }
        let name = self.generate_name(path);
        for row in self.rows.iter_mut() {
            row.push((name.clone(), value.clone_ref(self.py)));
        }
    }

    fn generate_name(&self, path: &JsonPath) -> String {
        if path.is_empty() {
            return self.opts.fallback.clone();
        }
        let name = path.join(&self.opts.separator);
        if name.is_empty() {
            self.opts.fallback.clone()
        } else {
            name
        }
    }

    fn cross_join(&mut self, other_rows: Vec<Row>) {
        if other_rows.is_empty() {
            return;
        }
        let mut result = Vec::with_capacity(self.rows.len() * other_rows.len());
        for existing in &self.rows {
            for other in &other_rows {
                let mut merged = Vec::with_capacity(existing.len() + other.len());
                for (k, v) in existing {
                    merged.push((k.clone(), v.clone_ref(self.py)));
                }
                for (k, v) in other {
                    merged.push((k.clone(), v.clone_ref(self.py)));
                }
                result.push(merged);
            }
        }
        self.rows = result;
    }
}

impl<'a> JsonVisitor for NormalizerVisitor<'a> {
    fn on_scalar(&mut self, path: &JsonPath, value: PyObject) {
        self.set_value(path, value);
    }

    fn on_null(&mut self, path: &JsonPath) {
        if let Some(ref ss) = self.opts.selection_set {
            if !ss.contains(path) {
                return;
            }
        }
        let name = self.generate_name(path);
        let none: PyObject = self.py.None();
        for row in self.rows.iter_mut() {
            row.push((name.clone(), none.clone_ref(self.py)));
        }
    }

    fn enter_array(
        &mut self,
        path: &JsonPath,
        value: PyObject,
        py: Python<'_>,
    ) -> VisitorAction {
        // For each non-None item in the array, normalize recursively, then cross-join.
        let bound = value.bind(py);
        let list: &Bound<'_, PyList> = bound.downcast().unwrap();
        let mut all_sub_rows: Vec<Row> = Vec::new();
        for item in list.iter() {
            if item.is_none() {
                continue;
            }
            if let Ok(sub_rows) =
                normalize_value(self.py, &item, self.opts, Some(path.clone()))
            {
                all_sub_rows.extend(sub_rows);
            }
        }
        self.cross_join(all_sub_rows);
        VisitorAction::Stop
    }
}

/// Convert Vec<Row> into a Python list of dicts.
fn rows_to_py(py: Python<'_>, rows: &[Row]) -> PyResult<Py<PyList>> {
    let list = PyList::empty(py);
    for row in rows {
        let dict = PyDict::new(py);
        for (key, value) in row {
            dict.set_item(key, value)?;
        }
        list.append(dict)?;
    }
    Ok(list.unbind())
}

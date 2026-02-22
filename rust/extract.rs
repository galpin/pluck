use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{HashMap, HashSet};

use crate::walker::{self, JsonPath, JsonVisitor, VisitorAction};

/// Extract frame data from a JSON response based on frame paths.
///
/// This is the Rust equivalent of the FrameExtractor visitor in `_execution.py`.
///
/// Args:
///     data: The JSON response data (a Python dict).
///     frame_paths: List of paths where frames are located, e.g. [["launches"], ["rockets"]].
///     nested_frame_paths: List of paths that have nested frames beneath them.
///
/// Returns:
///     A dict mapping frame name (last element of path) to list of extracted values.
#[pyfunction]
pub fn extract_frames(
    py: Python<'_>,
    data: &Bound<'_, PyAny>,
    frame_paths: Vec<Vec<String>>,
    nested_frame_paths: Vec<Vec<String>>,
) -> PyResult<Py<PyDict>> {
    let frame_path_set: HashSet<Vec<String>> = frame_paths.iter().cloned().collect();
    let nested_set: HashSet<Vec<String>> = nested_frame_paths.into_iter().collect();

    let mut visitor = FrameExtractorVisitor {
        frame_paths: frame_path_set,
        nested_frame_paths: nested_set,
        frame_data: HashMap::new(),
        captured: HashMap::new(),
    };

    walker::walk(py, data, &mut visitor, None);

    // Build result dict: frame_name -> list of values
    let result = PyDict::new(py);
    for path in &frame_paths {
        let name = path.last().map(|s| s.as_str()).unwrap_or("");
        let values = visitor.frame_data.remove(name).unwrap_or_default();
        let py_list = PyList::new(py, &values)?;
        result.set_item(name, py_list)?;
    }
    Ok(result.unbind())
}

struct FrameExtractorVisitor {
    frame_paths: HashSet<Vec<String>>,
    nested_frame_paths: HashSet<Vec<String>>,
    frame_data: HashMap<String, Vec<PyObject>>,
    /// Tracks paths we've already captured to avoid duplicates.
    captured: HashMap<Vec<String>, usize>,
}

impl FrameExtractorVisitor {
    fn is_frame_at(&self, path: &JsonPath) -> bool {
        self.frame_paths.contains(path)
    }

    fn has_nested_frame(&self, path: &JsonPath) -> bool {
        let len = path.len();
        self.nested_frame_paths.contains(path)
            || self.frame_paths.iter().any(|fp| {
                fp.len() > len && fp[..len] == path[..]
            })
    }

    fn try_enter(&mut self, path: &JsonPath, value: PyObject) -> VisitorAction {
        if !self.captured.contains_key(path) && self.is_frame_at(path) {
            let name = path.last().map(|s| s.as_str()).unwrap_or("").to_string();
            self.frame_data
                .entry(name)
                .or_default()
                .push(value);
            if !self.has_nested_frame(path) {
                return VisitorAction::Stop;
            }
            self.captured.insert(path.clone(), 0);
        }
        VisitorAction::Continue
    }
}

impl JsonVisitor for FrameExtractorVisitor {
    fn enter_object(
        &mut self,
        path: &JsonPath,
        value: PyObject,
        _py: Python<'_>,
    ) -> VisitorAction {
        self.try_enter(path, value)
    }

    fn enter_array(
        &mut self,
        path: &JsonPath,
        value: PyObject,
        _py: Python<'_>,
    ) -> VisitorAction {
        self.try_enter(path, value)
    }

    fn on_scalar(&mut self, path: &JsonPath, value: PyObject) {
        // For scalar frames, enter and immediately leave.
        if !self.captured.contains_key(path) && self.is_frame_at(path) {
            let name = path.last().map(|s| s.as_str()).unwrap_or("").to_string();
            self.frame_data
                .entry(name)
                .or_default()
                .push(value);
        }
    }

    fn leave(&mut self, path: &JsonPath) {
        self.captured.remove(path);
    }
}

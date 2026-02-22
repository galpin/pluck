use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString};
use std::collections::VecDeque;

/// Represents a path through a JSON structure (e.g., ["launches", "rocket", "name"]).
pub type JsonPath = Vec<String>;

/// Action returned by visitor callbacks to control traversal.
pub enum VisitorAction {
    Continue,
    Stop,
}

/// Trait for visiting nodes in a JSON-like Python object tree.
/// All value parameters are PyObject (owned) to avoid lifetime issues at trait boundaries.
pub trait JsonVisitor {
    fn enter_object(
        &mut self,
        _path: &JsonPath,
        _value: PyObject,
        _py: Python<'_>,
    ) -> VisitorAction {
        VisitorAction::Continue
    }

    fn enter_array(
        &mut self,
        _path: &JsonPath,
        _value: PyObject,
        _py: Python<'_>,
    ) -> VisitorAction {
        VisitorAction::Continue
    }

    fn leave(&mut self, _path: &JsonPath) {}

    fn on_scalar(&mut self, _path: &JsonPath, _value: PyObject) {}

    fn on_null(&mut self, _path: &JsonPath) {}
}

enum StackEntry {
    Visit(JsonPath, PyObject),
    Leave(JsonPath),
}

/// Walks a Python object tree (dicts, lists, scalars, None) calling visitor methods.
pub fn walk<V: JsonVisitor>(
    py: Python<'_>,
    root: &Bound<'_, PyAny>,
    visitor: &mut V,
    initial_path: Option<JsonPath>,
) {
    let mut stack: VecDeque<StackEntry> = VecDeque::new();
    let path = initial_path.unwrap_or_default();
    stack.push_front(StackEntry::Visit(path, root.clone().unbind()));

    while let Some(entry) = stack.pop_front() {
        match entry {
            StackEntry::Leave(path) => {
                visitor.leave(&path);
            }
            StackEntry::Visit(path, current) => {
                let bound = current.bind(py);
                if bound.is_none() {
                    visitor.on_null(&path);
                } else if let Ok(dict) = bound.downcast::<PyDict>() {
                    if matches!(
                        visitor.enter_object(&path, current.clone_ref(py), py),
                        VisitorAction::Continue
                    ) {
                        stack.push_front(StackEntry::Leave(path.clone()));
                        let items: Vec<_> = dict
                            .iter()
                            .map(|(k, v)| {
                                let key: String = k.extract().unwrap_or_default();
                                let mut child_path = path.clone();
                                child_path.push(key);
                                (child_path, v.unbind())
                            })
                            .collect();
                        for (child_path, value) in items.into_iter().rev() {
                            stack.push_front(StackEntry::Visit(child_path, value));
                        }
                    }
                } else if let Ok(list) = bound.downcast::<PyList>() {
                    if matches!(
                        visitor.enter_array(&path, current.clone_ref(py), py),
                        VisitorAction::Continue
                    ) {
                        stack.push_front(StackEntry::Leave(path.clone()));
                        let items: Vec<_> = list.iter().map(|v| v.unbind()).collect();
                        for value in items.into_iter().rev() {
                            stack.push_front(StackEntry::Visit(path.clone(), value));
                        }
                    }
                } else if is_scalar(bound) {
                    visitor.on_scalar(&path, current);
                }
            }
        }
    }
}

fn is_scalar(obj: &Bound<'_, PyAny>) -> bool {
    obj.is_instance_of::<PyString>()
        || obj.is_instance_of::<PyInt>()
        || obj.is_instance_of::<PyFloat>()
        || obj.is_instance_of::<PyBool>()
}

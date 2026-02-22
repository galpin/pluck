//! Arrow-based output: converts Vec<Row> directly to a PyArrow RecordBatch.
//! This eliminates per-cell PyObject creation by building typed Arrow arrays
//! in pure Rust and passing them to Python via zero-copy FFI.

use std::collections::HashMap;
use std::rc::Rc;
use std::sync::Arc;

use arrow::array::{
    ArrayRef, BooleanBuilder, Float64Builder, Int64Builder, NullArray, StringBuilder,
};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::pyarrow::ToPyArrow;
use arrow::record_batch::RecordBatch;
use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::normalize::{normalize_value, py_to_value, NormalizeOpts, Row, Value};
use std::collections::HashSet;

/// Detect the dominant (most common non-null) Arrow DataType for a column
/// by scanning all values. Falls back to Utf8 (string) for mixed types.
fn detect_column_type(rows: &[Row], col_idx: usize) -> DataType {
    let mut has_bool = false;
    let mut has_int = false;
    let mut has_float = false;
    let mut has_str = false;

    for row in rows {
        match &row[col_idx].1 {
            Value::Null => {}
            Value::Bool(_) => has_bool = true,
            Value::Int(_) => has_int = true,
            Value::Float(_) => has_float = true,
            Value::Str(_) => has_str = true,
            _ => has_str = true,
        }
    }

    // If only one non-null type, use it. If mixed, promote.
    match (has_bool, has_int, has_float, has_str) {
        (true, false, false, false) => DataType::Boolean,
        (false, true, false, false) => DataType::Int64,
        (false, false, true, false) => DataType::Float64,
        (false, false, false, true) => DataType::Utf8,
        // int + float → float
        (false, true, true, false) => DataType::Float64,
        // All nulls
        (false, false, false, false) => DataType::Null,
        // Anything else → string
        _ => DataType::Utf8,
    }
}

/// Build an Arrow ArrayRef for a single column from row data.
fn build_column_array(rows: &[Row], col_idx: usize, dtype: &DataType) -> ArrayRef {
    let num_rows = rows.len();

    match dtype {
        DataType::Boolean => {
            let mut builder = BooleanBuilder::with_capacity(num_rows);
            for row in rows {
                match &row[col_idx].1 {
                    Value::Bool(b) => builder.append_value(*b),
                    Value::Null => builder.append_null(),
                    _ => builder.append_null(),
                }
            }
            Arc::new(builder.finish())
        }
        DataType::Int64 => {
            let mut builder = Int64Builder::with_capacity(num_rows);
            for row in rows {
                match &row[col_idx].1 {
                    Value::Int(i) => builder.append_value(*i),
                    Value::Null => builder.append_null(),
                    _ => builder.append_null(),
                }
            }
            Arc::new(builder.finish())
        }
        DataType::Float64 => {
            let mut builder = Float64Builder::with_capacity(num_rows);
            for row in rows {
                match &row[col_idx].1 {
                    Value::Float(f) => builder.append_value(*f),
                    Value::Int(i) => builder.append_value(*i as f64),
                    Value::Null => builder.append_null(),
                    _ => builder.append_null(),
                }
            }
            Arc::new(builder.finish())
        }
        DataType::Utf8 => {
            let mut builder = StringBuilder::new();
            for row in rows {
                match &row[col_idx].1 {
                    Value::Str(s) => builder.append_value(s.as_ref()),
                    Value::Int(i) => builder.append_value(i.to_string()),
                    Value::Float(f) => builder.append_value(f.to_string()),
                    Value::Bool(b) => builder.append_value(if *b { "True" } else { "False" }),
                    Value::Null => builder.append_null(),
                    _ => builder.append_null(),
                }
            }
            Arc::new(builder.finish())
        }
        DataType::Null => Arc::new(NullArray::new(num_rows)),
        _ => Arc::new(NullArray::new(num_rows)),
    }
}

/// Convert Vec<Row> to an Arrow RecordBatch. Pure Rust, no Python interaction.
fn rows_to_record_batch(rows: &[Row]) -> RecordBatch {
    if rows.is_empty() {
        let schema = Schema::empty();
        return RecordBatch::new_empty(Arc::new(schema));
    }

    let num_cols = rows[0].len();

    // Detect types and build fields
    let mut fields = Vec::with_capacity(num_cols);
    let mut arrays: Vec<ArrayRef> = Vec::with_capacity(num_cols);

    for col_idx in 0..num_cols {
        let col_name = rows[0][col_idx].0.as_ref();
        let dtype = detect_column_type(rows, col_idx);
        fields.push(Field::new(col_name, dtype.clone(), true));
        arrays.push(build_column_array(rows, col_idx, &dtype));
    }

    let schema = Arc::new(Schema::new(fields));
    RecordBatch::try_new(schema, arrays).expect("failed to create RecordBatch")
}

/// Batch normalize and return a PyArrow RecordBatch.
/// This is the fastest path: Rust Value → Rust normalize → Arrow arrays → zero-copy FFI.
#[pyfunction]
#[pyo3(signature = (objects, separator=".", fallback="?", selection_set=None))]
pub fn normalize_arrow_batch(
    py: Python<'_>,
    objects: &Bound<'_, PyList>,
    separator: &str,
    fallback: &str,
    selection_set: Option<Vec<Vec<String>>>,
) -> PyResult<PyObject> {
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

    // Normalize all items, collecting rows in Rust (no Python interaction)
    let mut all_rows: Vec<Row> = Vec::new();
    for obj in objects.iter() {
        let value = py_to_value(&obj);
        let rows = normalize_value(&value, &opts, &mut path_stack, &mut name_cache);
        all_rows.extend(rows);
    }

    // Build RecordBatch from rows (pure Rust)
    let batch = rows_to_record_batch(&all_rows);

    // Zero-copy transfer to Python via Arrow C Data Interface
    batch.to_pyarrow(py)
}

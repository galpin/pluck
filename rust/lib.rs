mod arrow_out;
mod extract;
mod normalize;
mod walker;

use pyo3::prelude::*;

#[pymodule]
fn _pluck_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(normalize::normalize, m)?)?;
    m.add_function(wrap_pyfunction!(normalize::normalize_columnar, m)?)?;
    m.add_function(wrap_pyfunction!(normalize::normalize_columnar_batch, m)?)?;
    m.add_function(wrap_pyfunction!(arrow_out::normalize_arrow_batch, m)?)?;
    m.add_function(wrap_pyfunction!(extract::extract_frames, m)?)?;
    Ok(())
}

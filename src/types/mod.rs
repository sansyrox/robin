use std::collections::HashMap;
use log::debug;
use pyo3::{
    exceptions::PyValueError,
    prelude::*,
    types::{PyBool, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple},
};
use serde_json::Value;

pub mod function_info;
pub mod headers;
pub mod identity;
pub mod multimap;
pub mod request;
pub mod response;

#[allow(clippy::large_enum_variant)]
pub enum MiddlewareReturn {
    Request(request::Request),
    Response(response::Response),
}

#[pyclass]
#[allow(clippy::upper_case_acronyms)]
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum HttpMethod {
    GET,
    POST,
    PUT,
    DELETE,
    PATCH,
    HEAD,
    OPTIONS,
    CONNECT,
    TRACE,
}

impl HttpMethod {
    pub fn from_actix_method(method: &actix_web::http::Method) -> Self {
        match *method {
            actix_web::http::Method::GET => Self::GET,
            actix_web::http::Method::POST => Self::POST,
            actix_web::http::Method::PUT => Self::PUT,
            actix_web::http::Method::DELETE => Self::DELETE,
            actix_web::http::Method::PATCH => Self::PATCH,
            actix_web::http::Method::HEAD => Self::HEAD,
            actix_web::http::Method::OPTIONS => Self::OPTIONS,
            actix_web::http::Method::CONNECT => Self::CONNECT,
            actix_web::http::Method::TRACE => Self::TRACE,
            _ => panic!("Unsupported HTTP method"),
        }
    }
}

#[pyclass]
#[derive(Default, Debug, Clone)]
pub struct Url {
    #[pyo3(get)]
    pub scheme: String,
    #[pyo3(get)]
    pub host: String,
    #[pyo3(get)]
    pub path: String,
}

#[pymethods]
impl Url {
    #[new]
    pub fn new(scheme: &str, host: &str, path: &str) -> Self {
        Self {
            scheme: scheme.to_string(),
            host: host.to_string(),
            path: path.to_string(),
        }
    }
}

pub fn get_body_from_pyobject(body: &PyAny) -> PyResult<Vec<u8>> {
    if let Ok(s) = body.downcast::<PyString>() {
        Ok(s.to_string().into_bytes())
    } else if let Ok(b) = body.downcast::<PyBytes>() {
        Ok(b.as_bytes().to_vec())
    } else {
        debug!("Could not convert specified body to bytes");
        Ok(vec![])
    }
}

pub fn get_form_data_from_pyobject(form_data: &PyAny) -> PyResult<Option<HashMap<String, Value>>> {
    if let Ok(py_dict) = form_data.downcast::<PyDict>() {
        let mut map = HashMap::new();
        for (key, value) in py_dict.iter() {
            let key_str: String = key.extract()?;
            let json_value: Value = pyany_to_value(value)?;
            map.insert(key_str, json_value);
        }
        Ok(Some(map))
    } else {
        debug!("Could not convert specified form data");
        Ok(None)
    }
}

fn pyany_to_value(obj: &PyAny) -> PyResult<Value> {
    if obj.is_none() {
        Ok(Value::Null)
    } else if let Ok(val) = obj.downcast::<PyBool>() {
        Ok(Value::Bool(val.is_true()))
    } else if let Ok(val) = obj.downcast::<PyInt>() {
        let int_val: i64 = val.extract()?;
        Ok(Value::Number(int_val.into()))
    } else if let Ok(val) = obj.downcast::<PyFloat>() {
        let float_val: f64 = val.extract()?;
        Ok(Value::Number(serde_json::Number::from_f64(float_val).ok_or_else(|| {
            PyValueError::new_err("Failed to convert float")
        })?))
    } else if let Ok(val) = obj.downcast::<PyString>() {
        let str_val: String = val.extract()?;
        Ok(Value::String(str_val))
    } else if let Ok(val) = obj.downcast::<PyBytes>() {
        let bytes_val = val.extract::<Vec<u8>>()?.into_iter().map(|c| Value::Number(c.into())).collect();
        Ok(Value::Array(bytes_val))
    } else if let Ok(dict) = obj.downcast::<PyDict>() {
        let mut map = serde_json::Map::new();
        for (key, value) in dict.iter() {
            let key_str: String = key.extract()?;
            let json_value = pyany_to_value(value)?;
            map.insert(key_str, json_value);
        }
        Ok(Value::Object(map))
    } else if let Ok(list) = obj.downcast::<PyList>() {
        let vec = list.iter().map(pyany_to_value).collect::<Result<Vec<_>, _>>()?;
        Ok(Value::Array(vec))
    } else if let Ok(tuple) = obj.downcast::<PyTuple>() {
        let vec = tuple.iter().map(pyany_to_value).collect::<Result<Vec<_>, _>>()?;
        Ok(Value::Array(vec))
    } else {
        Err(PyValueError::new_err(
            "Unsupported Python type for conversion to JSON",
        ))
    }
}

pub fn get_description_from_pyobject(description: &PyAny) -> PyResult<Vec<u8>> {
    if let Ok(s) = description.downcast::<PyString>() {
        Ok(s.to_string().into_bytes())
    } else if let Ok(b) = description.downcast::<PyBytes>() {
        Ok(b.as_bytes().to_vec())
    } else {
        debug!("Could not convert specified response description to bytes");
        Ok(vec![])
    }
}

pub fn check_body_type(py: Python, body: &Py<PyAny>) -> PyResult<()> {
    if body.downcast::<PyString>(py).is_err() && body.downcast::<PyBytes>(py).is_err() {
        return Err(PyValueError::new_err(
            "Could not convert specified body to bytes",
        ));
    };
    Ok(())
}

pub fn check_description_type(py: Python, body: &Py<PyAny>) -> PyResult<()> {
    if body.downcast::<PyString>(py).is_err() && body.downcast::<PyBytes>(py).is_err() {
        return Err(PyValueError::new_err(
            "Could not convert specified response description to bytes",
        ));
    };
    Ok(())
}

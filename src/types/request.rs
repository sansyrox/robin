use actix_multipart::Multipart;
use actix_web::{
    web::{self, BytesMut},
    Error, HttpRequest,
};
use futures_util::StreamExt as _;
use log::debug;
use pyo3::types::{PyBytes, PyDict, PyList, PyString};
use pyo3::{exceptions::PyValueError, prelude::*};
use serde_json::Value;
use std::collections::HashMap;

use crate::types::{check_body_type, get_body_from_pyobject, Url};

use super::{headers::Headers, identity::Identity, multimap::QueryParams};

#[derive(Default, Debug, Clone, FromPyObject)]
pub struct Request {
    pub query_params: QueryParams,
    pub headers: Headers,
    pub method: String,
    pub path_params: HashMap<String, String>,
    // https://pyo3.rs/v0.19.2/function.html?highlight=from_py_#per-argument-options
    #[pyo3(from_py_with = "get_body_from_pyobject")]
    pub body: Vec<u8>,
    pub url: Url,
    pub ip_addr: Option<String>,
    pub identity: Option<Identity>,
    pub form_data: Option<HashMap<String, String>>,
    pub files: Option<HashMap<String, Vec<u8>>>,
}

impl ToPyObject for Request {
    fn to_object(&self, py: Python) -> PyObject {
        let query_params = self.query_params.clone();
        let headers: Py<Headers> = self.headers.clone().into_py(py).extract(py).unwrap();
        let path_params = self.path_params.clone().into_py(py).extract(py).unwrap();
        let body = match String::from_utf8(self.body.clone()) {
            Ok(s) => s.into_py(py),
            Err(_) => self.body.clone().into_py(py),
        };
        let form_data: Py<PyDict> = match &self.form_data {
            Some(data) => {
                let dict = PyDict::new(py);
                for (key, value) in data.iter() {
                    dict.set_item(key, value).unwrap();
                }
                dict.into_py(py)
            }
            None => PyDict::new(py).into_py(py),
        };

        let files: Py<PyDict> = match &self.files {
            Some(data) => {
                let dict = PyDict::new(py);
                for (key, value) in data.iter() {
                    let bytes = PyBytes::new(py, value);
                    dict.set_item(key, bytes).unwrap();
                }
                dict.into_py(py)
            }
            None => PyDict::new(py).into_py(py),
        };

        let request = PyRequest {
            query_params,
            path_params,
            headers,
            body,
            method: self.method.clone(),
            url: self.url.clone(),
            ip_addr: self.ip_addr.clone(),
            identity: self.identity.clone(),
            form_data: form_data.clone(),
            files: files.clone(),
        };
        Py::new(py, request).unwrap().as_ref(py).into()
    }
}

async fn handle_multipart(
    mut payload: Multipart,
    files: &mut HashMap<String, Vec<u8>>,
    form_data: &mut HashMap<String, String>,
    body: &mut Vec<u8>,
) -> Result<(), Error> {
    // Iterate over multipart stream

    while let Some(item) = payload.next().await {
        let mut field = item?;

        let mut data = Vec::new();
        // Read the field data
        while let Some(chunk) = field.next().await {
            debug!("Chunk: {:?}", chunk);
            let data_chunk = chunk?;
            data.extend_from_slice(&data_chunk);
        }

        let content_disposition = field.content_disposition();
        let field_name = content_disposition.get_name().unwrap_or_default();
        let file_name = content_disposition.get_filename().map(|s| s.to_string());

        body.extend_from_slice(&data.clone());

        if let Some(name) = file_name {
            files.insert(name, data);
        } else if let Ok(text) = String::from_utf8(data) {
            form_data.insert(field_name.to_string(), text);
        }
    }

    Ok(())
}

impl Request {
    pub async fn from_actix_request(
        req: &HttpRequest,
        mut payload: web::Payload,
        global_headers: &Headers,
    ) -> Self {
        let mut query_params: QueryParams = QueryParams::new();
        let mut form_data: HashMap<String, String> = HashMap::new();
        let mut files = HashMap::new();

        if !req.query_string().is_empty() {
            let split = req.query_string().split('&');
            for s in split {
                let path_params = s.split_once('=').unwrap_or((s, ""));
                let key = path_params.0.to_string();
                let value = path_params.1.to_string();

                query_params.set(key, value);
            }
        }

        let mut headers = Headers::from_actix_headers(req.headers());
        debug!("Global headers: {:?}", global_headers);
        headers.extend(global_headers);

        let body: Vec<u8> = if headers.contains(String::from("content-type"))
            && headers
                .get(String::from("content-type"))
                .is_some_and(|val| val.contains("multipart/form-data"))
        {
            let h = headers.get(String::from("content-type")).unwrap();
            debug!("Content-Type: {:?}", h);
            let multipart = Multipart::new(req.headers(), payload);
            let mut body_local: Vec<u8> = Vec::new();

            let a = handle_multipart(multipart, &mut files, &mut form_data, &mut body_local).await;

            if let Err(e) = a {
                debug!("Error handling multipart data: {:?}", e);
            }

            body_local
        } else {
            let mut body_local = BytesMut::new();
            while let Some(chunk) = payload.next().await {
                let chunk = chunk.expect("Failed to read chunk from payload");
                body_local.extend_from_slice(&chunk);
            }
            body_local.freeze().to_vec()
        };

        debug!("Request body: {:?}", body);
        debug!("Request headers: {:?}", headers);
        debug!("Request query params: {:?}", query_params);
        debug!("Request form data: {:?}", form_data);
        debug!("Request files: {:?}", files);

        let url = Url::new(
            req.connection_info().scheme(),
            req.connection_info().host(),
            req.path(),
        );
        let ip_addr = req.peer_addr().map(|val| val.ip().to_string());

        Self {
            query_params,
            headers,
            method: req.method().as_str().to_owned(),
            path_params: HashMap::new(),
            body,
            url,
            ip_addr,
            identity: None,
            form_data: Some(form_data),
            files: Some(files),
        }
    }
}

#[pyclass(name = "Request")]
#[derive(Clone)]
pub struct PyRequest {
    #[pyo3(get, set)]
    pub query_params: QueryParams,
    #[pyo3(get, set)]
    pub headers: Py<Headers>,
    #[pyo3(get, set)]
    pub path_params: Py<PyDict>,
    #[pyo3(get, set)]
    pub identity: Option<Identity>,
    #[pyo3(get)]
    pub body: Py<PyAny>,
    #[pyo3(get)]
    pub method: String,
    #[pyo3(get)]
    pub url: Url,
    #[pyo3(get)]
    pub ip_addr: Option<String>,
    #[pyo3(get, set)]
    pub form_data: Py<PyDict>,
    #[pyo3(get, set)]
    pub files: Py<PyDict>,
}

#[pymethods]
impl PyRequest {
    #[new]
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        query_params: QueryParams,
        headers: Py<Headers>,
        path_params: Py<PyDict>,
        body: Py<PyAny>,
        method: String,
        url: Url,
        form_data: Py<PyDict>,
        files: Py<PyDict>,
        identity: Option<Identity>,
        ip_addr: Option<String>,
    ) -> Self {
        Self {
            query_params,
            headers,
            path_params,
            identity,
            body,
            method,
            url,
            form_data,
            files,
            ip_addr,
        }
    }

    #[setter]
    pub fn set_body(&mut self, py: Python, body: Py<PyAny>) -> PyResult<()> {
        check_body_type(py, &body)?;
        self.body = body;
        Ok(())
    }

    pub fn json(&self, py: Python) -> PyResult<PyObject> {
        match self.body.as_ref(py).downcast::<PyString>() {
            Ok(python_string) => json_string_to_pyobject(py, python_string.extract()?),
            Err(e) => Err(e.into()),
        }
    }
}

///serde_json not impl IntoPy<PyObject>  but orphan principle. so use this function
fn json_string_to_pyobject(py: Python, json_string: &str) -> PyResult<PyObject> {
    /// Converts a serde_json::Number to a Python object.
    fn number_to_pyobject(num: serde_json::Number, py: Python) -> PyResult<PyObject> {
        match num.as_u64() {
            Some(u) => Ok(u.into_py(py)),
            None => match num.as_i64() {
                Some(i) => Ok(i.into_py(py)),
                None => match num.as_f64() {
                    Some(f) => Ok(f.into_py(py)),
                    None => Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
                        "Invalid number format",
                    )),
                },
            },
        }
    }

    /// Converts a serde_json::Value to a Python object.
    fn value_to_pyobject(py: Python, value: serde_json::Value) -> PyResult<PyObject> {
        match value {
            Value::Null => Ok(().into_py(py)),
            Value::Bool(b) => Ok(b.into_py(py)),
            Value::Number(num) => number_to_pyobject(num, py),
            Value::String(s) => Ok(s.into_py(py)),
            Value::Array(array) => array
                .into_iter()
                .map(|v| value_to_pyobject(py, v))
                .collect::<PyResult<Vec<PyObject>>>()
                .map(|list| PyList::new(py, list).into()),
            Value::Object(map) => {
                let dict = PyDict::new(py);
                for (key, value) in map.into_iter() {
                    let py_key = key.to_string().into_py(py);
                    let py_value = value_to_pyobject(py, value)?;
                    dict.set_item(py_key, py_value)?;
                }
                Ok(dict.into_py(py))
            }
        }
    }
    match serde_json::from_str(json_string) {
        Ok(value) => value_to_pyobject(py, value),
        Err(e) => Err(PyValueError::new_err(format!("Invalid JSON: {}", e))),
    }
}

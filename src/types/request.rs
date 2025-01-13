use actix_multipart::Multipart;
use actix_web::{
    web::{self, BytesMut},
    Error, HttpRequest,
};
use futures_util::StreamExt as _;
use log::debug;
use percent_encoding::percent_decode;
use pyo3::types::{PyBytes, PyDict, PyString};
use pyo3::{
    exceptions::PyValueError,
    prelude::*,
    types::{PyAny, PyList},
};
use serde_json::Value;
use std::collections::HashMap;

use crate::types::{check_body_type, get_body_from_pyobject, get_form_data_from_pyobject, Url};

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
    #[pyo3(from_py_with = "get_form_data_from_pyobject")]
    pub form_data: Option<HashMap<String, Value>>,
    #[pyo3(from_py_with = "get_form_data_from_pyobject")]
    pub files: Option<HashMap<String, Value>>,
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
                    dict.set_item(key, value_to_pyany(py, value).unwrap())
                        .unwrap();
                }
                dict.into_py(py)
            }
            None => PyDict::new(py).into_py(py),
        };
        let files: Py<PyDict> = match &self.files {
            Some(data) => {
                let dict = PyDict::new(py);
                for (field, value) in data.iter() {
                    let mut _dict = PyDict::new(py);
                    match value {
                        Value::Object(file_dict) => {
                            for (file_name, val) in file_dict {
                                if let Value::Array(file_content) = val {
                                    let mut single = true;
                                    let files = PyList::empty(py);
                                    let mut file_bytes: Vec<u8> = Vec::new();
                                    for file_data in file_content.into_iter() {
                                        if let Value::Array(_files) = file_data {
                                            // file list
                                            single = false;
                                            let mut _file_bytes: Vec<u8> = Vec::new();
                                            for _file in _files.into_iter() {
                                                if let Value::Number(content) = _file {
                                                    if let Some(i) = content.as_u64() {
                                                        if i <= u8::MAX as u64 {
                                                            let num_u8 = i as u8;
                                                            _file_bytes.push(num_u8);
                                                        }
                                                    }
                                                }
                                            }
                                            files.append(PyBytes::new(py, &_file_bytes)).unwrap();
                                        } else if let Value::Number(content) = file_data {
                                            // file char
                                            if let Some(i) = content.as_u64() {
                                                if i <= u8::MAX as u64 {
                                                    let num_u8 = i as u8;
                                                    file_bytes.push(num_u8);
                                                }
                                            }
                                        } else {
                                            _dict.set_item(file_name, py.None()).unwrap();
                                        }
                                    }
                                    if single {
                                        _dict.set_item(file_name, PyBytes::new(py, &file_bytes)).unwrap();
                                    } else {
                                        _dict.set_item(file_name, files).unwrap();
                                    }
                                } else {
                                    _dict.set_item(file_name, py.None()).unwrap();
                                }
                            }
                        }
                        _ => {
                            _dict = PyDict::new(py);
                        }
                    }
                    dict.set_item(field, _dict).unwrap();
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
    files: &mut HashMap<String, Value>,
    form_data: &mut HashMap<String, Value>,
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
            match files.get(field_name) {
                Some(f) => match f {
                    Value::Array(f) => {
                        let mut _f = f.clone();
                        let mut file_map = serde_json::Map::new();
                        file_map.insert(name, data.into());
                        _f.push(serde_json::Value::Object(file_map));
                        files.insert(field_name.to_owned(), serde_json::Value::Array(_f));
                    }
                    _ => {
                        let mut file_map = serde_json::Map::new();
                        file_map.insert(name, data.into());
                        files.insert(
                            field_name.to_owned(),
                            vec![f.clone(), serde_json::Value::Object(file_map)].into(),
                        );
                    }
                },
                None => {
                    let mut file_map = serde_json::Map::new();
                    file_map.insert(name, data.into());
                    files.insert(field_name.to_owned(), serde_json::Value::Object(file_map));
                }
            };
        } else if let Ok(value) = String::from_utf8(data) {
            form_data_handler(form_data, field_name, &value)?;
        }
    }

    Ok(())
}

async fn handle_form(
    mut payload: web::Payload,
    form_data: &mut HashMap<String, Value>,
    body: &mut Vec<u8>,
) -> Result<(), Error> {
    // Iterate over multipart stream
    let mut data = web::BytesMut::new();
    while let Some(chunk) = payload.next().await {
        let chunk = chunk?;
        data.extend_from_slice(&chunk);
        body.extend_from_slice(&chunk);
    }
    let body_str = std::str::from_utf8(&data)?;
    let body_str_split: Vec<&str> = body_str.split("&").collect();
    for i in body_str_split {
        let key_value: Vec<&str> = i.split("=").collect();
        if let [key, value] = key_value[..] {
            form_data_handler(form_data, key, value)?;
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
        let mut form_data: HashMap<String, Value> = HashMap::new();
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
        } else if headers.contains(String::from("content-type"))
            && headers
                .get(String::from("content-type"))
                .is_some_and(|val| val.contains("application/x-www-form-urlencoded"))
        {
            let h = headers.get(String::from("content-type")).unwrap();
            debug!("Content-Type: {:?}", h);
            let mut body_local: Vec<u8> = Vec::new();

            let a = handle_form(payload, &mut form_data, &mut body_local).await;

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
            // use python orjson deserialization
            // let orjson_mod = PyModule::import(py, "orjson")?;
            // let fun = orjson_mod.getattr("loads")?;
            // let parsed_json = fun.call1((python_string,))?;

            // Ok(parsed_json.into_py(py))
            Ok(python_string) => match serde_json::from_str(python_string.extract()?) {
                Ok(map) => {
                    let dict = value_to_pydict(py, &map)?;
                    Ok(dict.into_py(py))
                }
                Err(_) => Err(PyValueError::new_err("Invalid JSON Object.")),
            },
            Err(e) => Err(e.into()),
        }
    }
}

fn value_to_pydict<'a>(py: Python<'a>, value: &Value) -> PyResult<&'a PyDict> {
    let dict = PyDict::new(py);

    if let Value::Object(map) = value {
        for (key, val) in map {
            let py_val = value_to_pyany(py, val)?;
            dict.set_item(key, py_val)?;
        }
    }

    Ok(dict)
}

fn value_to_pyany(py: Python, val: &Value) -> PyResult<Py<PyAny>> {
    let object = match val {
        Value::Null => py.None(),
        Value::Bool(b) => b.into_py(py),
        Value::Number(num) => {
            if let Some(i) = num.as_i64() {
                i.into_py(py)
            } else if let Some(u) = num.as_u64() {
                u.into_py(py)
            } else if let Some(f) = num.as_f64() {
                f.into_py(py)
            } else {
                return Err(PyValueError::new_err("Unsupported number type"));
            }
        }
        Value::String(s) => s.into_py(py),
        Value::Array(arr) => {
            let py_list = PyList::new(py, arr.iter().map(|v| value_to_pyany(py, v).unwrap()));
            py_list.into_py(py)
        }
        Value::Object(_) => value_to_pydict(py, val)?.into_py(py),
    };
    Ok(object)
}

fn form_data_handler(
    form_data: &mut HashMap<String, Value>,
    key: &str,
    value: &str,
) -> Result<(), Error> {
    match form_data.get(key) {
        Some(v) => match v {
            Value::Array(vs) => {
                let mut _vs = vs.clone();
                _vs.push(serde_json::Value::String(
                    percent_decode(value.as_bytes()).decode_utf8()?.into_owned(),
                ));
                form_data.insert(key.to_owned(), serde_json::Value::Array(_vs));
            }
            _ => {
                form_data.insert(
                    key.to_owned(),
                    vec![
                        v.clone(),
                        serde_json::Value::String(
                            percent_decode(value.as_bytes()).decode_utf8()?.into_owned(),
                        ),
                    ]
                    .into(),
                );
            }
        },
        None => {
            form_data.insert(
                key.to_owned(),
                percent_decode(value.as_bytes())
                    .decode_utf8()?
                    .into_owned()
                    .into(),
            );
        }
    };
    Ok(())
}

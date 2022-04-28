/// This is the module that has all the executor functions
/// i.e. the functions that have the responsibility of parsing and executing functions.
use crate::io_helpers::read_file;

use std::borrow::Borrow;
use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;
use std::sync::Arc;

use actix_web::{http::Method, web, HttpRequest};
use anyhow::{bail, Result};
use futures::lock::Mutex;
// pyO3 module
use crate::types::{Headers, PyFunction};
use futures_util::stream::StreamExt;
use pyo3::prelude::*;
use pyo3::types::PyDict;

/// @TODO make configurable
const MAX_SIZE: usize = 10_000;

pub async fn execute_middleware_function<'a>(
    function: PyFunction,
    payload: &mut web::Payload,
    headers: &Headers,
    req: &HttpRequest,
    route_params: HashMap<String, String>,
    queries: Rc<RefCell<HashMap<String, String>>>,
    number_of_params: u8,
) -> Result<HashMap<String, HashMap<String, String>>> {
    // TODO:
    // try executing the first version of middleware(s) here
    // with just headers as params

    let mut data: Vec<u8> = Vec::new();

    if req.method() == Method::POST
        || req.method() == Method::PUT
        || req.method() == Method::PATCH
        || req.method() == Method::DELETE
    {
        let mut body = web::BytesMut::new();
        while let Some(chunk) = payload.next().await {
            let chunk = chunk?;
            // limit max size of in-memory payload
            if (body.len() + chunk.len()) > MAX_SIZE {
                bail!("Body content Overflow");
            }
            body.extend_from_slice(&chunk);
        }

        data = body.to_vec()
    }

    // request object accessible while creating routes
    let mut request = HashMap::new();
    let mut headers_python = HashMap::new();
    for elem in (*headers).iter() {
        headers_python.insert(elem.key().clone(), elem.value().clone());
    }
    let mut queries_clone: HashMap<String, String> = HashMap::new();

    for (key, value) in (*queries).borrow().clone() {
        queries_clone.insert(key, value);
    }

    match function {
        PyFunction::CoRoutine(handler) => {
            let output = Python::with_gil(|py| {
                let handler = handler.as_ref(py);
                request.insert("params", route_params.into_py(py));
                request.insert("queries", queries_clone.into_py(py));
                request.insert("headers", headers_python.into_py(py));
                // request.insert("body", data.into_py(py));

                // this makes the request object to be accessible across every route
                let coro: PyResult<&PyAny> = match number_of_params {
                    0 => handler.call0(),
                    1 => handler.call1((request,)),
                    // this is done to accomodate any future params
                    2_u8..=u8::MAX => handler.call1((request,)),
                };
                pyo3_asyncio::tokio::into_future(coro?)
            })?;

            let output = output.await?;

            let res =
                Python::with_gil(|py| -> PyResult<HashMap<String, HashMap<String, String>>> {
                    let output: Vec<HashMap<String, HashMap<String, String>>> =
                        output.extract(py).unwrap();
                    let responses = output[0].clone();
                    Ok(responses)
                })?;

            Ok(res)
        }

        PyFunction::SyncFunction(handler) => {
            // do we even need this?
            // How else can we return a future from this?
            // let's wrap the output in a future?
            let output: Result<HashMap<String, HashMap<String, String>>> = Python::with_gil(|py| {
                let handler = handler.as_ref(py);
                request.insert("params", route_params.into_py(py));
                request.insert("queries", queries_clone.into_py(py));
                request.insert("headers", headers_python.into_py(py));
                request.insert("body", data.into_py(py));

                let output: PyResult<&PyAny> = match number_of_params {
                    0 => handler.call0(),
                    1 => handler.call1((request,)),
                    // this is done to accomodate any future params
                    2_u8..=u8::MAX => handler.call1((request,)),
                };

                let output: Vec<HashMap<String, HashMap<String, String>>> =
                    output?.extract().unwrap();

                Ok(output[0].clone())
            });

            Ok(output.unwrap())
        }
    }
}

// Change this!
#[inline]
pub async fn execute_http_function(
    function: PyFunction,
    payload: &mut web::Payload,
    headers: HashMap<String, String>,
    req: &HttpRequest,
    route_params: HashMap<String, String>,
    queries: Rc<RefCell<HashMap<String, String>>>,
    number_of_params: u8,
    // need to change this to return a response struct
    // create a custom struct for this
) -> Result<HashMap<String, String>> {
    let mut data: Vec<u8> = Vec::new();

    if req.method() == Method::POST
        || req.method() == Method::PUT
        || req.method() == Method::PATCH
        || req.method() == Method::DELETE
    {
        let mut body = web::BytesMut::new();
        while let Some(chunk) = payload.next().await {
            let chunk = chunk?;
            // limit max size of in-memory payload
            if (body.len() + chunk.len()) > MAX_SIZE {
                bail!("Body content Overflow");
            }
            body.extend_from_slice(&chunk);
        }

        data = body.to_vec()
    }

    // request object accessible while creating routes
    let mut request = HashMap::new();

    let mut queries_clone: HashMap<String, String> = HashMap::new();

    for (key, value) in (*queries).borrow().clone() {
        queries_clone.insert(key, value);
    }

    match function {
        PyFunction::CoRoutine(handler) => {
            let output = Python::with_gil(|py| {
                let handler = handler.as_ref(py);
                request.insert("params", route_params.into_py(py));
                request.insert("queries", queries_clone.into_py(py));
                request.insert("headers", headers.into_py(py));
                let data = data.into_py(py);
                request.insert("body", data);

                // this makes the request object to be accessible across every route
                let coro: PyResult<&PyAny> = match number_of_params {
                    0 => handler.call0(),
                    1 => handler.call1((request,)),
                    // this is done to accomodate any future params
                    2_u8..=u8::MAX => handler.call1((request,)),
                };
                pyo3_asyncio::tokio::into_future(coro?)
            })?;

            let output = output.await?;
            let res = Python::with_gil(|py| -> PyResult<HashMap<String, String>> {
                println!("This is the result of the code {:?}", output);

                let mut res: HashMap<String, String> =
                    output.into_ref(py).downcast::<PyDict>()?.extract()?;

                let response_type = res.get("type").unwrap();

                if response_type == "static_file" {
                    let file_path = res.get("file_path").unwrap();
                    let contents = read_file(file_path);
                    res.insert("body".to_owned(), contents);
                }
                Ok(res)
            })?;

            Ok(res)
        }

        PyFunction::SyncFunction(handler) => {
            tokio::task::spawn_blocking(move || {
                Python::with_gil(|py| {
                    let handler = handler.as_ref(py);
                    request.insert("params", route_params.into_py(py));
                    request.insert("headers", headers.into_py(py));
                    let data = data.into_py(py);
                    request.insert("body", data);

                    let output: PyResult<&PyAny> = match number_of_params {
                        0 => handler.call0(),
                        1 => handler.call1((request,)),
                        // this is done to accomodate any future params
                        2_u8..=u8::MAX => handler.call1((request,)),
                    };
                    let output: HashMap<String, String> = output?.extract()?;
                    // also convert to object here
                    // also check why don't sync functions have file handling enabled
                    Ok(output)
                })
            })
            .await?
        }
    }
}

pub async fn execute_event_handler(
    event_handler: Option<Arc<PyFunction>>,
    event_loop: Arc<Py<PyAny>>,
) {
    if let Some(handler) = event_handler {
        match &(*handler) {
            PyFunction::SyncFunction(function) => {
                println!("Startup event handler");
                Python::with_gil(|py| {
                    function.call0(py).unwrap();
                });
            }
            PyFunction::CoRoutine(function) => {
                let future = Python::with_gil(|py| {
                    println!("Startup event handler async");

                    let coroutine = function.as_ref(py).call0().unwrap();
                    pyo3_asyncio::into_future_with_loop((*event_loop).as_ref(py), coroutine)
                        .unwrap()
                });
                future.await.unwrap();
            }
        }
    }
}

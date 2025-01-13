use crate::executors::{
    execute_http_function, execute_middleware_function, execute_startup_handler,
};

use crate::routers::const_router::ConstRouter;
use crate::routers::Router;

use crate::routers::http_router::HttpRouter;
use crate::routers::{middleware_router::MiddlewareRouter, web_socket_router::WebSocketRouter};
use crate::shared_socket::SocketHeld;
use crate::types::function_info::{FunctionInfo, MiddlewareType};
use crate::types::headers::Headers;
use crate::types::request::Request;
use crate::types::response::Response;
use crate::types::HttpMethod;
use crate::types::MiddlewareReturn;
use crate::websockets::start_web_socket;

use std::sync::atomic::AtomicBool;
use std::sync::atomic::Ordering::{Relaxed, SeqCst};
use std::sync::{Arc, RwLock};

use std::process::exit;
use std::{env, thread};

use actix_files::Files;
use actix_http::KeepAlive;
use actix_web::*;

// pyO3 module
use log::{debug, error};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

const MAX_PAYLOAD_SIZE: &str = "ROBYN_MAX_PAYLOAD_SIZE";
const DEFAULT_MAX_PAYLOAD_SIZE: usize = 1_000_000; // 1Mb

static STARTED: AtomicBool = AtomicBool::new(false);

#[derive(Clone)]
struct Directory {
    route: String,
    directory_path: String,
    show_files_listing: bool,
    index_file: Option<String>,
}

#[pyclass]
pub struct Server {
    router: Arc<HttpRouter>,
    const_router: Arc<ConstRouter>,
    websocket_router: Arc<WebSocketRouter>,
    middleware_router: Arc<MiddlewareRouter>,
    global_request_headers: Arc<Headers>,
    global_response_headers: Arc<Headers>,
    directories: Arc<RwLock<Vec<Directory>>>,
    startup_handler: Option<Arc<FunctionInfo>>,
    shutdown_handler: Option<Arc<FunctionInfo>>,
    excluded_response_headers_paths: Option<Vec<String>>,
}

#[pymethods]
impl Server {
    #[new]
    pub fn new() -> Self {
        Self {
            router: Arc::new(HttpRouter::new()),
            const_router: Arc::new(ConstRouter::new()),
            websocket_router: Arc::new(WebSocketRouter::new()),
            middleware_router: Arc::new(MiddlewareRouter::new()),
            global_request_headers: Arc::new(Headers::new(None)),
            global_response_headers: Arc::new(Headers::new(None)),
            directories: Arc::new(RwLock::new(Vec::new())),
            startup_handler: None,
            shutdown_handler: None,
            excluded_response_headers_paths: None,
        }
    }

    pub fn start(
        &mut self,
        py: Python,
        socket: &PyCell<SocketHeld>,
        workers: usize,
    ) -> PyResult<()> {
        pyo3_log::init();

        if STARTED
            .compare_exchange(false, true, SeqCst, Relaxed)
            .is_err()
        {
            debug!("Robyn is already running...");
            return Ok(());
        }

        let raw_socket = socket.try_borrow_mut()?.get_socket();

        let router = self.router.clone();
        let const_router = self.const_router.clone();
        let middleware_router = self.middleware_router.clone();
        let web_socket_router = self.websocket_router.clone();
        let global_request_headers = self.global_request_headers.clone();
        let global_response_headers = self.global_response_headers.clone();
        let directories = self.directories.clone();

        let asyncio = py.import("asyncio")?;
        let event_loop = asyncio.call_method0("new_event_loop")?;
        asyncio.call_method1("set_event_loop", (event_loop,))?;

        let startup_handler = self.startup_handler.clone();
        let shutdown_handler = self.shutdown_handler.clone();

        let excluded_response_headers_paths = self.excluded_response_headers_paths.clone();

        let task_locals = pyo3_asyncio::TaskLocals::new(event_loop).copy_context(py)?;
        let task_locals_copy = task_locals.clone();

        let max_payload_size = env::var(MAX_PAYLOAD_SIZE)
            .unwrap_or(DEFAULT_MAX_PAYLOAD_SIZE.to_string())
            .trim()
            .parse::<usize>()
            .map_err(|e| {
                PyValueError::new_err(format!(
                    "Failed to parse environment variable {MAX_PAYLOAD_SIZE} - {e}"
                ))
            })?;

        thread::spawn(move || {
            actix_web::rt::System::new().block_on(async move {
                debug!("The number of workers is {}", workers);
                execute_startup_handler(startup_handler, &task_locals_copy)
                    .await
                    .unwrap();

                HttpServer::new(move || {
                    let mut app = App::new();

                    let task_locals = task_locals_copy.clone();
                    let directories = directories.read().unwrap();

                    // this loop matches three types of directory serving
                    // 1. Serves a build folder. e.g. the build folder generated from yarn build
                    // 2. Shows file listing
                    // 3. Just serves the file without any redirection to sub links
                    for directory in directories.iter() {
                        if let Some(index_file) = &directory.index_file {
                            app = app.service(
                                Files::new(&directory.route, &directory.directory_path)
                                    .index_file(index_file)
                                    .redirect_to_slash_directory(),
                            );
                        } else if directory.show_files_listing {
                            app = app.service(
                                Files::new(&directory.route, &directory.directory_path)
                                    .redirect_to_slash_directory()
                                    .show_files_listing(),
                            );
                        } else {
                            app = app
                                .service(Files::new(&directory.route, &directory.directory_path));
                        }
                    }

                    app = app
                        .app_data(web::Data::new(router.clone()))
                        .app_data(web::Data::new(const_router.clone()))
                        .app_data(web::Data::new(middleware_router.clone()))
                        .app_data(web::Data::new(global_request_headers.clone()))
                        .app_data(web::Data::new(global_response_headers.clone()))
                        .app_data(web::Data::new(excluded_response_headers_paths.clone()));

                    let web_socket_map = web_socket_router.get_web_socket_map();
                    for (elem, value) in (web_socket_map.read()).iter() {
                        let endpoint = elem.clone();
                        let path_params = value.clone();
                        let task_locals = task_locals.clone();
                        app = app.route(
                            &endpoint.clone(),
                            web::get().to(move |stream: web::Payload, req: HttpRequest| {
                                let endpoint_copy = endpoint.clone();
                                start_web_socket(
                                    req,
                                    stream,
                                    path_params.clone(),
                                    task_locals.clone(),
                                    endpoint_copy,
                                )
                            }),
                        );
                    }

                    debug!("Max payload size is {}", max_payload_size);

                    app.app_data(web::PayloadConfig::new(max_payload_size))
                        .default_service(web::route().to(
                            move |router: web::Data<Arc<HttpRouter>>,
                                  const_router: web::Data<Arc<ConstRouter>>,
                                  middleware_router: web::Data<Arc<MiddlewareRouter>>,
                                  payload: web::Payload,
                                  global_request_headers,
                                  global_response_headers,
                                  response_headers_exclude_paths,
                                  req| {
                                pyo3_asyncio::tokio::scope_local(task_locals.clone(), async move {
                                    index(
                                        router,
                                        payload,
                                        const_router,
                                        middleware_router,
                                        global_request_headers,
                                        global_response_headers,
                                        response_headers_exclude_paths,
                                        req,
                                    )
                                    .await
                                })
                            },
                        ))
                })
                .keep_alive(KeepAlive::Os)
                .workers(workers)
                .client_request_timeout(std::time::Duration::from_secs(0))
                .listen(raw_socket.into())
                .unwrap()
                .run()
                .await
                .unwrap();
            });
        });

        let event_loop = (*event_loop).call_method0("run_forever");
        if event_loop.is_err() {
            debug!("Ctrl c handler");

            // executing this from the same file (and not creating a function -- like startup handler)
            // to fix an issue that arises when a new async function is spooled up.

            // if we create a function & move the code, the function won't run s & raises the warning:
            // "unused implementer of `futures_util::Future` that must be used futures do nothing
            // unless you await or poll them."

            // but, adding `.await` raises the error "await is used inside non-async function,
            // which is not an async context".

            // which can only be solved by creating a new async function -- hence, resorting
            // to this solution

            if let Some(function) = shutdown_handler {
                if function.is_async {
                    debug!("Shutdown event handler async");

                    pyo3_asyncio::tokio::run_until_complete(
                        task_locals.event_loop(py),
                        pyo3_asyncio::into_future_with_locals(
                            &task_locals.clone(),
                            function.handler.as_ref(py).call0()?,
                        )
                        .unwrap(),
                    )
                    .unwrap();
                } else {
                    debug!("Shutdown event handler");

                    Python::with_gil(|py| function.handler.call0(py))?;
                }
            }

            exit(0);
        }
        Ok(())
    }

    pub fn add_directory(
        &mut self,
        route: String,
        directory_path: String,
        show_files_listing: bool,
        index_file: Option<String>,
    ) {
        self.directories.write().unwrap().push(Directory {
            route,
            directory_path,
            show_files_listing,
            index_file,
        });
    }

    /// Removes a new request header to our concurrent hashmap
    /// this can be called after the server has started.
    pub fn remove_header(&self, key: &str) {
        self.global_request_headers.headers.remove(key);
    }

    /// Removes a new response header to our concurrent hashmap
    /// this can be called after the server has started.
    pub fn remove_response_header(&self, key: &str) {
        self.global_response_headers.headers.remove(key);
    }

    pub fn apply_request_headers(&mut self, headers: &Headers) {
        self.global_request_headers = Arc::new(headers.clone());
    }

    pub fn apply_response_headers(&mut self, headers: &Headers) {
        self.global_response_headers = Arc::new(headers.clone());
    }

    pub fn set_response_headers_exclude_paths(
        &mut self,
        excluded_response_headers_paths: Option<Vec<String>>,
    ) {
        self.excluded_response_headers_paths = excluded_response_headers_paths;
    }

    /// Add a new route to the routing tables
    /// can be called after the server has been started
    pub fn add_route(
        &self,
        py: Python,
        route_type: &HttpMethod,
        route: &str,
        function: FunctionInfo,
        is_const: bool,
    ) {
        let second_route: String = if route.ends_with('/') {
            route[0..route.len() - 1].to_string()
        } else {
            format!("{}/", route)
        };

        self._add_route(py, route_type, route, function.clone(), is_const);
        self._add_route(py, route_type, &second_route, function, is_const);
    }

    fn _add_route(
        &self,
        py: Python,
        route_type: &HttpMethod,
        route: &str,
        function: FunctionInfo,
        is_const: bool,
    ) {
        debug!("Route added for {:?} {} ", route_type, route);
        let asyncio = py.import("asyncio").unwrap();
        let event_loop = asyncio.call_method0("get_event_loop").unwrap();

        if is_const {
            match self
                .const_router
                .add_route(route_type, route, function, Some(event_loop))
            {
                Ok(_) => (),
                Err(e) => {
                    debug!("Error adding const route {}", e);
                }
            }
        } else {
            match self.router.add_route(route_type, route, function, None) {
                Ok(_) => (),
                Err(e) => {
                    debug!("Error adding route {}", e);
                }
            }
        }
    }

    /// Add a new global middleware
    /// can be called after the server has been started
    pub fn add_global_middleware(&self, middleware_type: &MiddlewareType, function: FunctionInfo) {
        self.middleware_router
            .add_global_middleware(middleware_type, function)
            .unwrap();
    }

    /// Add a new route to the routing tables
    /// can be called after the server has been started
    pub fn add_middleware_route(
        &self,
        middleware_type: &MiddlewareType,
        route: &str,
        function: FunctionInfo,
    ) {
        debug!(
            "MiddleWare Route added for {:?} {} ",
            middleware_type, route
        );
        self.middleware_router
            .add_route(middleware_type, route, function, None)
            .unwrap();
    }

    /// Add a new web socket route to the routing tables
    /// can be called after the server has been started
    pub fn add_web_socket_route(
        &mut self,
        route: &str,
        connect_route: FunctionInfo,
        close_route: FunctionInfo,
        message_route: FunctionInfo,
    ) {
        self.websocket_router
            .add_websocket_route(route, connect_route, close_route, message_route);
    }

    /// Add a new startup handler
    pub fn add_startup_handler(&mut self, function: FunctionInfo) {
        self.startup_handler = Some(Arc::new(function));
        debug!("Added startup handler {:?}", self.startup_handler);
    }

    /// Add a new shutdown handler
    pub fn add_shutdown_handler(&mut self, function: FunctionInfo) {
        self.shutdown_handler = Some(Arc::new(function));
        debug!("Added shutdown handler {:?}", self.shutdown_handler);
    }
}

impl Default for Server {
    fn default() -> Self {
        Self::new()
    }
}

/// This is our service handler. It receives a Request, routes on it
/// path, and returns a Future of a Response.
#[allow(clippy::too_many_arguments)]
async fn index(
    router: web::Data<Arc<HttpRouter>>,
    payload: web::Payload,
    const_router: web::Data<Arc<ConstRouter>>,
    middleware_router: web::Data<Arc<MiddlewareRouter>>,
    global_request_headers: web::Data<Arc<Headers>>,
    global_response_headers: web::Data<Arc<Headers>>,
    excluded_response_headers_paths: web::Data<Option<Vec<String>>>,
    req: HttpRequest,
) -> impl Responder {
    let mut request = Request::from_actix_request(&req, payload, &global_request_headers).await;

    // Before middleware
    // Global
    let mut before_middlewares =
        middleware_router.get_global_middlewares(&MiddlewareType::BeforeRequest);
    // Route specific
    if let Some((function, route_params)) =
        middleware_router.get_route(&MiddlewareType::BeforeRequest, req.uri().path())
    {
        before_middlewares.push(function);
        request.path_params = route_params;
    }
    for before_middleware in before_middlewares {
        request = match execute_middleware_function(&request, &before_middleware).await {
            Ok(MiddlewareReturn::Request(r)) => r,
            Ok(MiddlewareReturn::Response(r)) => {
                // If a before middleware returns a response, we abort the request and return the response
                return r;
            }
            Err(e) => {
                let e = e.downcast_ref::<PyErr>().unwrap();
                error!(
                    "Error while executing before middleware function for endpoint `{}`: {}",
                    req.uri().path(),
                    get_traceback(e)
                );
                return Response::internal_server_error(None, Some(get_traceback(e)));
            }
        };
    }

    // Route execution
    let mut response = if let Some(res) = const_router.get_route(
        &HttpMethod::from_actix_method(req.method()),
        req.uri().path(),
    ) {
        res
    } else if let Some((function, route_params)) = router.get_route(
        &HttpMethod::from_actix_method(req.method()),
        req.uri().path(),
    ) {
        request.path_params = route_params;
        match execute_http_function(&request, &function).await {
            Ok(r) => r,
            Err(e) => {
                error!(
                    "Error while executing route function for endpoint `{}`: {}",
                    req.uri().path(),
                    get_traceback(&e)
                );

                Response::internal_server_error(None, Some(get_traceback(&e)))
            }
        }
    } else {
        Response::not_found(None)
    };

    debug!("OG Response : {:?}", response);

    response.headers.extend(&global_response_headers);

    match &excluded_response_headers_paths.get_ref() {
        None => {}
        Some(excluded_response_headers_paths) => {
            if excluded_response_headers_paths.contains(&req.uri().path().to_owned()) {
                response.headers.clear();
            }
        }
    }

    debug!("Extended Response : {:?}", response);

    // After middleware
    // Global
    let mut after_middlewares =
        middleware_router.get_global_middlewares(&MiddlewareType::AfterRequest);
    // Route specific
    if let Some((function, _)) =
        middleware_router.get_route(&MiddlewareType::AfterRequest, req.uri().path())
    {
        after_middlewares.push(function);
    }
    for after_middleware in after_middlewares {
        response = match execute_middleware_function(&response, &after_middleware).await {
            Ok(MiddlewareReturn::Request(_)) => {
                error!("After middleware returned a request");
                return Response::internal_server_error(
                    Some(&response.headers),
                    Some("After middleware returned a request".to_string()),
                );
            }
            Ok(MiddlewareReturn::Response(r)) => {
                let response = r;

                debug!("Response returned: {:?}", response);
                response
            }
            Err(e) => {
                let e = e.downcast_ref::<PyErr>().unwrap();
                error!(
                    "Error while executing after middleware function for endpoint `{}`: {}",
                    req.uri().path(),
                    get_traceback(e)
                );
                return Response::internal_server_error(
                    Some(&response.headers),
                    Some(get_traceback(e)),
                );
            }
        };
    }

    debug!("Response returned: {:?}", response);

    response
}

fn get_traceback(error: &PyErr) -> String {
    Python::with_gil(|py| -> String {
        if let Some(traceback) = error.traceback(py) {
            let msg = match traceback.format() {
                Ok(msg) => format!("\n{msg} {error}"),
                Err(e) => e.to_string(),
            };
            return msg;
        };

        error.value(py).to_string()
    })
}

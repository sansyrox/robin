use crate::processor::{apply_headers, execute_event_handler, handle_request};
use crate::router::Router;
use crate::shared_socket::SocketHeld;
use crate::types::{Headers, PyFunction};
use crate::web_socket_connection::start_web_socket;

use std::collections::HashMap;
use std::convert::TryInto;
use std::sync::atomic::AtomicBool;
use std::sync::atomic::Ordering::{Relaxed, SeqCst};
use std::sync::{Arc, RwLock};
use std::thread;

use actix_files::Files;
use actix_http::KeepAlive;
use actix_web::*;
use dashmap::DashMap;

// pyO3 module
use pyo3::prelude::*;

static STARTED: AtomicBool = AtomicBool::new(false);

#[derive(Clone)]
struct Directory {
    route: String,
    directory_path: String,
    index_file: Option<String>,
    show_files_listing: bool,
}

#[pyclass]
pub struct Server {
    router: Arc<Router>,
    headers: Arc<DashMap<String, String>>,
    directories: Arc<RwLock<Vec<Directory>>>,
    startup_handler: Option<PyFunction>,
    shutdown_handler: Option<PyFunction>,
}

#[pymethods]
impl Server {
    #[new]
    pub fn new() -> Self {
        Self {
            router: Arc::new(Router::new()),
            headers: Arc::new(DashMap::new()),
            directories: Arc::new(RwLock::new(Vec::new())),
            startup_handler: None,
            shutdown_handler: None,
        }
    }

    pub fn start(
        &mut self,
        py: Python,
        socket: &PyCell<SocketHeld>,
        workers: usize,
    ) -> PyResult<()> {
        if STARTED
            .compare_exchange(false, true, SeqCst, Relaxed)
            .is_err()
        {
            println!("Already running...");
            return Ok(());
        }

        let borrow = socket.try_borrow_mut()?;
        let held_socket: &SocketHeld = &*borrow;

        let raw_socket = held_socket.get_socket();

        let router = self.router.clone();
        let headers = self.headers.clone();
        let directories = self.directories.clone();
        let workers = Arc::new(workers);

        let asyncio = py.import("asyncio").unwrap();

        let event_loop = asyncio.call_method0("new_event_loop").unwrap();
        asyncio
            .call_method1("set_event_loop", (event_loop,))
            .unwrap();
        let event_loop_hdl = PyObject::from(event_loop);
        let event_loop_cleanup = PyObject::from(event_loop);
        let startup_handler = self.startup_handler.clone();
        let shutdown_handler = self.shutdown_handler.clone();

        thread::spawn(move || {
            //init_current_thread_once();
            let copied_event_loop = event_loop_hdl.clone();
            actix_web::rt::System::new().block_on(async move {
                println!("The number of workers are {}", workers.clone());
                execute_event_handler(startup_handler, copied_event_loop.clone()).await;

                HttpServer::new(move || {
                    let mut app = App::new();
                    let event_loop_hdl = copied_event_loop.clone();
                    let directories = directories.read().unwrap();
                    let router_copy = router.clone();

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
                        .app_data(web::Data::new(headers.clone()));

                    let web_socket_map = router_copy.get_web_socket_map();
                    for (elem, value) in (web_socket_map.read().unwrap()).iter() {
                        let route = elem.clone();
                        let params = value.clone();
                        let event_loop_hdl = event_loop_hdl.clone();
                        app = app.route(
                            &route.clone(),
                            web::get().to(
                                move |_router: web::Data<Arc<Router>>,
                                      _headers: web::Data<Arc<Headers>>,
                                      stream: web::Payload,
                                      req: HttpRequest| {
                                    start_web_socket(
                                        req,
                                        stream,
                                        params.clone(),
                                        event_loop_hdl.clone(),
                                    )
                                },
                            ),
                        );
                    }

                    app.default_service(web::route().to(move |router, headers, payload, req| {
                        pyo3_asyncio::tokio::scope_local(event_loop_hdl.clone(), async move {
                            index(router, headers, payload, req).await
                        })
                    }))
                })
                .keep_alive(KeepAlive::Os)
                .workers(*workers.clone())
                .client_timeout(0)
                .listen(raw_socket.try_into().unwrap())
                .unwrap()
                .run()
                .await
                .unwrap();
            });
        });

        let event_loop = event_loop.call_method0("run_forever");
        if event_loop.is_err() {
            println!("Ctrl c handler");
            Python::with_gil(|py| {
                let event_loop_hdl = event_loop_cleanup.clone();
                pyo3_asyncio::tokio::run(py, async move {
                    execute_event_handler(shutdown_handler, event_loop_hdl.clone()).await;
                    Ok(())
                })
                .unwrap();
            })
        }
        Ok(())
    }

    pub fn add_directory(
        &mut self,
        route: String,
        directory_path: String,
        index_file: Option<String>,
        show_files_listing: bool,
    ) {
        self.directories.write().unwrap().push(Directory {
            route,
            directory_path,
            index_file,
            show_files_listing,
        });
    }

    /// Adds a new header to our concurrent hashmap
    /// this can be called after the server has started.
    pub fn add_header(&self, key: &str, value: &str) {
        self.headers.insert(key.to_string(), value.to_string());
    }

    /// Removes a new header to our concurrent hashmap
    /// this can be called after the server has started.
    pub fn remove_header(&self, key: &str) {
        self.headers.remove(key);
    }

    /// Add a new route to the routing tables
    /// can be called after the server has been started
    pub fn add_route(
        &self,
        route_type: &str,
        route: &str,
        handler: Py<PyAny>,
        is_async: bool,
        number_of_params: u8,
    ) {
        println!("Route added for {} {} ", route_type, route);
        self.router
            .add_route(route_type, route, handler, is_async, number_of_params);
    }

    /// Add a new web socket route to the routing tables
    /// can be called after the server has been started
    pub fn add_web_socket_route(
        &mut self,
        route: &str,
        // handler, is_async, number of params
        connect_route: (Py<PyAny>, bool, u8),
        close_route: (Py<PyAny>, bool, u8),
        message_route: (Py<PyAny>, bool, u8),
    ) {
        self.router
            .add_websocket_route(route, connect_route, close_route, message_route);
    }

    /// Add a new startup handler
    pub fn add_startup_handler(&mut self, handler: Py<PyAny>, is_async: bool) {
        println!("Adding startup handler");
        match is_async {
            true => self.startup_handler = Some(PyFunction::CoRoutine(handler)),
            false => self.startup_handler = Some(PyFunction::SyncFunction(handler)),
        };
        println!("{:?}", self.startup_handler);
    }

    /// Add a new shutdown handler
    pub fn add_shutdown_handler(&mut self, handler: Py<PyAny>, is_async: bool) {
        println!("Adding shutdown handler");
        match is_async {
            true => self.shutdown_handler = Some(PyFunction::CoRoutine(handler)),
            false => self.shutdown_handler = Some(PyFunction::SyncFunction(handler)),
        };
        println!("{:?}", self.startup_handler);
        println!("{:?}", self.shutdown_handler);
    }
}

impl Default for Server {
    fn default() -> Self {
        Self::new()
    }
}

/// This is our service handler. It receives a Request, routes on it
/// path, and returns a Future of a Response.
async fn index(
    router: web::Data<Arc<Router>>,
    headers: web::Data<Arc<Headers>>,
    mut payload: web::Payload,
    req: HttpRequest,
) -> impl Responder {
    let mut queries = HashMap::new();

    if req.query_string().len() > 0 {
        let split = req.query_string().split("&");
        for s in split {
            let params = s.split_once("=").unwrap_or((s, ""));
            queries.insert(params.0, params.1);
        }
    }

    match router.get_route(req.method().clone(), req.uri().path()) {
        Some(((handler_function, number_of_params), route_params)) => {
            handle_request(
                handler_function,
                number_of_params,
                &headers,
                &mut payload,
                &req,
                route_params,
                queries,
            )
            .await
        }
        None => {
            let mut response = HttpResponse::Ok();
            apply_headers(&mut response, &headers);
            response.finish()
        }
    }
}

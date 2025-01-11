import asyncio
import logging
import os
import socket
from abc import ABC
from pathlib import Path
from typing import Callable, List, Optional, Union

import multiprocess as mp  # type: ignore

from robyn import status_codes
from robyn.argument_parser import Config
from robyn.authentication import AuthenticationHandler
from robyn.dependency_injection import DependencyMap
from robyn.env_populator import load_vars
from robyn.events import Events
from robyn.jsonify import jsonify
from robyn.logger import Colors, logger
from robyn.openapi import OpenAPI
from robyn.processpool import run_processes
from robyn.reloader import compile_rust_files
from robyn.responses import html, serve_file, serve_html
from robyn.robyn import FunctionInfo, Headers, HttpMethod, Request, Response, WebSocketConnector, get_version
from robyn.router import MiddlewareRouter, MiddlewareType, Router, WebSocketRouter
from robyn.types import Directory
from robyn.ws import WebSocket

__version__ = get_version()


config = Config()

if (compile_path := config.compile_rust_path) is not None:
    compile_rust_files(compile_path)
    print("Compiled rust files")


class BaseRobyn(ABC):
    """This is the python wrapper for the Robyn binaries."""

    def __init__(
        self,
        file_object: str,
        config: Config = Config(),
        openapi_file_path: Optional[str] = None,
        openapi: Optional[OpenAPI] = None,
        dependencies: DependencyMap = DependencyMap(),
    ) -> None:
        directory_path = os.path.dirname(os.path.abspath(file_object))
        self.file_path = file_object
        self.directory_path = directory_path
        self.config = config
        self.dependencies = dependencies
        self.openapi = openapi

        self.init_openapi(openapi_file_path)

        if not bool(os.environ.get("ROBYN_CLI", False)):
            # the env variables are already set when are running through the cli
            load_vars(project_root=directory_path)

        self._handle_dev_mode()

        logging.basicConfig(level=self.config.log_level)

        if self.config.log_level.lower() != "warn":
            logger.info(
                "SERVER IS RUNNING IN VERBOSE/DEBUG MODE. Set --log-level to WARN to run in production mode.",
                color=Colors.BLUE,
            )

        self.router = Router()
        self.middleware_router = MiddlewareRouter()
        self.web_socket_router = WebSocketRouter()
        self.request_headers: Headers = Headers({})
        self.response_headers: Headers = Headers({})
        self.excluded_response_headers_paths: Optional[List[str]] = None
        self.directories: List[Directory] = []
        self.event_handlers: dict = {}
        self.exception_handler: Optional[Callable] = None
        self.authentication_handler: Optional[AuthenticationHandler] = None
        self.included_routers: List[Router] = []

    def init_openapi(self, openapi_file_path: Optional[str]) -> None:
        if self.config.disable_openapi:
            return

        if self.openapi is None:
            self.openapi = OpenAPI()

        if openapi_file_path:
            self.openapi.override_openapi(Path(self.directory_path).joinpath(openapi_file_path))
        elif Path(self.directory_path).joinpath("openapi.json").exists():
            self.openapi.override_openapi(Path(self.directory_path).joinpath("openapi.json"))
        # TODO! what about when the elif fails?

    def _handle_dev_mode(self):
        cli_dev_mode = self.config.dev  # --dev
        env_dev_mode = os.getenv("ROBYN_DEV_MODE", "False").lower() == "true"  # ROBYN_DEV_MODE=True
        is_robyn = os.getenv("ROBYN_CLI", False)

        if cli_dev_mode and not is_robyn:
            raise SystemExit("Dev mode is not supported in the python wrapper. Please use the Robyn CLI. e.g. python3 -m robyn app.py --dev")

        if env_dev_mode and not is_robyn:
            logger.error("Ignoring ROBYN_DEV_MODE environment variable. Dev mode is not supported in the python wrapper.")
            raise SystemExit("Dev mode is not supported in the python wrapper. Please use the Robyn CLI. e.g. python3 -m robyn app.py")

    def add_route(
        self,
        route_type: Union[HttpMethod, str],
        endpoint: str,
        handler: Callable,
        is_const: bool = False,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: Union[List[str], None] = None,
    ):
        """
        Connect a URI to a handler

        :param route_type str: route type between GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS/TRACE
        :param endpoint str: endpoint for the route added
        :param handler function: represents the sync or async function passed as a handler for the route
        :param is_const bool: represents if the handler is a const function or not
        :param auth_required bool: represents if the route needs authentication or not
        """

        """ We will add the status code here only
        """
        injected_dependencies = self.dependencies.get_dependency_map(self)

        list_openapi_tags: List[str] = openapi_tags if openapi_tags else []

        if auth_required:
            self.middleware_router.add_auth_middleware(endpoint)(handler)

        if isinstance(route_type, str):
            http_methods = {
                "GET": HttpMethod.GET,
                "POST": HttpMethod.POST,
                "PUT": HttpMethod.PUT,
                "DELETE": HttpMethod.DELETE,
                "PATCH": HttpMethod.PATCH,
                "HEAD": HttpMethod.HEAD,
                "OPTIONS": HttpMethod.OPTIONS,
            }
            route_type = http_methods[route_type]

        add_route_response = self.router.add_route(
            route_type=route_type,
            endpoint=endpoint,
            handler=handler,
            is_const=is_const,
            auth_required=auth_required,
            openapi_name=openapi_name,
            openapi_tags=list_openapi_tags,
            exception_handler=self.exception_handler,
            injected_dependencies=injected_dependencies,
        )

        logger.info("Added route %s %s", route_type, endpoint)

        return add_route_response

    def inject(self, **kwargs):
        """
        Injects the dependencies for the route

        :param kwargs dict: the dependencies to be injected
        """
        self.dependencies.add_router_dependency(self, **kwargs)

    def inject_global(self, **kwargs):
        """
        Injects the dependencies for the global routes
        Ideally, this function should be a global function

        :param kwargs dict: the dependencies to be injected
        """
        self.dependencies.add_global_dependency(**kwargs)

    def before_request(self, endpoint: Optional[str] = None) -> Callable[..., None]:
        """
        You can use the @app.before_request decorator to call a method before routing to the specified endpoint

        :param endpoint str|None: endpoint to server the route. If None, the middleware will be applied to all the routes.
        """

        return self.middleware_router.add_middleware(MiddlewareType.BEFORE_REQUEST, endpoint)

    def after_request(self, endpoint: Optional[str] = None) -> Callable[..., None]:
        """
        You can use the @app.after_request decorator to call a method after routing to the specified endpoint

        :param endpoint str|None: endpoint to server the route. If None, the middleware will be applied to all the routes.
        """
        return self.middleware_router.add_middleware(MiddlewareType.AFTER_REQUEST, endpoint)

    def serve_directory(
        self,
        route: str,
        directory_path: str,
        index_file: Optional[str] = None,
        show_files_listing: bool = False,
    ):
        """
        Serves a directory at the given route

        :param route str: the route at which the directory is to be served
        :param directory_path str: the path of the directory to be served
        :param index_file str|None: the index file to be served
        :param show_files_listing bool: if the files listing should be shown or not
        """
        self.directories.append(Directory(route, directory_path, show_files_listing, index_file))

    def add_request_header(self, key: str, value: str) -> None:
        self.request_headers.append(key, value)

    def add_response_header(self, key: str, value: str) -> None:
        self.response_headers.append(key, value)

    def set_request_header(self, key: str, value: str) -> None:
        self.request_headers.set(key, value)

    def set_response_header(self, key: str, value: str) -> None:
        self.response_headers.set(key, value)

    def exclude_response_headers_for(self, excluded_response_headers_paths: Optional[List[str]]):
        """
        To exclude response headers from certain routes
        @param exclude_paths: the paths to exclude response headers from
        """
        self.excluded_response_headers_paths = excluded_response_headers_paths

    def add_web_socket(self, endpoint: str, ws: WebSocket) -> None:
        self.web_socket_router.add_route(endpoint, ws)

    def _add_event_handler(self, event_type: Events, handler: Callable) -> None:
        logger.info("Added event %s handler", event_type)
        if event_type not in {Events.STARTUP, Events.SHUTDOWN}:
            return

        is_async = asyncio.iscoroutinefunction(handler)
        self.event_handlers[event_type] = FunctionInfo(handler, is_async, 0, {}, {})

    def startup_handler(self, handler: Callable) -> None:
        self._add_event_handler(Events.STARTUP, handler)

    def shutdown_handler(self, handler: Callable) -> None:
        self._add_event_handler(Events.SHUTDOWN, handler)

    def is_port_in_use(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(("localhost", port)) == 0
        except Exception:
            raise Exception(f"Invalid port number: {port}")

    def _add_openapi_routes(self, auth_required: bool = False):
        if self.config.disable_openapi:
            return

        if self.openapi is None:
            logger.error("No openAPI")
            return

        self.router.prepare_routes_openapi(self.openapi, self.included_routers)

        self.add_route(
            route_type=HttpMethod.GET,
            endpoint="/openapi.json",
            handler=self.openapi.get_openapi_config,
            is_const=True,
            auth_required=auth_required,
        )
        self.add_route(
            route_type=HttpMethod.GET,
            endpoint="/docs",
            handler=self.openapi.get_openapi_docs_page,
            is_const=True,
            auth_required=auth_required,
        )
        self.exclude_response_headers_for(["/docs", "/openapi.json"])

    def exception(self, exception_handler: Callable):
        self.exception_handler = exception_handler

    def get(
        self,
        endpoint: str,
        const: bool = False,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: List[str] = ["get"],
    ):
        """
        The @app.get decorator to add a route with the GET method

        :param endpoint str: endpoint for the route added
        :param const bool: represents if the handler is a const function or not
        :param auth_required bool: represents if the route needs authentication or not
        :param openapi_name: str -- the name of the endpoint in the openapi spec
        :param openapi_tags: List[str] -- for grouping of endpoints in the openapi spec
        """

        def inner(handler):
            return self.add_route(HttpMethod.GET, endpoint, handler, const, auth_required, openapi_name, openapi_tags)

        return inner

    def post(
        self,
        endpoint: str,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: List[str] = ["post"],
    ):
        """
        The @app.post decorator to add a route with POST method

        :param endpoint str: endpoint for the route added
        :param auth_required bool: represents if the route needs authentication or not
        :param openapi_name: str -- the name of the endpoint in the openapi spec
        :param openapi_tags: List[str] -- for grouping of endpoints in the openapi spec
        """

        def inner(handler):
            return self.add_route(HttpMethod.POST, endpoint, handler, auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

        return inner

    def put(
        self,
        endpoint: str,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: List[str] = ["put"],
    ):
        """
        The @app.put decorator to add a get route with PUT method

        :param endpoint str: endpoint for the route added
        :param auth_required bool: represents if the route needs authentication or not
        :param openapi_name: str -- the name of the endpoint in the openapi spec
        :param openapi_tags: List[str] -- for grouping of endpoints in the openapi spec
        """

        def inner(handler):
            return self.add_route(HttpMethod.PUT, endpoint, handler, auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

        return inner

    def delete(
        self,
        endpoint: str,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: List[str] = ["delete"],
    ):
        """
        The @app.delete decorator to add a route with DELETE method

        :param endpoint str: endpoint for the route added
        :param auth_required bool: represents if the route needs authentication or not
        :param openapi_name: str -- the name of the endpoint in the openapi spec
        :param openapi_tags: List[str] -- for grouping of endpoints in the openapi spec
        """

        def inner(handler):
            return self.add_route(HttpMethod.DELETE, endpoint, handler, auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

        return inner

    def patch(
        self,
        endpoint: str,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: List[str] = ["patch"],
    ):
        """
        The @app.patch decorator to add a route with PATCH method

        :param endpoint str: endpoint for the route added
        :param auth_required bool: represents if the route needs authentication or not
        :param openapi_name: str -- the name of the endpoint in the openapi spec
        :param openapi_tags: List[str] -- for grouping of endpoints in the openapi spec
        """

        def inner(handler):
            return self.add_route(HttpMethod.PATCH, endpoint, handler, auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

        return inner

    def head(
        self,
        endpoint: str,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: List[str] = ["head"],
    ):
        """
        The @app.head decorator to add a route with HEAD method

        :param endpoint str: endpoint for the route added
        :param auth_required bool: represents if the route needs authentication or not
        :param openapi_name: str -- the name of the endpoint in the openapi spec
        :param openapi_tags: List[str] -- for grouping of endpoints in the openapi spec
        """

        def inner(handler):
            return self.add_route(HttpMethod.HEAD, endpoint, handler, auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

        return inner

    def options(
        self,
        endpoint: str,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: List[str] = ["options"],
    ):
        """
        The @app.options decorator to add a route with OPTIONS method

        :param endpoint str: endpoint for the route added
        :param auth_required bool: represents if the route needs authentication or not
        :param openapi_name: str -- the name of the endpoint in the openapi spec
        :param openapi_tags: List[str] -- for grouping of endpoints in the openapi spec
        """

        def inner(handler):
            return self.add_route(HttpMethod.OPTIONS, endpoint, handler, auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

        return inner

    def connect(
        self,
        endpoint: str,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: List[str] = ["connect"],
    ):
        """
        The @app.connect decorator to add a route with CONNECT method

        :param endpoint str: endpoint for the route added
        :param auth_required bool: represents if the route needs authentication or not
        :param openapi_name: str -- the name of the endpoint in the openapi spec
        :param openapi_tags: List[str] -- for grouping of endpoints in the openapi spec
        """

        def inner(handler):
            return self.add_route(HttpMethod.CONNECT, endpoint, handler, auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

        return inner

    def trace(
        self,
        endpoint: str,
        auth_required: bool = False,
        openapi_name: str = "",
        openapi_tags: List[str] = ["trace"],
    ):
        """
        The @app.trace decorator to add a route with TRACE method

        :param endpoint str: endpoint for the route added
        :param auth_required bool: represents if the route needs authentication or not
        :param openapi_name: str -- the name of the endpoint in the openapi spec
        :param openapi_tags: List[str] -- for grouping of endpoints in the openapi spec
        """

        def inner(handler):
            return self.add_route(HttpMethod.TRACE, endpoint, handler, auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

        return inner

    def include_router(self, router):
        """
        The method to include the routes from another router

        :param router Robyn: the router object to include the routes from
        """
        self.included_routers.append(router)

        self.router.routes.extend(router.router.routes)
        self.middleware_router.global_middlewares.extend(router.middleware_router.global_middlewares)
        self.middleware_router.route_middlewares.extend(router.middleware_router.route_middlewares)

        if not self.config.disable_openapi and self.openapi is not None:
            self.openapi.add_subrouter_paths(self.openapi)

        # extend the websocket routes
        prefix = router.prefix
        for route in router.web_socket_router.routes:
            new_endpoint = f"{prefix}{route}"
            self.web_socket_router.routes[new_endpoint] = router.web_socket_router.routes[route]

        self.dependencies.merge_dependencies(router)

    def configure_authentication(self, authentication_handler: AuthenticationHandler):
        """
        Configures the authentication handler for the application.

        :param authentication_handler: the instance of a class inheriting the AuthenticationHandler base class
        """
        self.authentication_handler = authentication_handler
        self.middleware_router.set_authentication_handler(authentication_handler)


class Robyn(BaseRobyn):
    def start(self, host: str = "127.0.0.1", port: int = 8080, _check_port: bool = True):
        """
        Starts the server

        :param host str: represents the host at which the server is listening
        :param port int: represents the port number at which the server is listening
        :param _check_port bool: represents if the port should be checked if it is already in use
        """

        host = os.getenv("ROBYN_HOST", host)
        port = int(os.getenv("ROBYN_PORT", port))
        open_browser = bool(os.getenv("ROBYN_BROWSER_OPEN", self.config.open_browser))

        if _check_port:
            while self.is_port_in_use(port):
                logger.error("Port %s is already in use. Please use a different port.", port)
                try:
                    port = int(input("Enter a different port: "))
                except Exception:
                    logger.error("Invalid port number. Please enter a valid port number.")
                    continue

        if not self.config.disable_openapi:
            self._add_openapi_routes()
            logger.info("Docs hosted at http://%s:%s/docs", host, port)

        logger.info("Robyn version: %s", __version__)
        logger.info("Starting server at http://%s:%s", host, port)

        mp.allow_connection_pickling()

        run_processes(
            host,
            port,
            self.directories,
            self.request_headers,
            self.router.get_routes(),
            self.middleware_router.get_global_middlewares(),
            self.middleware_router.get_route_middlewares(),
            self.web_socket_router.get_routes(),
            self.event_handlers,
            self.config.workers,
            self.config.processes,
            self.response_headers,
            self.excluded_response_headers_paths,
            open_browser,
        )


class SubRouter(BaseRobyn):
    def __init__(self, file_object: str, prefix: str = "", config: Config = Config(), openapi: OpenAPI = OpenAPI()) -> None:
        super().__init__(file_object=file_object, config=config, openapi=openapi)
        self.prefix = prefix

    def __add_prefix(self, endpoint: str):
        return f"{self.prefix}{endpoint}"

    def get(self, endpoint: str, const: bool = False, auth_required: bool = False, openapi_name: str = "", openapi_tags: List[str] = ["get"]):
        return super().get(endpoint=self.__add_prefix(endpoint), const=const, auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

    def post(self, endpoint: str, auth_required: bool = False, openapi_name: str = "", openapi_tags: List[str] = ["post"]):
        return super().post(endpoint=self.__add_prefix(endpoint), auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

    def put(self, endpoint: str, auth_required: bool = False, openapi_name: str = "", openapi_tags: List[str] = ["put"]):
        return super().put(endpoint=self.__add_prefix(endpoint), auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

    def delete(self, endpoint: str, auth_required: bool = False, openapi_name: str = "", openapi_tags: List[str] = ["delete"]):
        return super().delete(endpoint=self.__add_prefix(endpoint), auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

    def patch(self, endpoint: str, auth_required: bool = False, openapi_name: str = "", openapi_tags: List[str] = ["patch"]):
        return super().patch(endpoint=self.__add_prefix(endpoint), auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

    def head(self, endpoint: str, auth_required: bool = False, openapi_name: str = "", openapi_tags: List[str] = ["head"]):
        return super().head(endpoint=self.__add_prefix(endpoint), auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

    def trace(self, endpoint: str, auth_required: bool = False, openapi_name: str = "", openapi_tags: List[str] = ["trace"]):
        return super().trace(endpoint=self.__add_prefix(endpoint), auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)

    def options(self, endpoint: str, auth_required: bool = False, openapi_name: str = "", openapi_tags: List[str] = ["options"]):
        return super().options(endpoint=self.__add_prefix(endpoint), auth_required=auth_required, openapi_name=openapi_name, openapi_tags=openapi_tags)


def ALLOW_CORS(app: Robyn, origins: Union[List[str], str]):
    """
    Configure CORS headers for the application.

    Args:
        app: Robyn application instance
        origins: List of allowed origins or "*" for all origins
    """
    # Handle string input for origins
    if isinstance(origins, str):
        origins = [origins]

    @app.before_request()
    def cors_middleware(request):
        if request is None:
            return None

        origin = request.headers.get("Origin")

        # If specific origins are set, validate the request origin
        if origin and "*" not in origins and origin not in origins:
            return Response(status_code=403, description="", headers={})

        # Handle preflight requests
        if request.method == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin if origin else (origins[0] if origins else "*"),
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Max-Age": "3600",
                },
                description="",
            )

        return request

    # Set default CORS headers for all responses
    if len(origins) == 1:
        app.set_response_header("Access-Control-Allow-Origin", origins[0])
    else:
        # For multiple origins, we'll handle it dynamically in the response
        app.set_response_header("Access-Control-Allow-Origin", "*")

    app.set_response_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS")
    app.set_response_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    app.set_response_header("Access-Control-Allow-Credentials", "true")


__all__ = [
    "Robyn",
    "Request",
    "Response",
    "status_codes",
    "jsonify",
    "serve_file",
    "serve_html",
    "html",
    "ALLOW_CORS",
    "SubRouter",
    "AuthenticationHandler",
    "Headers",
    "WebSocketConnector",
    "WebSocket",
]

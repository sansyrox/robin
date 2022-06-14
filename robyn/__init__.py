import asyncio
import logging
import multiprocessing as mp
import os

from multiprocess import Process
from watchdog.observers import Observer
from robyn.events import Events
from .argument_parser import ArgumentParser
from .dev_event_handler import EventHandler
from .log_colors import Colors
from .processpool import spawn_process
from .responses import jsonify, static_file

from .robyn import SocketHeld
from .router import MiddlewareRouter, Router, WebSocketRouter
from .ws import WS

mp.allow_connection_pickling()

logger = logging.getLogger(__name__)


class Robyn:
    """This is the python wrapper for the Robyn binaries."""

    def __init__(self, file_object):
        directory_path = os.path.dirname(os.path.abspath(file_object))
        self.file_path = file_object
        self.directory_path = directory_path
        self.parser = ArgumentParser()
        self.dev = self.parser.is_dev
        self.processes = self.parser.num_processes
        self.workers = self.parser.workers
        self.log_level = self.parser.log_level
        self.router = Router()
        self.middleware_router = MiddlewareRouter()
        self.web_socket_router = WebSocketRouter()
        self.headers = []
        self.directories = []
        self.event_handlers = {}

        self._config_logger()

    def _add_route(self, route_type, endpoint, handler, const=False):
        """
        [This is base handler for all the decorators]

        :param route_type [str]: [route type between GET/POST/PUT/DELETE/PATCH]
        :param endpoint [str]: [endpoint for the route added]
        :param handler [function]: [represents the sync or async function passed as a handler for the route]
        """

        """ We will add the status code here only
        """
        self.router.add_route(route_type, endpoint, handler, const)

    def before_request(self, endpoint):
        """
        The @app.before_request decorator to add a get route

        :param endpoint str: endpoint to server the route
        """

        return self.middleware_router.add_before_request(endpoint)

    def after_request(self, endpoint):
        """
        The @app.after_request decorator to add a get route

        :param endpoint str: endpoint to server the route
        """

        return self.middleware_router.add_after_request(endpoint)

    def add_directory(
        self, route, directory_path, index_file=None, show_files_listing=False
    ):
        self.directories.append((route, directory_path, index_file, show_files_listing))

    def add_header(self, key, value):
        self.headers.append((key, value))

    def add_web_socket(self, endpoint, ws):
        self.web_socket_router.add_route(endpoint, ws)

    def _add_event_handler(self, event_type: str, handler):
        logger.debug(f"Add event {event_type} handler")
        if event_type not in {Events.STARTUP, Events.SHUTDOWN}:
            return

        is_async = asyncio.iscoroutinefunction(handler)
        self.event_handlers[event_type] = (handler, is_async)

    def startup_handler(self, handler):
        self._add_event_handler(Events.STARTUP, handler)

    def shutdown_handler(self, handler):
        self._add_event_handler(Events.SHUTDOWN, handler)

    def start(self, url="127.0.0.1", port=5000):
        """
        Starts the server

        :param port int: reperesents the port number at which the server is listening
        """

        if not self.dev:
            processes = []
            workers = self.workers
            socket = SocketHeld(url, port)
            for _ in range(self.processes):
                copied_socket = socket.try_clone()
                p = Process(
                    target=spawn_process,
                    args=(
                        self.directories,
                        self.headers,
                        self.router.get_routes(),
                        self.middleware_router.get_routes(),
                        self.web_socket_router.get_routes(),
                        self.event_handlers,
                        copied_socket,
                        workers,
                    ),
                )
                p.start()
                processes.append(p)

            logger.info(f"{Colors.HEADER}Starting up \n{Colors.ENDC}")
            logger.info(f"{Colors.OKGREEN}Press Ctrl + C to stop \n{Colors.ENDC}")
            try:
                for process in processes:
                    process.join()
            except KeyboardInterrupt:
                logger.info(f"{Colors.BOLD}{Colors.OKGREEN} Terminating server!! {Colors.ENDC}")
                for process in processes:
                    process.kill()
        else:
            event_handler = EventHandler(self.file_path)
            event_handler.start_server_first_time()
            logger.info(
                f"{Colors.OKBLUE}Dev server initialised with the directory_path : {self.directory_path}{Colors.ENDC}"
            )
            observer = Observer()
            observer.schedule(event_handler, path=self.directory_path, recursive=True)
            observer.start()
            try:
                while True:
                    pass
            finally:
                observer.stop()
                observer.join()

    def get(self, endpoint, const=False):
        """
        The @app.get decorator to add a get route

        :param endpoint str: endpoint to server the route
        """

        def inner(handler):
            self._add_route("GET", endpoint, handler, const)

        return inner

    def post(self, endpoint):
        """
        The @app.post decorator to add a get route

        :param endpoint str: endpoint to server the route
        """

        def inner(handler):
            self._add_route("POST", endpoint, handler)

        return inner

    def put(self, endpoint):
        """
        The @app.put decorator to add a get route

        :param endpoint str: endpoint to server the route
        """
        def inner(handler):
            self._add_route("PUT", endpoint, handler)

        return inner

    def delete(self, endpoint):
        """
        The @app.delete decorator to add a get route

        :param endpoint str: endpoint to server the route
        """

        def inner(handler):
            self._add_route("DELETE", endpoint, handler)

        return inner

    def patch(self, endpoint):
        """
        [The @app.patch decorator to add a get route]

        :param endpoint [str]: [endpoint to server the route]
        """

        def inner(handler):
            self._add_route("PATCH", endpoint, handler)

        return inner

    def head(self, endpoint):
        """
        The @app.head decorator to add a get route

        :param endpoint str: endpoint to server the route
        """

        def inner(handler):
            self._add_route("HEAD", endpoint, handler)

        return inner

    def options(self, endpoint):
        """
        The @app.options decorator to add a get route

        :param endpoint str: endpoint to server the route
        """

        def inner(handler):
            self._add_route("OPTIONS", endpoint, handler)

        return inner

    def connect(self, endpoint):
        """
        The @app.connect decorator to add a get route

        :param endpoint str: endpoint to server the route
        """

        def inner(handler):
            self._add_route("CONNECT", endpoint, handler)

        return inner

    def trace(self, endpoint):
        """
        The @app.trace decorator to add a get route

        :param endpoint str: endpoint to server the route
        """

        def inner(handler):
            self._add_route("TRACE", endpoint, handler)

        return inner

    def _config_logger(self):
        """
        This is the method to configure the logger either on the dev mode or the env variable
        """

        log_level = "WARN"

        if self.dev:
            log_level = "DEBUG"

        log_level = self.log_level if self.log_level else log_level
        logging.basicConfig(level=log_level)


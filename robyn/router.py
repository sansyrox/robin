import inspect
import logging
from abc import ABC, abstractmethod
from asyncio import iscoroutinefunction
from functools import wraps
from inspect import signature
from types import CoroutineType
from typing import Callable, Dict, List, NamedTuple, Optional, Union

from robyn import status_codes
from robyn.authentication import AuthenticationHandler, AuthenticationNotConfiguredError
from robyn.dependency_injection import DependencyMap
from robyn.jsonify import jsonify
from robyn.responses import FileResponse
from robyn.robyn import FunctionInfo, Headers, HttpMethod, Identity, MiddlewareType, QueryParams, Request, Response, Url
from robyn.types import Body, Files, FormData, IPAddress, Method, PathParams
from robyn.ws import WebSocket

_logger = logging.getLogger(__name__)


class Route(NamedTuple):
    route_type: HttpMethod
    route: str
    function: FunctionInfo
    is_const: bool


class RouteMiddleware(NamedTuple):
    middleware_type: MiddlewareType
    route: str
    function: FunctionInfo


class GlobalMiddleware(NamedTuple):
    middleware_type: MiddlewareType
    function: FunctionInfo


class BaseRouter(ABC):
    @abstractmethod
    def add_route(*args) -> Union[Callable, CoroutineType, WebSocket]: ...


class Router(BaseRouter):
    def __init__(self) -> None:
        super().__init__()
        self.routes: List[Route] = []

    def _format_tuple_response(self, res: tuple) -> Response:
        if len(res) != 3:
            raise ValueError("Tuple should have 3 elements")

        description, headers, status_code = res
        description = self._format_response(description).description
        new_headers: Headers = Headers(headers)
        if new_headers.contains("Content-Type"):
            headers.set("Content-Type", new_headers.get("Content-Type"))

        return Response(
            status_code=status_code,
            headers=headers,
            description=description,
        )

    def _format_response(
        self,
        res: Union[Dict, Response, bytes, tuple, str],
    ) -> Response:
        if isinstance(res, Response):
            return res

        if isinstance(res, dict):
            return Response(
                status_code=status_codes.HTTP_200_OK,
                headers=Headers({"Content-Type": "application/json"}),
                description=jsonify(res),
            )

        if isinstance(res, FileResponse):
            response: Response = Response(
                status_code=res.status_code,
                headers=res.headers,
                description=res.file_path,
            )
            response.file_path = res.file_path
            return response

        if isinstance(res, bytes):
            return Response(
                status_code=status_codes.HTTP_200_OK,
                headers=Headers({"Content-Type": "application/octet-stream"}),
                description=res,
            )

        if isinstance(res, tuple):
            return self._format_tuple_response(tuple(res))

        return Response(
            status_code=status_codes.HTTP_200_OK,
            headers=Headers({"Content-Type": "text/plain"}),
            description=str(res).encode("utf-8"),
        )

    def add_route(  # type: ignore
        self,
        route_type: HttpMethod,
        endpoint: str,
        handler: Callable,
        is_const: bool,
        exception_handler: Optional[Callable],
        injected_dependencies: dict,
    ) -> Union[Callable, CoroutineType]:
        def wrapped_handler(*args, **kwargs):
            # In the execute functions the request is passed into *args
            request = next(filter(lambda it: isinstance(it, Request), args), None)

            handler_params = signature(handler).parameters

            if not request or (len(handler_params) == 1 and next(iter(handler_params)) is Request):
                return handler(*args, **kwargs)

            type_mapping = {
                "request": Request,
                "query_params": QueryParams,
                "headers": Headers,
                "path_params": PathParams,
                "body": Body,
                "method": Method,
                "url": Url,
                "form_data": FormData,
                "files": Files,
                "ip_addr": IPAddress,
                "identity": Identity,
            }

            type_filtered_params = {}

            for handler_param in iter(handler_params):
                for type_name in type_mapping:
                    handler_param_type = handler_params[handler_param].annotation
                    handler_param_name = handler_params[handler_param].name
                    if handler_param_type is Request:
                        type_filtered_params[handler_param_name] = request
                    elif handler_param_type is type_mapping[type_name]:
                        type_filtered_params[handler_param_name] = getattr(request, type_name)
                    elif inspect.isclass(handler_param_type):
                        if issubclass(handler_param_type, Body):
                            type_filtered_params[handler_param_name] = getattr(request, "body")
                        elif issubclass(handler_param_type, QueryParams):
                            type_filtered_params[handler_param_name] = getattr(request, "query_params")

            request_components = {
                "r": request,
                "req": request,
                "request": request,
                "query_params": request.query_params,
                "headers": request.headers,
                "path_params": request.path_params,
                "body": request.body,
                "method": request.method,
                "url": request.url,
                "ip_addr": request.ip_addr,
                "identity": request.identity,
                "form_data": request.form_data,
                "files": request.files,
                "router_dependencies": injected_dependencies["router_dependencies"],
                "global_dependencies": injected_dependencies["global_dependencies"],
                **kwargs,
            }

            name_filtered_params = {k: v for k, v in request_components.items() if k in handler_params and k not in type_filtered_params}

            filtered_params = dict(**type_filtered_params, **name_filtered_params)

            if len(filtered_params) != len(handler_params):
                invalid_args = set(handler_params) - set(filtered_params)
                raise SyntaxError(f"Unexpected request params found: {invalid_args}")

            return handler(**filtered_params)

        @wraps(handler)
        async def async_inner_handler(*args, **kwargs):
            try:
                response = self._format_response(
                    await wrapped_handler(*args, **kwargs),
                )
            except Exception as err:
                if exception_handler is None:
                    raise
                response = self._format_response(
                    exception_handler(err),
                )
            return response

        @wraps(handler)
        def inner_handler(*args, **kwargs):
            try:
                response = self._format_response(
                    wrapped_handler(*args, **kwargs),
                )
            except Exception as err:
                if exception_handler is None:
                    raise
                response = self._format_response(
                    exception_handler(err),
                )
            return response

        number_of_params = len(signature(handler).parameters)
        # these are the arguments
        params = dict(inspect.signature(handler).parameters)

        new_injected_dependencies = {}
        for dependency in injected_dependencies:
            if dependency in params:
                new_injected_dependencies[dependency] = injected_dependencies[dependency]
            else:
                _logger.debug(f"Dependency {dependency} is not used in the handler {handler.__name__}")

        if iscoroutinefunction(handler):
            function = FunctionInfo(
                async_inner_handler,
                True,
                number_of_params,
                params,
                new_injected_dependencies,
            )
            self.routes.append(Route(route_type, endpoint, function, is_const))
            return async_inner_handler
        else:
            function = FunctionInfo(
                inner_handler,
                False,
                number_of_params,
                params,
                new_injected_dependencies,
            )
            self.routes.append(Route(route_type, endpoint, function, is_const))
            return inner_handler

    def get_routes(self) -> List[Route]:
        return self.routes


class MiddlewareRouter(BaseRouter):
    def __init__(self, dependencies: DependencyMap = DependencyMap()) -> None:
        super().__init__()
        self.global_middlewares: List[GlobalMiddleware] = []
        self.route_middlewares: List[RouteMiddleware] = []
        self.authentication_handler: Optional[AuthenticationHandler] = None
        self.dependencies = dependencies

    def set_authentication_handler(self, authentication_handler: AuthenticationHandler):
        self.authentication_handler = authentication_handler

    def add_route(  # type: ignore
        self,
        middleware_type: MiddlewareType,
        endpoint: str,
        handler: Callable,
        injected_dependencies: dict,
    ) -> Callable:
        params = dict(inspect.signature(handler).parameters)
        number_of_params = len(params)

        new_injected_dependencies = {}
        for dependency in injected_dependencies:
            if dependency in params:
                new_injected_dependencies[dependency] = injected_dependencies[dependency]
            else:
                _logger.debug(f"Dependency {dependency} is not used in the middleware handler {handler.__name__}")

        function = FunctionInfo(
            handler,
            iscoroutinefunction(handler),
            number_of_params,
            params,
            new_injected_dependencies,
        )
        self.route_middlewares.append(RouteMiddleware(middleware_type, endpoint, function))
        return handler

    def add_auth_middleware(self, endpoint: str):
        """
        This method adds an authentication middleware to the specified endpoint.
        """

        injected_dependencies: dict = {}

        def decorator(handler):
            if inspect.iscoroutinefunction(self.authentication_handler.authenticate):

                @wraps(handler)
                async def inner_handler(request: Request, *args):
                    if not self.authentication_handler:
                        raise AuthenticationNotConfiguredError()

                    identity = await self.authentication_handler.authenticate(request)
                    if identity is None:
                        return self.authentication_handler.unauthorized_response
                    request.identity = identity

                    return request
            else:

                @wraps(handler)
                def inner_handler(request: Request, *args):
                    if not self.authentication_handler:
                        raise AuthenticationNotConfiguredError()

                    identity = self.authentication_handler.authenticate(request)
                    if identity is None:
                        return self.authentication_handler.unauthorized_response
                    request.identity = identity

                    return request

            self.add_route(
                MiddlewareType.BEFORE_REQUEST,
                endpoint,
                inner_handler,
                injected_dependencies,
            )
            return inner_handler

        return decorator

    # These inner functions are basically a wrapper around the closure(decorator) being returned.
    # They take a handler, convert it into a closure and return the arguments.
    # Arguments are returned as they could be modified by the middlewares.
    def add_middleware(self, middleware_type: MiddlewareType, endpoint: Optional[str]) -> Callable[..., None]:
        # no dependency injection here
        injected_dependencies: dict = {}

        def inner(handler):
            @wraps(handler)
            async def async_inner_handler(*args, **kwargs):
                return await handler(*args, **kwargs)

            @wraps(handler)
            def inner_handler(*args, **kwargs):
                return handler(*args, **kwargs)

            if endpoint is not None:
                if iscoroutinefunction(handler):
                    self.add_route(
                        middleware_type,
                        endpoint,
                        async_inner_handler,
                        injected_dependencies,
                    )
                else:
                    self.add_route(middleware_type, endpoint, inner_handler, injected_dependencies)
            else:
                params = dict(inspect.signature(handler).parameters)

                if iscoroutinefunction(handler):
                    self.global_middlewares.append(
                        GlobalMiddleware(
                            middleware_type,
                            FunctionInfo(
                                async_inner_handler,
                                True,
                                len(params),
                                params,
                                injected_dependencies,
                            ),
                        )
                    )
                else:
                    self.global_middlewares.append(
                        GlobalMiddleware(
                            middleware_type,
                            FunctionInfo(
                                inner_handler,
                                False,
                                len(params),
                                params,
                                injected_dependencies,
                            ),
                        )
                    )

        return inner

    def get_route_middlewares(self) -> List[RouteMiddleware]:
        return self.route_middlewares

    def get_global_middlewares(self) -> List[GlobalMiddleware]:
        return self.global_middlewares


class WebSocketRouter(BaseRouter):
    def __init__(self) -> None:
        super().__init__()
        self.routes: dict = {}

    def add_route(self, endpoint: str, web_socket: WebSocket) -> None:  # type: ignore
        self.routes[endpoint] = web_socket

    def get_routes(self) -> Dict[str, WebSocket]:
        return self.routes

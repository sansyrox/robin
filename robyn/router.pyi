from abc import ABC, abstractmethod
from robyn.ws import WS
from typing import Callable, List, Tuple

Routes = List[Tuple[str, str, Callable, bool, int]]


class BaseRouter(ABC):
    @abstractmethod
    def add_route(*args) -> None:
        pass


class Router(BaseRouter):
    def __init__(self) -> None:
        pass

    def add_route(self, route_type: str, endpoint: str, handler: Callable) -> None:
        pass

    def get_routes(self) -> list:
        pass


class MiddlewareRouter(BaseRouter):
    def __init__(self) -> None:
        pass

    def add_route(self, route_type: str, endpoint: str, handler: Callable) -> None:
        pass

    def add_after_request(self, endpoint: str) -> Callable[..., None]:
        pass

    def add_before_request(self, endpoint: str) -> Callable[..., None]:
        pass

    def get_routes(self) -> list:
        pass


class WebSocketRouter(BaseRouter):
    def __init__(self) -> None:
        pass

    def add_route(self, endpoint: str, web_socket: WS) -> None:
        pass

    def get_routes(self) -> dict[str, WS]:
        pass

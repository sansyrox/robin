from abc import ABC, abstractmethod
from typing import Callable, List, Union

from jinja2 import Environment, FileSystemLoader

from robyn import Robyn, status_codes
from robyn.router import Route

from .robyn import Headers, Response


def get_param_filled_url(url: str, kwdict: Union[dict, None] = None) -> str:
    """fill the :params in the url

    Args:
        url (str): typically comes from the route
        kwdict (dict): the **kwargs as a dict

    Returns:
        str: _description_modified url (if there are elements in kwdict, otherwise unchanged)
    """
    if kwdict is not None:
        for k, v in zip(kwdict.keys(), kwdict.values()):
            url = url.replace(f":{k}", f"{v}")

    return url


class TemplateInterface(ABC):
    def __init__(self): ...

    @abstractmethod
    def render_template(self, *args, **kwargs) -> Response: ...

    @abstractmethod
    def set_robyn(self, robyn: Robyn) -> None: ...

    @abstractmethod
    def get_function_url(self, function_name: str, route_type: str = "GET", **kwargs) -> str: ...


class JinjaTemplate(TemplateInterface):
    def __init__(self, directory, encoding="utf-8", followlinks=False) -> None:
        self.env: Environment = Environment(loader=FileSystemLoader(searchpath=directory, encoding=encoding, followlinks=followlinks))
        self.add_function_to_globals("get_function_url", self.get_function_url)
        self.robyn: Union[Robyn, None] = None

    def add_function_to_globals(self, name: str, func: Callable):
        """
        Add a global function to a Jinja environment.
        """
        self.env.globals[name] = func

    def set_robyn(self, robyn: Robyn) -> None:
        """
        The get_function_url needs to have access to the list of routes stored in the apps Robyn object

        Args:
            robyn (Robyn): The top instance of the Robyn class for this app.
        """
        self.robyn = robyn

    def get_function_url(self, function_name: str, route_type: str = "GET", **kwargs) -> str:
        """Creates a link to an endpoint function name

        Returns:
            str: the url for the function
        """

        if self.robyn is None:
            return "get_function_url needs set_robyn"

        routes: List[Route] = self.robyn.router.get_routes()
        for r in routes:
            if r.function.handler.__name__ == function_name and str(r.route_type) == f"HttpMethod.{route_type}":
                if len(kwargs) > 0:
                    return get_param_filled_url(r.route, kwargs)
                return r.route

        return "route not found in Robyn router"

    def render_template(self, template_name, **kwargs) -> Response:
        rendered_template = self.env.get_template(template_name).render(**kwargs)
        return Response(
            status_code=status_codes.HTTP_200_OK,
            description=rendered_template,
            headers=Headers({"Content-Type": "text/html; charset=utf-8"}),
        )


__all__ = ["TemplateInterface", "JinjaTemplate"]

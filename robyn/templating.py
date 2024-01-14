from abc import ABC, abstractmethod
from typing import Callable

from robyn import status_codes

from .robyn import Headers, Response

from jinja2 import Environment, FileSystemLoader


class TemplateInterface(ABC):
    def __init__(self):
        ...

    @abstractmethod
    def render_template(self, *args, **kwargs) -> Response:
        ...


class JinjaTemplate(TemplateInterface):
    def __init__(self, directory, encoding="utf-8", followlinks=False):
        self.env = Environment(loader=FileSystemLoader(searchpath=directory, encoding=encoding, followlinks=followlinks))

    def render_template(self, template_name, **kwargs) -> Response:
        rendered_template = self.env.get_template(template_name).render(**kwargs)
        return Response(
            status_code=status_codes.HTTP_200_OK,
            description=rendered_template,
            headers=Headers({"Content-Type": "text/html; charset=utf-8"}),
        )

    def add_template_global(self, func: Callable, name: str | None = None):
        if not callable(func):
            raise TypeError("Must be callable.")
        self.env.globals[name or func.__name__] = func


__all__ = ["TemplateInterface", "JinjaTemplate"]

import inspect
import json
import typing
from dataclasses import asdict, dataclass, field
from importlib import resources
from inspect import Signature
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict, Union

from robyn.responses import html
from robyn.robyn import QueryParams, Response
from robyn.types import Body


class str_typed_dict(TypedDict):
    key: str
    value: str


@dataclass
class Contact:
    """
    The contact information for the exposed API.
    (https://swagger.io/specification/#contact-object)

    @param name: Optional[str] The identifying name of the contact person/organization.
    @param url: Optional[str] The URL pointing to the contact information. This MUST be in the form of a URL.
    @param email: Optional[str] The email address of the contact person/organization. This MUST be in the form of an email address.
    """

    name: Optional[str] = None
    url: Optional[str] = None
    email: Optional[str] = None


@dataclass
class License:
    """
    The license information for the exposed API.
    (https://swagger.io/specification/#license-object)

    @param name: Optional[str] The license name used for the API.
    @param url: Optional[str] A URL to the license used for the API. This MUST be in the form of a URL.
    """

    name: Optional[str] = None
    url: Optional[str] = None


@dataclass
class Server:
    """
    An array of Server Objects, which provide connectivity information to a target server. If the servers property is
    not provided, or is an empty array, the default value would be a Server Object with a url value of /.
    (https://swagger.io/specification/#server-object)

    @param url: str A URL to the target host. This URL supports Server Variables and MAY be relative,
    to indicate that the host location is relative to the location where the OpenAPI document is being served.
    Variable substitutions will be made when a variable is named in {brackets}.
    @param description: Optional[str] An optional string describing the host designated by the URL.
    """

    url: str
    description: Optional[str] = None


@dataclass
class ExternalDocumentation:
    """
    Additional external documentation for this operation.
    (https://swagger.io/specification/#external-documentation-object)

    @param description: Optional[str] A description of the target documentation.
    @param url: Optional[str] The URL for the target documentation.
    """

    description: Optional[str] = None
    url: Optional[str] = None


@dataclass
class Components:
    """
    Additional external documentation for this operation.
    (https://swagger.io/specification/#components-object)

    @param schemas: Optional[Dict[str, Dict]] An object to hold reusable Schema Objects.
    @param responses: Optional[Dict[str, Dict]] An object to hold reusable Response Objects.
    @param parameters: Optional[Dict[str, Dict]] An object to hold reusable Parameter Objects.
    @param examples: Optional[Dict[str, Dict]] An object to hold reusable Example Objects.
    @param requestBodies: Optional[Dict[str, Dict]] An object to hold reusable Request Body Objects.
    @param securitySchemes: Optional[Dict[str, Dict]] An object to hold reusable Security Scheme Objects.
    @param links: Optional[Dict[str, Dict]] An object to hold reusable Link Objects.
    @param callbacks: Optional[Dict[str, Dict]] An object to hold reusable Callback Objects.
    @param pathItems: Optional[Dict[str, Dict]] An object to hold reusable Callback Objects.
    """

    schemas: Optional[Dict[str, Dict]] = field(default_factory=dict)
    responses: Optional[Dict[str, Dict]] = field(default_factory=dict)
    parameters: Optional[Dict[str, Dict]] = field(default_factory=dict)
    examples: Optional[Dict[str, Dict]] = field(default_factory=dict)
    requestBodies: Optional[Dict[str, Dict]] = field(default_factory=dict)
    securitySchemes: Optional[Dict[str, Dict]] = field(default_factory=dict)
    links: Optional[Dict[str, Dict]] = field(default_factory=dict)
    callbacks: Optional[Dict[str, Dict]] = field(default_factory=dict)
    pathItems: Optional[Dict[str, Dict]] = field(default_factory=dict)


@dataclass
class OpenAPIInfo:
    """
    Provides metadata about the API. The metadata MAY be used by tooling as required.
    (https://swagger.io/specification/#info-object)

    @param title: str The title of the API.
    @param version: str The version of the API.
    @param description: Optional[str] A description of the API.
    @param termsOfService: Optional[str] A URL to the Terms of Service for the API.
    @param contact: Contact The contact information for the exposed API.
    @param license: License The license information for the exposed API.
    @param servers: list[Server] An list of Server objects representing the servers.
    @param externalDocs: Optional[ExternalDocumentation] Additional external documentation.
    @param components: Components An element to hold various schemas for the document.
    """

    title: str = "Robyn API"
    version: str = "1.0.0"
    description: Optional[str] = None
    termsOfService: Optional[str] = None
    contact: Contact = field(default_factory=Contact)
    license: License = field(default_factory=License)
    servers: List[Server] = field(default_factory=list)
    externalDocs: Optional[ExternalDocumentation] = field(default_factory=ExternalDocumentation)
    components: Components = field(default_factory=Components)


@dataclass
class OpenAPI:
    """
    This is the root object of the OpenAPI document.

    @param info: OpenAPIInfo Provides metadata about the API.
    @param openapi_spec: dict The content of openapi.json as a dict
    """

    info: OpenAPIInfo = field(default_factory=OpenAPIInfo)
    openapi_spec: dict = field(init=False)
    openapi_file_override: bool = False  # denotes whether there is an override or not.

    def __post_init__(self):
        """
        Initializes the openapi_spec dict
        """
        if self.openapi_file_override:
            return

        self.openapi_spec = {
            "openapi": "3.1.0",
            "info": asdict(self.info),
            "paths": {},
            "components": asdict(self.info.components),
            "servers": [asdict(server) for server in self.info.servers],
            "externalDocs": asdict(self.info.externalDocs) if self.info.externalDocs.url else None,
        }

    def add_openapi_path_obj(self, route_type: str, endpoint: str, openapi_name: str, openapi_tags: List[str], handler: Callable):
        """
        Adds the given path to openapi spec

        @param route_type: str the http method as string (get, post ...)
        @param endpoint: str the endpoint to be added
        @param openapi_name: str the name of the endpoint
        @param openapi_tags: List[str] for grouping of endpoints
        @param handler: Callable the handler function for the endpoint
        """

        if self.openapi_file_override:
            return

        query_params = None
        request_body = None
        return_annotation = None

        signature = inspect.signature(handler)
        openapi_description = inspect.getdoc(handler) or ""

        if signature:
            parameters = signature.parameters

            if "query_params" in parameters:
                query_params = parameters["query_params"].default

                if query_params is Signature.empty:
                    query_params = None

            if "body" in parameters:
                request_body = parameters["body"].default

                if request_body is Signature.empty:
                    request_body = None

            # priority to typing
            for parameter in parameters:
                param_annotation = parameters[parameter].annotation

                if inspect.isclass(param_annotation):
                    if issubclass(param_annotation, Body):
                        request_body = param_annotation
                    elif issubclass(param_annotation, QueryParams):
                        query_params = param_annotation

            if signature.return_annotation is not Signature.empty:
                return_annotation = signature.return_annotation

        modified_endpoint, path_obj = self.get_path_obj(
            endpoint, openapi_name, openapi_description, openapi_tags, query_params, request_body, return_annotation
        )

        if modified_endpoint not in self.openapi_spec["paths"]:
            self.openapi_spec["paths"][modified_endpoint] = {}
        self.openapi_spec["paths"][modified_endpoint][route_type] = path_obj

    def add_subrouter_paths(self, subrouter_openapi: "OpenAPI"):
        """
        Adds the subrouter paths to main router's openapi specs

        @param subrouter_openapi: OpenAPI the OpenAPI object of the current subrouter
        """

        if self.openapi_file_override:
            return

        paths = subrouter_openapi.openapi_spec["paths"]

        for path in paths:
            self.openapi_spec["paths"][path] = paths[path]

    def get_path_obj(
        self,
        endpoint: str,
        name: str,
        description: str,
        tags: List[str],
        query_params: Optional[str_typed_dict],
        request_body: Optional[str_typed_dict],
        return_annotation: Optional[str_typed_dict],
    ) -> Tuple[str, dict]:
        """
        Get the "path" openapi object according to spec

        @param endpoint: str the endpoint to be added
        @param name: str the name of the endpoint
        @param description: Optional[str] short description of the endpoint (to be fetched from the endpoint definition by default)
        @param tags: List[str] for grouping of endpoints
        @param query_params: Optional[TypedDict] query params for the function
        @param request_body: Optional[TypedDict] request body for the function
        @param return_annotation: Optional[TypedDict] return type of the endpoint handler

        @return: (str, dict) a tuple containing the endpoint with path params wrapped in braces and the "path" openapi object
        according to spec
        """

        if not description:
            description = "No description provided"

        openapi_path_object: dict = {
            "summary": name,
            "description": description,
            "parameters": [],
            "tags": tags,
        }

        # robyn has paths like /:url/:etc whereas openapi requires path like /{url}/{path}
        # this function is used for converting path params to the required form
        # initialized with endpoint for handling endpoints without path params
        endpoint_with_path_params_wrapped_in_braces = endpoint

        endpoint_path_params_split = endpoint.split(":")

        if len(endpoint_path_params_split) > 1:
            endpoint_without_path_params = endpoint_path_params_split[0]

            endpoint_with_path_params_wrapped_in_braces = (
                endpoint_without_path_params[:-1] if endpoint_without_path_params.endswith("/") else endpoint_without_path_params
            )

            for path_param in endpoint_path_params_split[1:]:
                path_param_name = path_param[:-1] if path_param.endswith("/") else path_param

                openapi_path_object["parameters"].append(
                    {
                        "name": path_param_name,
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                )
                endpoint_with_path_params_wrapped_in_braces += "/{" + path_param_name + "}"

        if query_params:
            query_param_annotations = query_params.__annotations__ if query_params is str_typed_dict else typing.get_type_hints(query_params)

            for query_param in query_param_annotations:
                query_param_type = self.get_openapi_type(query_param_annotations[query_param])

                openapi_path_object["parameters"].append(
                    {
                        "name": query_param,
                        "in": "query",
                        "required": False,
                        "schema": {"type": query_param_type},
                    }
                )

        if request_body:
            properties = {}

            request_body_annotations = request_body.__annotations__ if request_body is TypedDict else typing.get_type_hints(request_body)

            for body_item in request_body_annotations:
                properties[body_item] = self.get_schema_object(body_item, request_body_annotations[body_item])

            request_body_object = {
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": properties,
                        }
                    }
                }
            }

            openapi_path_object["requestBody"] = request_body_object

        response_schema: dict = {}
        response_type = "text/plain"

        if return_annotation and return_annotation is not Response:
            response_type = "application/json"
            response_schema = self.get_schema_object("response object", return_annotation)

        openapi_path_object["responses"] = {"200": {"description": "Successful Response", "content": {response_type: {"schema": response_schema}}}}

        return endpoint_with_path_params_wrapped_in_braces, openapi_path_object

    def get_openapi_type(self, typed_dict: str_typed_dict) -> str:
        """
        Get actual type from the TypedDict annotations

        @param typed_dict: TypedDict The TypedDict to be converted
        @return: str the type inferred
        """
        type_mapping = {
            int: "integer",
            str: "string",
            bool: "boolean",
            float: "number",
            dict: "object",
            list: "array",
        }

        for type_name in type_mapping:
            if typed_dict is type_name:
                return type_mapping[type_name]

        # default to "string" if type is not found
        return "string"

    def get_schema_object(self, parameter: str, param_type: Any) -> dict:
        """
        Get the schema object for request/response body

        @param parameter: name of the parameter
        @param param_type: Any the type to be inferred
        @return: dict the properties object
        """

        properties: dict = {
            "title": parameter.capitalize(),
        }

        type_mapping: dict = {
            int: "integer",
            str: "string",
            bool: "boolean",
            float: "number",
            dict: "object",
            list: "array",
        }

        # Handle basic types
        for type_name in type_mapping:
            if param_type is type_name:
                properties["type"] = type_mapping[type_name]
                return properties

        # Handle typing module types (Optional, List, etc)
        if hasattr(param_type, "__module__") and param_type.__module__ == "typing":
            origin = typing.get_origin(param_type)
            args = typing.get_args(param_type)

            # Handle Optional types
            if origin is Union and type(None) in args:
                non_none_type = next(t for t in args if t is not type(None))
                properties["anyOf"] = [{"type": self.get_openapi_type(non_none_type)}, {"type": "null"}]
                return properties

            # Handle List types
            elif origin in (list, List):
                properties["type"] = "array"
                if args:
                    item_type = args[0]
                    properties["items"] = self.get_schema_object("item", item_type)
                return properties

        # Handle custom classes and TypedDicts
        elif inspect.isclass(param_type):
            properties["type"] = "object"
            properties["properties"] = {}

            if hasattr(param_type, "__annotations__"):
                for e in param_type.__annotations__:
                    properties["properties"][e] = self.get_schema_object(e, param_type.__annotations__[e])

        return properties

    def override_openapi(self, openapi_json_spec_path: Path):
        """
        Set a pre-configured OpenAPI spec
        @param openapi_json_spec_path: str the path to the json file
        """
        with open(openapi_json_spec_path) as json_file:
            json_file_content = json.load(json_file)
            self.openapi_spec = dict(json_file_content)
            self.openapi_file_override = True

    def get_openapi_docs_page(self) -> Response:
        """
        Handler to the swagger html page to be deployed to the endpoint `/docs`
        @return: FileResponse the swagger html page
        """
        with resources.open_text("robyn", "swagger.html") as path:
            html_file = path.read()
        return html(html_file)

    def get_openapi_config(self) -> dict:
        """
        Returns the openapi spec as a dict
        @return: dict the openapi spec
        """
        return self.openapi_spec

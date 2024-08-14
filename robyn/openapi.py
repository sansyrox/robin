import re
from dataclasses import asdict, dataclass, field
from inspect import Signature
from pathlib import Path
from typing import Optional, TypedDict

from robyn.responses import FileResponse, serve_html


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
    @param servers: List[Server] An list of Server objects representing the servers.
    @param externalDocs: Optional[ExternalDocumentation] Additional external documentation.
    @param components: Components An element to hold various schemas for the document.
    """

    title: str = "Robyn API"
    version: str = "1.0.0"
    description: Optional[str] = None
    termsOfService: Optional[str] = None
    contact: Contact = field(default_factory=Contact)
    license: License = field(default_factory=License)
    servers: list[Server] = field(default_factory=list)
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

    def __post_init__(self):
        """
        Initializes the openapi_spec dict
        """
        self.openapi_spec = {
            "openapi": "3.0.0",
            "info": asdict(self.info),
            "paths": {},
            "components": asdict(self.info.components),
            "servers": [asdict(server) for server in self.info.servers],
            "externalDocs": asdict(self.info.externalDocs) if self.info.externalDocs.url else None,
        }

    def add_openapi_path_obj(self, route_type: str, endpoint: str, openapi_summary: str, openapi_tags: list, signature: Signature = None):
        """
        Adds the given path to openapi spec

        :param route_type: the http method as string (get, post ...)
        :param endpoint: the endpoint to be added
        :param openapi_summary: short summary of the endpoint (to be fetched from the endpoint defenition by default)
        :param openapi_tags: tags -- for grouping of endpoints
        :param signature: the function signature -- to grab the typed dict annotations for query params
        """

        query_params = None

        if signature and "query_params" in signature.parameters:
            query_params = signature.parameters["query_params"].default

        modified_endpoint, path_obj = self.get_path_obj(endpoint, openapi_summary, openapi_tags, query_params)

        if modified_endpoint not in self.openapi_spec["paths"]:
            self.openapi_spec["paths"][modified_endpoint] = {}
        self.openapi_spec["paths"][modified_endpoint][route_type] = path_obj

    def add_subrouter_paths(self, subrouter_openapi):
        """
        Adds the subrouter paths to main router's openapi specs

        :param subrouter_openapi: the OpenAPI object of the current subrouter
        """
        paths = subrouter_openapi.openapi_spec["paths"]

        for path in paths:
            self.openapi_spec["paths"][path] = paths[path]

    def get_path_obj(self, endpoint: str, summary: str, tags: list, query_params: TypedDict = None) -> (str, dict):
        """
        Get the "path" openapi object according to spec

        :param endpoint: the endpoint to be added
        :param summary: short summary of the endpoint (to be fetched from the endpoint defenition by default)
        :param tags: tags -- for grouping of endpoints
        :param query_params: query params for the function

        :return: a tuple containing the endpoint with path params wrapped in braces and the "path" openapi object
        according to spec
        """
        # robyn has paths like /:url/:etc whereas openapi requires path like /{url}/{path}
        # this function is used for converting path params to the required form
        # initialized with endpoint for handling endpoints without path params
        endpoint_with_path_params_wrapped_in_braces = endpoint

        endpoint_path_params_split = endpoint.split(":")
        openapi_parameter_object = []

        if len(endpoint_path_params_split) > 1:
            endpoint_without_path_params = endpoint_path_params_split[0]

            endpoint_with_path_params_wrapped_in_braces = (
                endpoint_without_path_params[:-1] if endpoint_without_path_params.endswith("/") else endpoint_without_path_params
            )

            for path_param in endpoint_path_params_split[1:]:
                path_param_name = path_param[:-1] if path_param.endswith("/") else path_param

                openapi_parameter_object.append(
                    {
                        "name": path_param_name,
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                )
                endpoint_with_path_params_wrapped_in_braces += "/{" + path_param_name + "}"

        if query_params:
            for query_param in query_params.__annotations__:
                # ugly hack!
                # returns "<class 'int'>" -- this line strips out the type a.k.a int from it
                query_param_type = re.findall("'[a-z]+'", str(query_params.__annotations__[query_param]))[0].replace("'", "")

                openapi_parameter_object.append(
                    {
                        "name": query_param,
                        "in": "query",
                        "required": False,
                        "schema": {"type": query_param_type},
                    }
                )

        return endpoint_with_path_params_wrapped_in_braces, {
            "summary": summary,
            "tags": tags,
            "parameters": openapi_parameter_object,
            "responses": {
                "200": {
                    "description": "Successful Response",
                }
            },
        }

    def docs_handler(self) -> FileResponse:
        """
        Handler to the swagger html page to be deployed to the endpoint `/docs`
        @return: the swagger html page
        """
        html_file = str(Path("./robyn/swagger.html"))
        return serve_html(html_file)

    def json_handler(self) -> str:
        """
        Handler to the openapi spec json object to be deployed to the endpoint `/openapi.json`
        @return: a JSON string representing the openapi spec
        """
        return self.openapi_spec.__repr__()

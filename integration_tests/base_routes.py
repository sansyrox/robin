import os
import pathlib
from collections import defaultdict
from typing import Optional

from integration_tests.subroutes import di_subrouter, sub_router
from robyn import Headers, Request, Response, Robyn, WebSocket, WebSocketConnector, jsonify, serve_file, serve_html
from robyn.authentication import AuthenticationHandler, BearerGetter, Identity
from robyn.robyn import QueryParams, Url
from robyn.templating import JinjaTemplate
from robyn.types import Body, JSONResponse, Method, PathParams

app = Robyn(__file__)
websocket = WebSocket(app, "/web_socket")

# Creating a new WebSocket app to test json handling + to serve an example to future users of this lib
# while the original "raw" web_socket is used with benchmark tests
websocket_json = WebSocket(app, "/web_socket_json")

websocket_di = WebSocket(app, "/web_socket_di")

websocket_di.inject_global(GLOBAL_DEPENDENCY="GLOBAL DEPENDENCY")
websocket_di.inject(ROUTER_DEPENDENCY="ROUTER DEPENDENCY")

current_file_path = pathlib.Path(__file__).parent.resolve()
jinja_template = JinjaTemplate(os.path.join(current_file_path, "templates"))

# ===== Websockets =====

# Make it easier for multiple test runs
websocket_state = defaultdict(int)


@websocket_json.on("message")
async def jsonws_message(ws, msg: str) -> str:
    websocket_id = ws.id
    response: dict = {"ws_id": websocket_id, "resp": "", "msg": msg}
    global websocket_state
    state = websocket_state[websocket_id]
    if state == 0:
        response["resp"] = "Whaaat??"
    elif state == 1:
        response["resp"] = "Whooo??"
    elif state == 2:
        response["resp"] = "*chika* *chika* Slim Shady."
    websocket_state[websocket_id] = (state + 1) % 3
    return jsonify(response)


@websocket.on("message")
async def message(ws: WebSocketConnector, msg: str, global_dependencies) -> str:
    global websocket_state
    websocket_id = ws.id
    state = websocket_state[websocket_id]
    resp = ""
    if state == 0:
        resp = "Whaaat??"
        await ws.async_broadcast("This is a broadcast message")
        ws.sync_send_to(websocket_id, "This is a message to self")
    elif state == 1:
        resp = "Whooo??"
    elif state == 2:
        await ws.async_broadcast(ws.query_params.get("one"))
        ws.sync_send_to(websocket_id, ws.query_params.get("two"))
        resp = "*chika* *chika* Slim Shady."
    elif state == 3:
        ws.close()
        # TODO temporary fix to avoid CI failure
        resp = "Connection closed"

    websocket_state[websocket_id] = (state + 1) % 4
    return resp


@websocket.on("close")
def close():
    return "GoodBye world, from ws"


@websocket_json.on("close")
def jsonws_close():
    return "GoodBye world, from ws"


@websocket.on("connect")
def connect():
    return "Hello world, from ws"


@websocket_json.on("connect")
def jsonws_connect():
    return "Hello world, from ws"


@websocket_di.on("connect")
async def di_message_connect(global_dependencies, router_dependencies):
    return global_dependencies["GLOBAL_DEPENDENCY"] + " " + router_dependencies["ROUTER_DEPENDENCY"]


@websocket_di.on("message")
async def di_message():
    return ""


@websocket_di.on("close")
async def di_message_close():
    return ""


# ===== Lifecycle handlers =====


async def startup_handler():
    print("Starting up")


@app.shutdown_handler
def shutdown_handler():
    print("Shutting down")


# ===== Middlewares =====

# --- Global ---


@app.before_request()
def global_before_request(request: Request):
    request.headers.set("global_before", "global_before_request")
    return request


@app.after_request()
def global_after_request(response: Response):
    response.headers.set("global_after", "global_after_request")
    return response


@app.get("/sync/global/middlewares")
def sync_global_middlewares(request: Request):
    print(request.headers)
    print(request.headers.get("txt"))
    print(request.headers["txt"])
    assert "global_before" in request.headers
    assert request.headers.get("global_before") == "global_before_request"
    return "sync global middlewares"


# --- Route specific ---


@app.before_request("/sync/middlewares")
def sync_before_request(request: Request):
    request.headers.set("before", "sync_before_request")
    return request


@app.after_request("/sync/middlewares")
def sync_after_request(response: Response):
    response.headers.set("after", "sync_after_request")
    response.description = response.description + " after"
    return response


@app.get("/sync/middlewares")
def sync_middlewares(request: Request):
    assert "before" in request.headers
    assert request.headers.get("before") == "sync_before_request"
    assert request.ip_addr == "127.0.0.1"
    return "sync middlewares"


@app.before_request("/async/middlewares")
async def async_before_request(request: Request):
    request.headers.set("before", "async_before_request")
    return request


@app.after_request("/async/middlewares")
async def async_after_request(response: Response):
    response.headers.set("after", "async_after_request")
    response.description = response.description + " after"
    return response


@app.get("/async/middlewares")
async def async_middlewares(request: Request):
    assert "before" in request.headers
    assert request.headers.get("before") == "async_before_request"
    assert request.ip_addr == "127.0.0.1"
    return "async middlewares"


@app.before_request("/sync/middlewares/401")
def sync_before_request_401():
    return Response(401, Headers({}), "sync before request 401")


@app.get("/sync/middlewares/401")
def sync_middlewares_401():
    pass


# ===== Routes =====

# --- GET ---

# Hello world

app.inject(RouterDependency="Router Dependency")


@app.get("/", openapi_name="Index")
async def hello_world(r):
    """
    Get hello world
    """
    return "Hello, world!"


@app.get("/trailing")
def trailing_slash(request):
    return "Trailing slash test successful!"


@app.get("/sync/str")
def sync_str_get():
    return "sync str get"


@app.get("/async/str")
async def async_str_get():
    return "async str get"


@app.get("/sync/str/const", const=True)
def sync_str_const_get():
    return "sync str const get"


@app.get("/async/str/const", const=True)
async def async_str_const_get():
    return "async str const get"


# dict


@app.get("/sync/dict")
def sync_dict_get():
    return Response(
        status_code=200,
        description="sync dict get",
        headers={"sync": "dict"},
    )


@app.get("/async/dict")
async def async_dict_get():
    return Response(
        status_code=200,
        description="async dict get",
        headers={"async": "dict"},
    )


@app.get("/sync/dict/const", const=True)
def sync_dict_const_get():
    return Response(
        status_code=200,
        description="sync dict const get",
        headers={"sync_const": "dict"},
    )


@app.get("/async/dict/const", const=True)
async def async_dict_const_get():
    return Response(
        status_code=200,
        description="async dict const get",
        headers={"async_const": "dict"},
    )


# Response


@app.get("/sync/response")
def sync_response_get():
    return Response(200, Headers({"sync": "response"}), "sync response get")


@app.get("/async/response")
async def async_response_get():
    return Response(200, Headers({"async": "response"}), "async response get")


@app.get("/sync/response/const", const=True)
def sync_response_const_get():
    return Response(200, Headers({"sync_const": "response"}), "sync response const get")


@app.get("/async/response/const", const=True)
async def async_response_const_get():
    return Response(200, Headers({"async_const": "response"}), "async response const get")


# Binary


@app.get("/sync/octet")
def sync_octet_get():
    return b"sync octet"


@app.get("/async/octet")
async def async_octet_get():
    return b"async octet"


@app.get("/sync/octet/response")
def sync_octet_response_get():
    return Response(
        status_code=200,
        headers=Headers({"Content-Type": "application/octet-stream"}),
        description="sync octet response",
    )


@app.get("/async/octet/response")
async def async_octet_response_get():
    return Response(
        status_code=200,
        headers=Headers({"Content-Type": "application/octet-stream"}),
        description="async octet response",
    )


# JSON


@app.get("/sync/json")
def sync_json_get():
    return jsonify({"sync json get": "json"})


@app.get("/async/json")
async def async_json_get():
    return jsonify({"async json get": "json"})


@app.get("/sync/json/const", const=True)
def sync_json_const_get():
    return jsonify({"sync json const get": "json"})


@app.get("/async/json/const", const=True)
async def async_json_const_get():
    return jsonify({"async json const get": "json"})


# Param


@app.get("/sync/param/:id")
def sync_param(request: Request):
    id = request.path_params["id"]
    return id


@app.get("/async/param/:id")
async def async_param(request: Request):
    id = request.path_params["id"]
    return id


@app.get("/sync/extra/*extra")
def sync_param_extra(request: Request):
    extra = request.path_params["extra"]
    return extra


@app.get("/async/extra/*extra")
async def async_param_extra(request: Request):
    extra = request.path_params["extra"]
    return extra


# Request Info


@app.get("/sync/http/param")
def sync_http_param(request: Request):
    return jsonify(
        {
            "url": {
                "scheme": request.url.scheme,
                "host": request.url.host,
                "path": request.url.path,
            },
            "method": request.method,
        }
    )


@app.get("/async/http/param")
async def async_http_param(request: Request):
    return jsonify(
        {
            "url": {
                "scheme": request.url.scheme,
                "host": request.url.host,
                "path": request.url.path,
            },
            "method": request.method,
        }
    )


# HTML serving


@app.get("/sync/serve/html")
def sync_serve_html():
    html_file = os.path.join(current_file_path, "index.html")
    return serve_html(html_file)


@app.get("/async/serve/html")
async def async_serve_html():
    html_file = os.path.join(current_file_path, "index.html")
    return serve_html(html_file)


# Template


@app.get("/sync/template")
def sync_template_render():
    context = {"framework": "Robyn", "templating_engine": "Jinja2"}
    template = jinja_template.render_template(template_name="test.html", **context)
    return template


@app.get("/async/template")
async def async_template_render():
    context = {"framework": "Robyn", "templating_engine": "Jinja2"}
    template = jinja_template.render_template(template_name="test.html", **context)
    return template


# File download


@app.get("/sync/file/download")
def sync_file_download():
    file_path = os.path.join(current_file_path, "downloads", "test.txt")
    return serve_file(file_path)


@app.get("/async/file/download")
async def file_download_async():
    file_path = os.path.join(current_file_path, "downloads", "test.txt")
    return serve_file(file_path)


# Multipart file


@app.post("/sync/multipart-file")
def sync_multipart_file(request: Request):
    files = request.files
    file_names = files.keys()
    return {"file_names": list(file_names)}


@app.post("/sync/multipart-file-form")
def sync_multipart_file_form(request: Request):
    files = request.files
    file_names = files.keys()
    return {"form_data": request.form_data, "file_names": list(file_names)}


# Queries


@app.get("/sync/queries")
def sync_queries(request: Request):
    query_data = request.query_params.to_dict()
    return jsonify(query_data)


@app.get("/async/queries")
async def async_query(request: Request):
    query_data = request.query_params.to_dict()
    return jsonify(query_data)


# Status code


@app.get("/404")
def return_404():
    return Response(status_code=404, description="not found", headers={"Content-Type": "text"})


@app.get("/202")
def return_202():
    return Response(status_code=202, description="hello", headers={"Content-Type": "text"})


@app.get("/307")
async def redirect():
    return Response(
        status_code=307,
        description="",
        headers={"Location": "redirect_route"},
    )


@app.get("/redirect_route")
async def redirect_route():
    return "This is the redirected route"


@app.get("/sync/raise")
def sync_raise():
    raise Exception()


@app.get("/async/raise")
async def async_raise():
    raise Exception()


# cookie
@app.get("/cookie")
def cookie():
    response = Response(status_code=200, headers=Headers({}), description="test cookies")
    response.set_cookie(key="fakesession", value="fake-cookie-session-value")

    return response


# --- POST ---

# dict


@app.post("/sync/dict")
def sync_dict_post():
    return Response(
        status_code=200,
        description="sync dict post",
        headers={"sync": "dict"},
    )


@app.post("/async/dict")
async def async_dict_post():
    return Response(
        status_code=200,
        description="async dict post",
        headers={"async": "dict"},
    )


# Body


@app.post("/sync/body")
def sync_body_post(request: Request):
    return request.body


@app.post("/async/body")
async def async_body_post(request: Request):
    return request.body


@app.post("/sync/form_data")
def sync_form_data(request: Request):
    return request.headers["Content-Type"]


@app.post("/sync/simple_form_data")
def sync_simple_form_data(request: Request):
    return request.form_data["list_field"]


# JSON Request


@app.post("/sync/request_json")
def sync_json_post(request: Request):
    try:
        return type(request.json())
    except ValueError:
        return None


@app.post("/async/request_json")
async def async_json_post(request: Request):
    try:
        return type(request.json())
    except ValueError:
        return None


@app.post("/sync/request_json/key")
async def request_json(request: Request):
    json = request.json()
    return json["key"]


@app.post("/sync/request_json/list")
async def request_json_list(request: Request):
    json = request.json()
    return json["field"]


# --- PUT ---

# dict


@app.put("/sync/dict")
def sync_dict_put():
    return Response(
        status_code=200,
        description="sync dict put",
        headers={"sync": "dict"},
    )


@app.put("/async/dict")
async def async_dict_put():
    return Response(
        status_code=200,
        description="async dict put",
        headers={"async": "dict"},
    )


# Body


@app.put("/sync/body")
def sync_body_put(request: Request):
    return request.body


@app.put("/async/body")
async def async_body_put(request: Request):
    return request.body


# --- DELETE ---

# dict


@app.delete("/sync/dict")
def sync_dict_delete():
    return Response(
        status_code=200,
        description="sync dict delete",
        headers={"sync": "dict"},
    )


@app.delete("/async/dict")
async def async_dict_delete():
    return Response(
        status_code=200,
        description="async dict delete",
        headers={"async": "dict"},
    )


# Body


@app.delete("/sync/body")
def sync_body_delete(request: Request):
    print(request.body)
    return request.body


@app.delete("/async/body")
async def async_body_delete(request: Request):
    return request.body


# --- PATCH ---

# dict


@app.patch("/sync/dict")
def sync_dict_patch():
    return Response(
        status_code=200,
        description="sync dict patch",
        headers={"sync": "dict"},
    )


@app.patch("/async/dict")
async def async_dict_patch():
    return Response(
        status_code=200,
        description="async dict patch",
        # need to fix this
        headers={"async": "dict"},
    )


# Body


@app.patch("/sync/body")
def sync_body_patch(request: Request):
    return request.body


@app.patch("/async/body")
async def async_body_patch(request: Request):
    return request.body


# ==== Exception Handling ====


@app.exception
def handle_exception(error):
    return Response(status_code=500, description=f"error msg: {error}", headers={})


@app.get("/sync/exception/get")
def sync_exception_get():
    raise ValueError("value error")


@app.get("/async/exception/get")
async def async_exception_get():
    raise ValueError("value error")


@app.put("/sync/exception/put")
def sync_exception_put(request: Request):
    raise ValueError("value error")


@app.put("/async/exception/put")
async def async_exception_put(request: Request):
    raise ValueError("value error")


@app.post("/sync/exception/post")
def sync_exception_post(request: Request):
    raise ValueError("value error")


@app.post("/async/exception/post")
async def async_exception_post(request: Request):
    raise ValueError("value error")


# ===== Authentication =====


@app.get("/sync/auth", auth_required=True)
def sync_auth(request: Request):
    assert request.identity is not None
    assert request.identity.claims == {"key": "value"}
    return "authenticated"


@app.get("/async/auth", auth_required=True)
async def async_auth(request: Request):
    assert request.identity is not None
    assert request.identity.claims == {"key": "value"}
    return "authenticated"


# ===== Main =====


def sync_without_decorator():
    return "Success!"


async def async_without_decorator():
    return "Success!"


app.add_route("GET", "/sync/get/no_dec", sync_without_decorator)
app.add_route("PUT", "/sync/put/no_dec", sync_without_decorator)
app.add_route("POST", "/sync/post/no_dec", sync_without_decorator)
app.add_route("GET", "/async/get/no_dec", async_without_decorator)
app.add_route("PUT", "/async/put/no_dec", async_without_decorator)
app.add_route("POST", "/async/post/no_dec", async_without_decorator)

# ===== Dependency Injection =====

GLOBAL_DEPENDENCY = "GLOBAL DEPENDENCY"
ROUTER_DEPENDENCY = "ROUTER DEPENDENCY"

app.inject_global(GLOBAL_DEPENDENCY=GLOBAL_DEPENDENCY)
app.inject(ROUTER_DEPENDENCY=ROUTER_DEPENDENCY)


@app.get("/sync/global_di")
def sync_global_di(request, router_dependencies, global_dependencies):
    return global_dependencies["GLOBAL_DEPENDENCY"]


@app.get("/sync/router_di")
def sync_router_di(request, router_dependencies):
    return router_dependencies["ROUTER_DEPENDENCY"]


# ===== Split request body =====


@app.get("/sync/split_request_untyped/query_params")
def sync_split_request_untyped_basic(query_params):
    return query_params.to_dict()


@app.get("/async/split_request_untyped/query_params")
async def async_split_request_untyped_basic(query_params):
    return query_params.to_dict()


@app.get("/sync/split_request_untyped/headers")
def sync_split_request_untyped_headers(headers):
    return headers.get("server")


@app.get("/async/split_request_untyped/headers")
async def async_split_request_untyped_headers(headers):
    return headers.get("server")


@app.get("/sync/split_request_untyped/path_params/:id")
def sync_split_request_untyped_path_params(path_params):
    return path_params


@app.get("/async/split_request_untyped/path_params/:id")
async def async_split_request_untyped_path_params(path_params):
    return path_params


@app.get("/sync/split_request_untyped/method")
def sync_split_request_untyped_method(method):
    return method


@app.get("/async/split_request_untyped/method")
async def async_split_request_untyped_method(method):
    return method


@app.post("/sync/split_request_untyped/body")
def sync_split_request_untyped_body(body):
    return body


@app.post("/async/split_request_untyped/body")
async def async_split_request_untyped_body(body):
    return body


@app.post("/sync/split_request_untyped/combined")
def sync_split_request_untyped_combined(body, query_params, method, url, headers):
    return {
        "body": body,
        "query_params": query_params.to_dict(),
        "method": method,
        "url": url.path,
        "headers": headers.get("server"),
    }


@app.post("/async/split_request_untyped/combined")
async def async_split_request_untyped_combined(body, query_params, method, url, headers):
    return {
        "body": body,
        "query_params": query_params.to_dict(),
        "method": method,
        "url": url.path,
        "headers": headers.get("server"),
    }


@app.get("/sync/split_request_typed/query_params")
def sync_split_request_basic(query_data: QueryParams):
    return query_data.to_dict()


@app.get("/async/split_request_typed/query_params")
async def async_split_request_basic(query_data: QueryParams):
    return query_data.to_dict()


@app.get("/sync/split_request_typed/headers")
def sync_split_request_headers(request_headers: Headers):
    return request_headers.get("server")


@app.get("/async/split_request_typed/headers")
async def async_split_request_headers(request_headers: Headers):
    return request_headers.get("server")


@app.get("/sync/split_request_typed/path_params/:id")
def sync_split_request_path_params(path_data: PathParams):
    return path_data


@app.get("/async/split_request_typed/path_params/:id")
async def async_split_request_path_params(path_data: PathParams):
    return path_data


@app.get("/sync/split_request_typed/method")
def sync_split_request_method(request_method: Method):
    return request_method


@app.get("/async/split_request_typed/method")
async def async_split_request_method(request_method: Method):
    return request_method


@app.post("/sync/split_request_typed/body")
def sync_split_request_body(request_body: Body):
    return request_body


@app.post("/async/split_request_typed/body")
async def async_split_request_body(request_body: Body):
    return request_body


@app.post("/sync/split_request_typed/combined")
def sync_split_request_combined(
    request_body: Body,
    query_data: QueryParams,
    request_method: Method,
    request_url: Url,
    request_headers: Headers,
):
    return {
        "body": request_body,
        "query_params": query_data.to_dict(),
        "method": request_method,
        "url": request_url.path,
        "headers": request_headers.get("server"),
    }


@app.post("/async/split_request_typed/combined")
async def async_split_request_combined(
    request_body: Body,
    query_data: QueryParams,
    request_method: Method,
    request_url: Url,
    request_headers: Headers,
):
    return {
        "body": request_body,
        "query_params": query_data.to_dict(),
        "method": request_method,
        "url": request_url.path,
        "headers": request_headers.get("server"),
    }


@app.post("/sync/split_request_typed_untyped/combined")
def sync_split_request_typed_untyped_combined(
    query_params,
    request_method: Method,
    request_body: Body,
    url: Url,
    headers: Headers,
):
    return {
        "body": request_body,
        "query_params": query_params.to_dict(),
        "method": request_method,
        "url": url.path,
        "headers": headers.get("server"),
    }


@app.post("/async/split_request_typed_untyped/combined")
async def async_split_request_typed_untyped_combined(
    query_params,
    request_method: Method,
    request_body: Body,
    url: Url,
    headers: Headers,
):
    return {
        "body": request_body,
        "query_params": query_params.to_dict(),
        "method": request_method,
        "url": url.path,
        "headers": headers.get("server"),
    }


@app.post("/sync/split_request_typed_untyped/combined/failure")
def sync_split_request_typed_untyped_combined_failure(query_params, request_method: Method, request_body: Body, url: Url, headers: Headers, vishnu):
    return {
        "body": request_body,
        "query_params": query_params.to_dict(),
        "method": request_method,
        "url": url.path,
        "headers": headers.get("server"),
        "vishnu": vishnu,
    }


@app.post("/async/split_request_typed_untyped/combined/failure")
async def async_split_request_typed_untyped_combined_failure(query_params, request_method: Method, request_body: Body, url: Url, headers: Headers, vishnu):
    return {
        "body": request_body,
        "query_params": query_params.to_dict(),
        "method": request_method,
        "url": url.path,
        "headers": headers.get("server"),
        "vishnu": vishnu,
    }


@app.get("/openapi_test", openapi_tags=["test tag"])
def sample_openapi_endpoint():
    """Get openapi"""
    return 200


class Initial(Body):
    is_present: bool
    letter: Optional[str]


class FullName(Body):
    first: str
    second: str
    initial: Initial


class CreateItemBody(Body):
    name: FullName
    description: str
    price: float
    tax: float


class CreateItemResponse(JSONResponse):
    success: bool
    items_changed: int


class CreateItemQueryParamsParams(QueryParams):
    required: bool


@app.post("/openapi_request_body")
def create_item(request, body: CreateItemBody, query: CreateItemQueryParamsParams) -> CreateItemResponse:
    return CreateItemResponse(success=True, items_changed=2)


def main():
    app.set_response_header("server", "robyn")
    app.serve_directory(
        route="/test_dir",
        directory_path=os.path.join(current_file_path, "build"),
        index_file="index.html",
    )
    app.startup_handler(startup_handler)
    app.include_router(sub_router)
    app.include_router(di_subrouter)

    class BasicAuthHandler(AuthenticationHandler):
        def authenticate(self, request: Request) -> Optional[Identity]:
            token = self.token_getter.get_token(request)
            if token is not None:
                # Useless but we call the set_token method for testing purposes
                self.token_getter.set_token(request, token)
            if token == "valid":
                return Identity(claims={"key": "value"})
            return None

    app.configure_authentication(BasicAuthHandler(token_getter=BearerGetter()))
    app.start(port=8080, _check_port=False)


if __name__ == "__main__":
    main()

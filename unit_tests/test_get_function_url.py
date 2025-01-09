from robyn import Robyn
from robyn.templating import JinjaTemplate


def h(request):
    return "Hello"


def get_hello(request):
    return "get_Hello"


def post_hello(request):
    return "post_Hello"


def put_hello(request):
    return "put_Hello"


def delete_hello(request):
    return "delete_Hello"


def patch_hello(request):
    return "patch_Hello"


def options_hello(request):
    return "options_Hello"


def head_hello(request):
    return "head_Hello"


def test_get_function_url():
    app = Robyn(__file__)
    app.add_route("GET", "/", h)
    app.add_route("GET", "/get_hello", get_hello)
    app.add_route("POST", "/post_hello", post_hello)
    app.add_route("PUT", "/put_hello", put_hello)
    app.add_route("DELETE", "/delete_hello", delete_hello)
    app.add_route("PATCH", "/patch_hello", patch_hello)
    app.add_route("OPTIONS", "/options_hello", options_hello)
    app.add_route("HEAD", "/head_hello", head_hello)

    jinja_template = JinjaTemplate(".", "templates", "utf-8")
    jinja_template.set_robyn(app)

    assert jinja_template.get_function_url("h") == "/"
    assert jinja_template.get_function_url("get_hello") == "/get_hello"
    assert jinja_template.get_function_url("get_hello", "GET") == "/get_hello"
    assert jinja_template.get_function_url("post_hello", "POST") == "/post_hello"
    assert jinja_template.get_function_url("put_hello", "PUT") == "/put_hello"
    assert jinja_template.get_function_url("delete_hello", "DELETE") == "/delete_hello"
    assert jinja_template.get_function_url("patch_hello", "PATCH") == "/patch_hello"
    assert jinja_template.get_function_url("options_hello", "OPTIONS") == "/options_hello"
    assert jinja_template.get_function_url("head_hello", "HEAD") == "/head_hello"


def get_hello_param(request):
    return "get_Hello_param"


def test_get_function_url_with_params() -> None:
    app = Robyn(__file__)
    app.add_route("GET", "/get_hello/:id", get_hello_param)

    jinja_template = JinjaTemplate(".", "templates", "utf-8")
    jinja_template.set_robyn(app)

    url: str = jinja_template.get_function_url("get_hello_param", "GET", id=42)
    assert url == "/get_hello/42", f"Param filled url|{url}|"

## Features

## Synchronous Requests

Robyn supports both sync methods and async methods for fetching requests. Every method gets a request object from the routing decorator.

```python
@app.get("/")
def h(request):
    return "Hello, world"
```

## Async Requests

```python
@app.get("/")
async def h(request):
    return "Hello, world"
```

## All kinds of HTTP Requests

The request object contains the `body` in PUT/POST/PATCH. The `header`s are available in every request object.

Robyn supports every HTTP request method. The examples of some of them are below:

#### GET Request

```python
@app.get("/")
async def h(request):
    return "Hello World"
```

#### POST Request

```python
@app.post("/post")
async def postreq(request):
    return request.body
```

#### PUT Request

```python
@app.put("/put")
async def postreq(request):
    return request.body
```

#### PATCH Request

```python
@app.patch("/patch")
async def postreq(request):
    return request.body
```

#### DELETE Request

```python
@app.delete("/delete")
async def postreq(request):
    return request.body
```

#### Directory Serving

```python
app.add_directory(
    route="/test_dir",
    directory_path="build/",
    index_file="index.html",
)
```

## Dynamic Routes

You can add params in the routes and access them from the request object.

```python
from robyn import jsonify


@app.post("/jsonify/:id")
async def json(request):
    print(request["params"]["id"])
    return jsonify({"hello": "world"})
```

## Returning a JSON Response

You can also serve JSON responses when serving HTTP request using the following way.

```python
from robyn import jsonify


@app.post("/jsonify")
async def json(request):
    return jsonify({"hello": "world"})
```

## Format of the Response

Robyn supports several kinds of Response for your routes

#### Dictionary

Robyn accepts dictionaries to build a response for the route:

```python
@app.post("/dictionary")
async def dictionary(request):
    return {
        "status_code": 200,
        "body": "This is a regular response",
        "type": "text",
        "headers": {"Header": "header_value"},
    }
```

#### Response object

Robyn provides a `Response` object to help you build a valid response.

```python
from robyn.robyn import Response


@app.get("/response")
async def response(request):
    return Response(status_code=200, headers={}, body="OK")
```

#### Status Codes

Robyn provides `StatusCodes` if you want to return type safe Status Responses.

```python

from robyn import StatusCodes


@app.get("/response")
async def response(request):
    return Response(status_code=StatusCodes.HTTP_200_OK.value, headers={}, body="OK")
```

#### Returning a byte response
You can also return byte response when serving HTTP requests using the following way

```python
@app.get("/binary_output_response_sync")
def binary_output_response_sync(request):
    return Response(
        status_code=200,
        headers={"Content-Type": "application/octet-stream"},
        body="OK",
    )


@app.get("/binary_output_async")
async def binary_output_async(request):
    return b"OK"


@app.get("/binary_output_response_async")
async def binary_output_response_async(request):
    return Response(
        status_code=200,
        headers={"Content-Type": "application/octet-stream"},
        body="OK",
    )
```


#### Other types

Whenever you want to use another type for your routes, the `str` method will be called on it, and it will be stored in the body of the response. Here is an example that returns a string:

```python
@app.get("/")
async def hello(request):
    return "Hello World"
```

## Global Request Headers

You can also add global headers for every request.

```python
app.add_request_header("server", "robyn")
```

## Global Response Headers

You can also add global response headers for every request.

```python
app.add_response_header("content-type", "application/json")
```

## Per route headers

You can also add request and response headers for every route.

```python
@app.get("/request_headers")
async def request_headers():
    return {
        "status_code": 200,
        "body": "",
        "type": "text",
        "headers": {"Header": "header_value"},
    }
```

```python
@app.get("/response_headers")
async def response_headers():
    return {
        "headers": {"Header": "header_value"},
    }
```


Additionally, you can access headers for per route.

```python
@app.get("/test-headers")
def sync_before_request(request: Request):
    request.headers["test"] = "we are modifying the request headers in the middle of the request!"
    print(rquest)
```

## Query Params

You can access query params from every HTTP method.

For the url: `http://localhost:8080/query?a=b`

You can use the following code snippet.

```python
@app.get("/query")
async def query_get(request):
    query_data = request["queries"]
    return jsonify(query_data)
```

## Events

You can add startup and shutdown events in Robyn. These events will execute before the requests have started serving and after the serving has been completed.

```python
async def startup_handler():
    print("Starting up")


app.startup_handler(startup_handler)


@app.shutdown_handler
def shutdown_handler():
    print("Shutting down")
```

## WebSockets

You can now serve websockets using Robyn.

Firstly, you need to create a WebSocket Class and wrap it around your Robyn app.

```python
from robyn import Robyn, jsonify, WS


app = Robyn(__file__)
websocket = WS(app, "/web_socket")
```

Now, you can define 3 methods for every web_socket for their life cycle, they are as follows:

```python
@websocket.on("message")
def connect():
    global i
    i += 1
    if i == 0:
        return "Whaaat??"
    elif i == 1:
        return "Whooo??"
    elif i == 2:
        return "*chika* *chika* Slim Shady."
    elif i == 3:
        i = -1
        return ""


@websocket.on("close")
def close():
    return "Goodbye world, from ws"


@websocket.on("connect")
def message():
    return "Hello world, from ws"
```

The three methods:

- "message" is called when the socket receives a message
- "close" is called when the socket is disconnected
- "connect" is called when the socket connects

To see a complete service in action, you can go to the folder [../integration_tests/base_routes.py](../integration_tests/base_routes.py)

#### Web Socket Usage

```python
@websocket.on("message")
async def connect():
    global i
    i += 1
    if i == 0:
        return "Whaaat??"
    elif i == 1:
        return "Whooo??"
    elif i == 2:
        return "*chika* *chika* Slim Shady."
    elif i == 3:
        i = -1
        return ""


@websocket.on("close")
async def close():
    return "Goodbye world, from ws"


@websocket.on("connect")
async def message():
    return "Hello world, from ws"
```

## Middlewares

You can use both sync and async functions for middlewares!

```python
@app.before_request("/")
async def hello_before_request(request: Request):
    request.headers["before"] = "sync_before_request"
    print(request)


@app.after_request("/")
def hello_after_request(response: Response):
    response.headers["after"] = "sync_after_request"
    print(response)
```

## MultiCore Scaling

To run Robyn across multiple cores, you can use the following command:

`python app.py --workers=N --processes=N`

## Const Requests

You can pre-compute the response for each route. This will compute the response even before execution. This will improve the response time bypassing the need to access the router.

```python
@app.get("/", const=True)
async def h():
    return "Hello, world"
```

## Templates

You can render templates in Robyn. We ship `Jinja2` as our out-of-the-box solution. If you would like to add support for other templating engines you can create your own renderer too! Read more at [templating](/templates.md) documentation.

Here is a sample below.

main.py

```python
from robyn.templating import JinjaTemplate

current_file_path = pathlib.Path(__file__).parent.resolve()
JINJA_TEMPLATE = JinjaTemplate(os.path.join(current_file_path, "templates"))


@app.get("/template_render")
def template_render():
    context = {"framework": "Robyn", "templating_engine": "Jinja2"}

    template = JINJA_TEMPLATE.render_template(template_name="test.html", **context)
    return template
```

templates/test.html

```html
{# templates/test.html #}

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Results</title>
</head>

<body>
  <h1>{{framework}} 🤝 {{templating_engine}}</h1>
</body>
</html>
```

### Understanding the code

Inside your project, you need to have a directory to store the templates, called `templates` in our case.

You can store and any `Jinja2` templates inside that directory. We are calling it `test.html`.

## Views

To organise your code in a better way - either to group by responsibility or for code splitting, you can use `views`.

A view, simply is a function with a collection of other closures. e.g.
```python
def sample_view():
    def get():
        return "Hello, world!"

    def post(request):
        body = request.body
        return {"status_code": 200, "body": body}
```

The above view contains two closures for the `get` and the `post` request.

You can serve views in two ways:

1. Using an `@app.view` decorator.
```python
@app.view("/sync/view/decorator")
def sync_decorator_view():
    def get():
        return "Hello, world!"

    def post(request):
        body = request.body
        return {"status_code": 200, "body": body}


@app.view("/async/view/decorator")
def async_decorator_view():
    async def get():
        return "Hello, world!"

    async def post(request):
        body = request.body
        return {"status_code": 200, "body": body}
```


2. Importing it from a different file.

```python
#views.py
def View():
    async def get():
        return "Hello, world!"

    async def post(request):
        body = request.body
        return {
            "status": 200,
            "body": body,
            "headers": {"Content-Type": "text/json"},
        }
```

app.py
```python
from .views import View

...
...

app.add_view("/", View)

```


## Populating Environment Variables

Robyn uses a custom `robyn.env` file to populate environment variables. You can just add a `robyn.env` file in your project directory and add the environment variables you want to populate.

```bash
# robyn.env
ROBYN_ENV=development
ROBYN_PORT=8000
RANDOM_ENV=123
```



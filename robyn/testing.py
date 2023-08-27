# known issues:
# no support for path parameters, authentication, cookies, timeout, redirects, proxies, streams or certification
# uses a new TestRequest class instead of robyn.Request

import asyncio
from json import dumps
from typing import Callable, Optional, Union
from urllib3 import encode_multipart_formdata
from robyn import HttpMethod
from requests.models import Response

# until we figure out a better method, I will be copying the classes over
class TestUrl:
    """
    The url object passed to the route handler.

    Attributes:
        scheme (str): The scheme of the url. e.g. http, https
        host (str): The host of the url. e.g. localhost,
        path (str): The path of the url. e.g. /user
    """

    scheme: str
    host: str
    path: str

class TestIdentity:
    claims: dict[str, str]

class TestRequest:
    """
    The request object passed to the route handler.

    Attributes:
        queries (dict[str, str]): The query parameters of the request. e.g. /user?id=123 -> {"id": "123"}
        headers (dict[str, str]): The headers of the request. e.g. {"Content-Type": "application/json"}
        params (dict[str, str]): The parameters of the request. e.g. /user/:id -> {"id": "123"}
        body (Union[str, bytes]): The body of the request. If the request is a JSON, it will be a dict.
        method (str): The method of the request. e.g. GET, POST, PUT, DELETE
        ip_addr (Optional[str]): The IP Address of the client
    """

    queries: dict[str, str]
    headers: dict[str, str]
    path_params: dict[str, str]
    body: Union[str, bytes]
    method: str
    url: TestUrl
    ip_addr: Optional[str]
    identity: Optional[TestIdentity] = None
    
    def __init__(self, queries: Optional[dict] = None, headers: Optional[dict] = None, path_params: Optional[dict] = None, method: Optional[HttpMethod] = HttpMethod.GET, ip_addr: Optional[str] = None):
        if queries == None:
            queries = {}
        if headers == None:
            headers = {}
        if path_params == None:
            path_params = {}
        self.queries = queries
        self.headers = headers
        self.path_params = path_params
        self.method = method
        self.ip_addr = ip_addr

class TestClient:
    #helper function
    def get_route(self, path, method):
        routes = self.app.router.get_routes()
        r = None
        for route in routes: 
            if route.route == path and route.route_type == method:
                r = route
                break
        return r
    
    def __init__(self, app):
        self.app = app
    
    def get(self, method_path, **kwargs):
        return self.do_test_request(HttpMethod.GET, method_path, **kwargs)
    
    def post(self, method_path, **kwargs):
        return self.do_test_request(HttpMethod.POST, method_path, **kwargs)
    
    def delete(self, method_path, **kwargs):
        return self.do_test_request(HttpMethod.DELETE, method_path, **kwargs)
    
    def patch(self, method_path, **kwargs):
        return self.do_test_request(HttpMethod.PATCH, method_path, **kwargs)
        
    def options(self, method_path, **kwargs):
        return self.do_test_request(HttpMethod.OPTIONS, method_path, **kwargs)
        
    def head(self, method_path, **kwargs):
        return self.do_test_request(HttpMethod.HEAD, method_path, **kwargs)
        
    def trace(self, method_path, **kwargs):
        return self.do_test_request(HttpMethod.TRACE, method_path, **kwargs)
        
    def connect(self, method_path, **kwargs):
        return self.do_test_request(HttpMethod.CONNECT, method_path, **kwargs)
        
    # Helper functions
    def create_default_headers(self, req):
        req.headers["host"] = "localhost"
        req.headers["connection"] = "keep-alive"
        req.headers["user-agent"] = "robyn-testclient"
        req.headers["accept"] = "*/*"
        req.headers["accept-encoding"] = "gzip, deflate"
    def create_request_body(self, req, data, json, files):
        if files != None:
            body, header = encode_multipart_formdata(files)
            req.headers["content-type"] = header
            req.body = list(body)
            req.headers["content-length"] = len(req.body)
        elif data != None:
            if type(data) == bytes:
                req.body = list(data)
            elif type(data) == dict:
                body = ""
                for element in data:
                    body = body + element + "=" + data + "&"
                body = body[:-1]
                req.body = list(body)
                req.headers["content-type"] = "application/x-www-form-urlencoded"
            elif type(data) == list:
                body = ""
                for element in data:
                    body = body + element[0] + "=" + element[1] + "&"
                body = body[:-1]
                req.body = list(body)
                req.headers["content-type"] = "application/x-www-form-urlencoded"
            req.headers["content-length"] = len(req.body)
        elif json == None:
            req.headers["content-type"] = "application/json"
            req.body = list(dumps(json))
            req.headers["content-length"] = len(req.body)
    def add_input_parameters(self, req, params):
        if params != None:
            if type(params) == dict:
                req.queries = params
            elif type(params) == list:
                for param in params:
                    req.queries[param[0]] = param[1]
    def add_cookies(self, req, cookies):
        if cookies != None:
            #cookies are either a dict or a CookieJar
            if type(cookies) != dict:
                c = {}
                for cookie in cookies:
                    c[cookie.name] = cookie.values
                cookies = c
            if len(cookies) > 0:
                header = ""
                for cookie in cookies:
                    header = header + cookie + "=" + cookies[cookie] + "; "
                header = header[:-2]
                req.headers["cookie"] = header
    def create_response(self, response):
        r = Response()
        r.status_code = response.status_code
        r.headers = response.headers
        if len(response.body) > 0:
            r._content = response.body if type(response.body) == bytes else bytes(response.body)
        return r
    # Main function for calling methods through the testing client
    def do_test_request(self, method, method_path, data=None, json=None, headers=None, files=None, params=None, auth=None, cookies=None):
        route = self.get_route(method_path, method)
        if route == None:
            return None
        req = TestRequest(method = method)
        self.create_default_headers(req)
        #input headers
        if headers != None:
            for header in headers:
                req.headers[header] = headers[header]
        self.add_input_parameters(req, params)
        self.create_request_body(req, data, json, files)
        self.add_cookies(req, cookies)
        #auth objects (requests.auth)
        #TODO: make work with digest auth
        if auth != None:
            auth(req)
        #run the handler function
        response = asyncio.run(route.function.handler(req))
        #turn the output into a requests.Response object
        return self.create_response(response)

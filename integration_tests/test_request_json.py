import pytest

from integration_tests.helpers.http_methods_helpers import post


@pytest.mark.parametrize(
    "route, body, expected_result",
    [
        ("/sync/request_json", '{"hello": "world"}', "<class 'dict'>"),
        ("/sync/request_json/key", '{"key": "world"}', "world"),
        ("/sync/request_json", '{"hello": "world"', "None"),
        ("/async/request_json", '{"hello": "world"}', "<class 'dict'>"),
        ("/async/request_json", '{"hello": "world"', "None"),
        ("/sync/request_json/list", '{"hello": "world", "field": ["a=", "b"]}', "['a=', 'b']"),
    ],
)
def test_request(route, body, expected_result):
    res = post(route, body)
    assert res.text == expected_result

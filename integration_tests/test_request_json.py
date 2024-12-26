import pytest
import json
from integration_tests.helpers.http_methods_helpers import post


@pytest.mark.parametrize(
    "route, body, expected_result",
    [
        ("/sync/request_json", '{"hello": "world"}', "<class 'dict'>"),
        ("/sync/request_json/key", '{"key": "world"}', "world"),
        ("/sync/request_json", '{"hello": "world"', "None"),
        ("/async/request_json", '{"hello": "world"}', "<class 'dict'>"),
        ("/async/request_json", '{"hello": "world"', "None"),
    ],
)
def test_request(route, body, expected_result):
    res = post(route, body)
    assert res.text == expected_result


@pytest.mark.parametrize(
    "route, body, expected_result",
    [
        ("/sync/request_json/json_type", '{"start": null}', {"start": None}),  # null
        ("/sync/request_json/json_type", '{"hello": "world"', None),  # invalid json
        ("/sync/request_json/json_type", '{"lid":570}', {"lid": 570}),  # number key
        ("/sync/request_json/json_type", '{"lid":-570}', {"lid": -570}),  # number key
        ("/sync/request_json/json_type", '{"lid":570.12}', {"lid": 570.12}),  # number key
        ("/sync/request_json/json_type", "[]", []),  # empty Array
        ("/sync/request_json/json_type", "{}", {}),  # empty object
        ("/sync/request_json/json_type", '"string"', "string"),  # string only
        ("/sync/request_json/json_type", "570", 570),  # number only
        (
            "/sync/request_json/json_type",  # object with multiple keys
            '{"lid": 570, "start": null, "field_name": "mobile", "field_value": "111000111"}',
            {"lid": int(570), "start": None, "field_name": "mobile", "field_value": "111000111"},
        ),
        ("/sync/request_json/json_type", '[{"k":"v"},{"k":null}]', [{"k": "v"}, {"k": None}]),  # Array<object>
        ("/sync/request_json/json_type", '{"key":[{"k":"v"},{"k":null}]}', {"key": [{"k": "v"}, {"k": None}]}),
        # Array Key
    ],
)
def test_request_type(route, body, expected_result):
    res = post(route, body)
    res_dict = json.loads(res.text)
    # Compare the response dictionary with the expected result
    assert res_dict == expected_result

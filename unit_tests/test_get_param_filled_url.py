from robyn.templating import get_param_filled_url


def test_get_param_filled_url_42() -> None:
    d42: dict = {"id": 42}
    assert get_param_filled_url("/get_hello/:id", d42) == "/get_hello/42"
    assert get_param_filled_url("/:id", d42) == "/42"
    assert get_param_filled_url("/get_hello/:idmore", d42) == "/get_hello/42more"
    assert get_param_filled_url("/get_hello/:id/", d42) == "/get_hello/42/"
    assert get_param_filled_url("/get_hello/:id/more", d42) == "/get_hello/42/more"


def test_get_param_filled_url_2s() -> None:
    d42: dict = {"id": 42, "s": "str"}
    assert get_param_filled_url("/get_hello/:id/:s", d42) == "/get_hello/42/str"
    assert get_param_filled_url("/:id/:s", d42) == "/42/str"
    assert get_param_filled_url("/get_hello/:id:smore", d42) == "/get_hello/42strmore"
    assert get_param_filled_url("/get_hello/:id/:s/", d42) == "/get_hello/42/str/"
    assert get_param_filled_url("/get_hello/:id/:s/more", d42) == "/get_hello/42/str/more"
    assert get_param_filled_url("/get_hello/:s/:id/:s/more", d42) == "/get_hello/str/42/str/more"


def test_get_param_filled_url() -> None:
    assert get_param_filled_url("/get_hello/:id/:s") == "/get_hello/:id/:s"
    assert get_param_filled_url("/:id/:s") == "/:id/:s"
    assert get_param_filled_url("/get_hello/:id:smore") == "/get_hello/:id:smore"
    assert get_param_filled_url("/get_hello/:id/:s/") == "/get_hello/:id/:s/"
    assert get_param_filled_url("/get_hello/:id/:s/more") == "/get_hello/:id/:s/more"
    assert get_param_filled_url("/get_hello/:s/:id/:s/more") == "/get_hello/:s/:id/:s/more"

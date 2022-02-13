import requests


def test_default_url_index_request(default_session):
    BASE_URL = "http://127.0.0.1:5000"
    res = requests.get(f"{BASE_URL}")
    assert(res.status_code == 200)


def test_local_index_request(session):
    BASE_URL = "http://127.0.0.1:5000"
    res = requests.get(f"{BASE_URL}")
    assert(res.status_code == 200)


def test_global_index_request(global_session):
    BASE_URL = "http://0.0.0.0:5000"
    res = requests.get(f"{BASE_URL}")
    assert(res.status_code == 200)


def test_dev_index_request(dev_session):
    BASE_URL = "http://0.0.0.0:5000"
    res = requests.get(f"{BASE_URL}")
    assert(res.status_code == 200)


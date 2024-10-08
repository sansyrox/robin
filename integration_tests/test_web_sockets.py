import json

import pytest
from websocket import create_connection

BASE_URL = "ws://127.0.0.1:8080"


@pytest.mark.benchmark
def test_web_socket_raw_benchmark(session):
    ws = create_connection(f"{BASE_URL}/web_socket?one=hi&two=hello")
    assert ws.recv() == "Hello world, from ws"

    ws.send("My name is?")
    assert ws.recv() == "This is a broadcast message"
    assert ws.recv() == "This is a message to self"
    assert ws.recv() == "Whaaat??"

    ws.send("My name is?")
    assert ws.recv() == "Whooo??"

    ws.send("My name is?")
    assert ws.recv() == "hi"
    assert ws.recv() == "hello"
    assert ws.recv() == "*chika* *chika* Slim Shady."

    # this will close the connection
    ws.send("test")
    assert ws.recv() == "Connection closed"


def test_web_socket_json(session):
    """
    Not using this as the benchmark test since this involves JSON marshalling/unmarshalling
    which pollutes the benchmark measurement.
    """
    ws = create_connection(f"{BASE_URL}/web_socket_json")
    assert ws.recv() == "Hello world, from ws"

    msg = "My name is?"

    ws.send(msg)
    resp = json.loads(ws.recv())
    assert resp["resp"] == "Whaaat??"
    assert resp["msg"] == msg

    ws.send(msg)
    resp = json.loads(ws.recv())
    assert resp["resp"] == "Whooo??"
    assert resp["msg"] == msg

    ws.send(msg)
    resp = json.loads(ws.recv())
    assert resp["resp"] == "*chika* *chika* Slim Shady."
    assert resp["msg"] == msg


def test_websocket_di(session):
    """
    Not using this as the benchmark test since this involves JSON marshalling/unmarshalling

    """

    msg = "GLOBAL DEPENDENCY ROUTER DEPENDENCY"

    ws = create_connection(f"{BASE_URL}/web_socket_di")
    assert ws.recv() == msg

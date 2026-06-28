"""Unit tests for the NetSysDB wire protocol."""

import json
import os
import socket
import struct
import sys
import threading

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared import protocol  # noqa: E402
from shared.protocol import (  # noqa: E402
    HEADER_SIZE,
    MAGIC,
    MSG_ALERT,
    MSG_HEARTBEAT,
    MSG_METRIC,
    decode,
    encode,
    recv_message,
)

SAMPLE_PAYLOADS = [
    {},
    {"a": 1},
    {"machine_name": "node-1", "cpu_percent": 12.34, "list": [1, 2, 3]},
    {"nested": {"x": {"y": [True, False, None]}}, "unicode": "café—über"},
    {"big": "z" * 5000},
]


@pytest.mark.parametrize("payload", SAMPLE_PAYLOADS)
@pytest.mark.parametrize("msg_type", [MSG_METRIC, MSG_HEARTBEAT, MSG_ALERT])
def test_encode_decode_roundtrip(msg_type, payload):
    """decode(encode(...)) reproduces the original (msg_type, payload)."""
    assert decode(encode(msg_type, payload)) == (msg_type, payload)


def test_encode_length_is_json_plus_header():
    """A frame is exactly len(json) + HEADER_SIZE bytes."""
    payload = {"machine_name": "node-1", "cpu_percent": 99.9}
    frame = encode(MSG_METRIC, payload)
    json_len = len(json.dumps(payload).encode("utf-8"))
    assert len(frame) == json_len + HEADER_SIZE


def test_bad_magic_raises():
    """decode() rejects a frame whose magic number is wrong."""
    good = encode(MSG_METRIC, {"x": 1})
    # Corrupt the first 4 bytes (the magic) with a different value.
    bad = struct.pack("!I", MAGIC ^ 0xFFFFFFFF) + good[4:]
    with pytest.raises(ValueError):
        decode(bad)


def test_header_field_values():
    """The packed header carries the expected magic / length / type."""
    payload = {"hello": "world"}
    frame = encode(MSG_ALERT, payload)
    magic, length, msg_type, version = struct.unpack("!IIBB", frame[:HEADER_SIZE])
    assert magic == MAGIC
    assert length == len(json.dumps(payload).encode("utf-8"))
    assert msg_type == MSG_ALERT
    assert version == protocol.VERSION


def test_recv_message_over_socketpair():
    """recv_message reassembles a frame sent over a real socket."""
    payload = {"machine_name": "node-2", "values": list(range(50))}

    # socket.socketpair is available on Windows in modern CPython via AF_INET.
    server, client = socket.socketpair()
    try:
        # Send in two chunks to exercise the _recv_exact loop.
        frame = encode(MSG_METRIC, payload)
        mid = len(frame) // 2

        def _send():
            client.sendall(frame[:mid])
            client.sendall(frame[mid:])

        t = threading.Thread(target=_send)
        t.start()
        msg_type, got = recv_message(server)
        t.join()

        assert msg_type == MSG_METRIC
        assert got == payload
    finally:
        server.close()
        client.close()


def test_recv_message_connection_closed():
    """recv_message raises ConnectionError when the peer closes early."""
    server, client = socket.socketpair()
    try:
        client.close()  # peer hangs up before sending anything
        with pytest.raises(ConnectionError):
            recv_message(server)
    finally:
        server.close()

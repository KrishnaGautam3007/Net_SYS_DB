"""NetSysDB — wire protocol (shared by agent and collector).

Frame layout (big-endian)::

    byte 0-3  : MAGIC          (uint32)   0xDEADBEEF
    byte 4-7  : payload length (uint32)   length of the JSON payload
    byte 8    : msg_type       (uint8)
    byte 9    : VERSION        (uint8)
    byte 10.. : payload        (UTF-8 JSON, ``payload length`` bytes)

The 10-byte header uses struct format ``"!IIBB"``. The payload is a JSON
object (``json`` is used here for encoding only, never for storage).
"""

import json
import struct

MAGIC = 0xDEADBEEF
VERSION = 0x01

MSG_METRIC = 0x01
MSG_HEARTBEAT = 0x02
MSG_ALERT = 0x03

HEADER_SIZE = 10
_HEADER_FORMAT = "!IIBB"  # magic, payload_len, msg_type, version


def encode(msg_type: int, payload: dict) -> bytes:
    """Serialize ``payload`` to a complete protocol frame (header + JSON)."""
    json_bytes = json.dumps(payload).encode("utf-8")
    header = struct.pack(_HEADER_FORMAT, MAGIC, len(json_bytes), msg_type, VERSION)
    return header + json_bytes


def decode(data: bytes) -> tuple:
    """Decode a complete frame into ``(msg_type, payload_dict)``.

    Raises ``ValueError`` if the magic number does not match.
    """
    assert len(data) >= HEADER_SIZE, "buffer smaller than header"
    magic, payload_len, msg_type, _version = struct.unpack(
        _HEADER_FORMAT, data[:HEADER_SIZE]
    )
    if magic != MAGIC:
        raise ValueError("bad magic")
    payload_json = data[HEADER_SIZE : HEADER_SIZE + payload_len].decode("utf-8")
    return msg_type, json.loads(payload_json)


def _recv_exact(sock, n: int) -> bytes:
    """Read exactly ``n`` bytes from ``sock`` or raise ``ConnectionError``."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed")
        buf += chunk
    return buf


def recv_message(sock) -> tuple:
    """Read one full framed message from a blocking socket.

    Returns ``(msg_type, payload_dict)``. Raises ``ConnectionError`` if the
    peer closes the connection, or ``ValueError`` on a bad magic number.
    """
    header = _recv_exact(sock, HEADER_SIZE)
    magic, payload_len, _msg_type, _version = struct.unpack(_HEADER_FORMAT, header)
    if magic != MAGIC:
        raise ValueError("bad magic")
    payload = _recv_exact(sock, payload_len) if payload_len else b""
    return decode(header + payload)

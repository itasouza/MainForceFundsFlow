"""ZeroMQ PUB socket for MTF flow signals."""

from __future__ import annotations

import json
from typing import Any

import zmq


class FlowPublisher:
    """Publish JSON signals on a ZeroMQ PUB socket."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5555) -> None:
        self._host = host
        self._port = port
        self._ctx = zmq.Context.instance()
        self._socket = self._ctx.socket(zmq.PUB)
        self._socket.bind(f"tcp://{host}:{port}")

    @property
    def endpoint(self) -> str:
        return f"tcp://{self._host}:{self._port}"

    def publish(self, payload: dict[str, Any], topic: str = "gold_mtf_flow") -> None:
        """Send one JSON message (multipart: topic + body)."""
        body = json.dumps(payload, separators=(",", ":"))
        self._socket.send_string(topic, zmq.SNDMORE)
        self._socket.send_string(body)

    def close(self) -> None:
        self._socket.close(linger=0)

"""ZeroMQ PUB for composite MTF signals (consumed by NT strategy / dashboard)."""

from __future__ import annotations

import json
from typing import Any

import zmq


class SignalPublisher:
    """Publish JSON signal payloads on a ZeroMQ PUB socket."""

    def __init__(self, bind: str = "tcp://*:5555", topic: str = "gold_mtf_flow") -> None:
        self.bind = bind
        self.topic = topic
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.PUB)
        self._sock.setsockopt(zmq.LINGER, 0)
        self._sock.bind(bind)

    def publish(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":"))
        self._sock.send_string(self.topic, zmq.SNDMORE)
        self._sock.send_string(body)

    def close(self) -> None:
        self._sock.close(linger=0)

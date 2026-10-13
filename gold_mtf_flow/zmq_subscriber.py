"""ZeroMQ SUB client for MTF flow messages."""

from __future__ import annotations

import json
from typing import Any, Callable

import zmq


class FlowSubscriber:
    """Subscribe to ``gold_mtf_flow`` topic on a PUB socket."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5555,
        topic: str = "gold_mtf_flow",
    ) -> None:
        self._host = host
        self._port = port
        self._topic = topic
        self._ctx = zmq.Context.instance()
        self._socket = self._ctx.socket(zmq.SUB)
        self._socket.setsockopt(zmq.RCVTIMEO, 1000)
        self._socket.connect(f"tcp://{host}:{port}")
        self._socket.subscribe(topic)

    @property
    def endpoint(self) -> str:
        return f"tcp://{self._host}:{self._port}"

    def recv_one(self) -> dict[str, Any] | None:
        """Non-blocking-ish receive; returns None on timeout."""
        try:
            parts = self._socket.recv_multipart()
        except zmq.Again:
            return None
        if len(parts) < 2:
            return None
        body = parts[1].decode("utf-8") if isinstance(parts[1], bytes) else parts[1]
        return json.loads(body)

    def close(self) -> None:
        self._socket.close(linger=0)


def run_subscriber_loop(
    subscriber: FlowSubscriber,
    on_message: Callable[[dict[str, Any]], None],
    stop_event: Any,
) -> None:
    """Poll ZMQ until ``stop_event`` is set."""
    while not stop_event.is_set():
        payload = subscriber.recv_one()
        if payload is not None:
            on_message(payload)

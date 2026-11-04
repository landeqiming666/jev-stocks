from __future__ import annotations

import json
import os
import queue
import threading
from collections.abc import Iterator
from typing import BinaryIO

import pytest

from sentinel.rpc import Dispatcher, RpcServer, ServerConfig
from sentinel.rpc.protocol import serialize
from sentinel.rpc.server import DEFAULT_CONFIG


class PipePair:
    def __init__(self, dispatcher: Dispatcher, config: ServerConfig = DEFAULT_CONFIG) -> None:
        incoming, self.input = self._pipe()
        self.output, outgoing = self._pipe()
        self.lines: queue.Queue[dict[str, object]] = queue.Queue()
        self.server = RpcServer(incoming, outgoing, dispatcher, config)
        self._observer = threading.Thread(target=self._observe, daemon=True)
        self._observer.start()
        self.server.start()
        self._outgoing = outgoing

    @staticmethod
    def _pipe() -> tuple[BinaryIO, BinaryIO]:
        reader, writer = os.pipe()
        return os.fdopen(reader, "rb", buffering=0), os.fdopen(writer, "wb", buffering=0)

    def _observe(self) -> None:
        while line := self.output.readline():
            self.lines.put(json.loads(line))

    def raw(self, data: bytes) -> None:
        offset = 0
        while offset < len(data):
            written = self.input.write(data[offset:])
            assert written is not None and written > 0
            offset += written

    def request(self, request_id: str, method: str, params: object = None) -> None:
        self.raw(
            serialize(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": {} if params is None else params,
                }
            )
        )

    def cancel(self, request_id: str) -> None:
        self.raw(serialize({"jsonrpc": "2.0", "method": "$/cancel", "params": {"id": request_id}}))

    def wait_for_line(self, timeout: float = 1.0) -> dict[str, object]:
        return self.lines.get(timeout=timeout)

    def close(self) -> None:
        self.input.close()
        self.server.stop()
        self._outgoing.close()
        self._observer.join(1.0)
        self.output.close()


@pytest.fixture
def dispatcher() -> Dispatcher:
    return Dispatcher()


@pytest.fixture
def pipe_pair(dispatcher: Dispatcher) -> Iterator[PipePair]:
    pair = PipePair(dispatcher, ServerConfig(shutdown_timeout_s=0.5))
    try:
        yield pair
    finally:
        pair.close()

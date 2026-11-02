from __future__ import annotations

import json

import pytest

from sentinel.rpc.protocol import (
    MAX_LINE_BYTES,
    CancelNotification,
    LineTooLarge,
    ProtocolError,
    Request,
    parse_request,
    recover_id,
    serialize,
)


def test_protocol_parses_minimal_ping_request() -> None:
    request = parse_request(b'{"jsonrpc":"2.0","id":"r-1","method":"app.ping","params":{}}')
    assert isinstance(request, Request)
    assert request.id == "r-1"
    assert request.method == "app.ping"
    assert request.params == {}


def test_protocol_rejects_line_over_one_mib() -> None:
    with pytest.raises(LineTooLarge) as raised:
        parse_request(b"x" * (MAX_LINE_BYTES + 1))
    assert raised.value.bytes == MAX_LINE_BYTES + 1


def test_protocol_serializes_one_line_with_lf_only() -> None:
    payload = serialize({"jsonrpc": "2.0", "id": "r-1", "result": {"ok": True, "text": "\r\n中文"}})
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1
    assert b"\r" not in payload
    assert json.loads(payload)["result"]["text"] == "\r\n中文"


@pytest.mark.parametrize(
    "changes",
    [
        {"params": None},
        {"params": []},
        {"id": 1},
        {"id": ""},
        {"id": "x" * 65},
        {"id": "中文"},
        {"id": "a\n"},
        {"method": "ping"},
        {"method": "App.ping"},
        {"jsonrpc": 2.0},
        {"jsonrpc": "1.0"},
        {"extra": True},
    ],
)
def test_protocol_rejects_invalid_envelopes(changes: dict[str, object]) -> None:
    message = {"jsonrpc": "2.0", "id": "r-1", "method": "app.ping", "params": {}} | changes
    with pytest.raises(ProtocolError):
        parse_request(serialize(message))


@pytest.mark.parametrize("missing", ["jsonrpc", "id", "method", "params"])
def test_protocol_requires_every_request_field(missing: str) -> None:
    message: dict[str, object] = {"jsonrpc": "2.0", "id": "r-1", "method": "app.ping", "params": {}}
    del message[missing]
    with pytest.raises(ProtocolError):
        parse_request(serialize(message))


@pytest.mark.parametrize(
    "line",
    [
        b"[]",
        b"null",
        b"1",
        b'{"id":"r-1",',
        b"\xff",
        b'{"id":"r-1","params":NaN}',
        b'{"id":"r-1","params":Infinity}',
        b'{"id":"r-1","id":"r-2"}',
        b'{"id":"r-1","params":"\\ud800"}',
    ],
)
def test_protocol_rejects_invalid_json(line: bytes) -> None:
    with pytest.raises(ProtocolError):
        parse_request(line)


def test_protocol_parses_strict_cancel_notification() -> None:
    message: dict[str, object] = {"jsonrpc": "2.0", "method": "$/cancel", "params": {"id": "r-1"}}
    result = parse_request(serialize(message))
    assert isinstance(result, CancelNotification)
    assert result.params.id == "r-1"
    for extra in ({"id": "cancel-id"}, {"params": {"id": "r-1", "extra": 1}}):
        with pytest.raises(ProtocolError):
            parse_request(serialize(message | extra))


def test_utf8_limit_counts_bytes_and_accepts_exact_limit() -> None:
    message = serialize(
        {"jsonrpc": "2.0", "id": "r-1", "method": "app.ping", "params": {"text": "中文"}}
    )
    assert parse_request(message, len(message)).id == "r-1"  # type: ignore[union-attr]
    with pytest.raises(LineTooLarge):
        parse_request(message, len(message) - 1)


def test_recover_id_ignores_nested_params_id() -> None:
    assert recover_id(b'{"params":{"id":"nested"},"id":"top",') == "top"
    assert recover_id(b'{"params":{"id":"nested"},') is None
    assert recover_id(b'{"jsonrpc":"2.0","id":"r-1","params":') == "r-1"


def test_oversized_prefix_recovers_id() -> None:
    with pytest.raises(LineTooLarge) as raised:
        parse_request(b'{"jsonrpc":"2.0","id":"r-1","params":"' + b"x" * MAX_LINE_BYTES)
    assert raised.value.request_id == "r-1"

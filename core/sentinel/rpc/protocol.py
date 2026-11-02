from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sentinel.errors import SentinelError, UserError

MAX_LINE_BYTES = 1_048_576
METHOD_PATTERN = r"^[a-z][a-z0-9]*(\.[A-Za-z][A-Za-z0-9]*)+$"
ID_PATTERN = r"^[\x20-\x7e]{1,64}$"


class Request(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    jsonrpc: Literal["2.0"]
    id: str = Field(pattern=ID_PATTERN)
    method: str = Field(pattern=METHOD_PATTERN)
    params: dict[str, object]


class CancelNotification(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    jsonrpc: Literal["2.0"]
    method: Literal["$/cancel"]
    params: CancelParams


class CancelParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(pattern=ID_PATTERN)


@dataclass
class ProtocolError(ValueError):
    request_id: str | None = None
    field: str | None = None
    reason: str = "INVALID_REQUEST"


class LineTooLarge(ProtocolError):
    def __init__(self, size: int, request_id: str | None = None) -> None:
        super().__init__(request_id, reason="LINE_TOO_LARGE")
        self.bytes = size


def recover_id(line: bytes) -> str | None:
    # 只恢复顶层 ID，避免把 params.id 当作请求编号。
    text = line.decode("utf-8", errors="replace").lstrip()
    if not text.startswith("{"):
        return None
    decoder = json.JSONDecoder()
    text = text[1:].lstrip()
    try:
        while text:
            key, end = decoder.raw_decode(text)
            text = text[end:].lstrip()
            if not text.startswith(":"):
                return None
            value, end = decoder.raw_decode(text[1:].lstrip())
            if key == "id":
                return value if isinstance(value, str) and re.fullmatch(ID_PATTERN, value) else None
            text = text[1:].lstrip()[end:].lstrip()
            if not text.startswith(","):
                return None
            text = text[1:].lstrip()
    except (ValueError, RecursionError):
        return None
    return None


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_: str) -> object:
    raise ValueError("non-finite JSON number")


def parse_request(
    line: bytes, max_line_bytes: int = MAX_LINE_BYTES
) -> Request | CancelNotification:
    request_id = recover_id(line[:max_line_bytes])
    if len(line) > max_line_bytes:
        raise LineTooLarge(len(line), recover_id(line[:64]))
    try:
        raw = json.loads(line.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        # JSON 转义也可能引入不合法的 Unicode surrogate。
        json.dumps(raw, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError(request_id, reason="INVALID_JSON") from exc
    if not isinstance(raw, dict):
        raise ProtocolError(request_id)
    model = CancelNotification if raw.get("method") == "$/cancel" else Request
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        field = ".".join(str(part) for part in exc.errors()[0]["loc"])
        raise ProtocolError(request_id, field=field) from exc


def serialize(message: Mapping[str, object]) -> bytes:
    return (
        json.dumps(dict(message), ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def success(request_id: str, result: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def failure(request_id: str, error: SentinelError) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": error.to_wire(request_id)}


def invalid(error: ProtocolError) -> dict[str, object]:
    assert error.request_id is not None
    return failure(
        error.request_id,
        UserError(
            "INVALID_ARGUMENT",
            field=error.field,
            reason=error.reason,
        ),
    )

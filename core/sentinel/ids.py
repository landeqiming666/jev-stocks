"""不依赖第三方库的 ULID 生成、解析与确定性段落 ID。"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from . import clock

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
MAX_TIMESTAMP_MS = (1 << 48) - 1

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ONE_MS = timedelta(milliseconds=1)


def new_id(*, timestamp_ms: int | None = None, entropy: bytes | None = None) -> str:
    """生成 26 字符 ULID。"""
    if timestamp_ms is None:
        timestamp_ms = (clock.now() - _EPOCH) // _ONE_MS
    if not isinstance(timestamp_ms, int) or isinstance(timestamp_ms, bool):
        raise ValueError("timestamp_ms must be an integer")
    if not 0 <= timestamp_ms <= MAX_TIMESTAMP_MS:
        raise ValueError("timestamp_ms is outside the ULID range")

    if entropy is None:
        entropy = secrets.token_bytes(10)
    if not isinstance(entropy, bytes) or len(entropy) != 10:
        raise ValueError("entropy must be exactly 10 bytes")

    value = (timestamp_ms << 80) | int.from_bytes(entropy, "big")
    chars = ["0"] * 26
    for index in range(25, -1, -1):
        chars[index] = CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def is_ulid(value: str) -> bool:
    """判断字符串是否为规范的大写 26 字符 ULID。"""
    return (
        isinstance(value, str)
        and len(value) == 26
        and value[0] in "01234567"
        and all(char in CROCKFORD for char in value)
    )


def ulid_to_timestamp_ms(value: str) -> int:
    """解析 ULID 的 48 位毫秒时间戳。"""
    if not is_ulid(value):
        raise ValueError("invalid ULID")

    number = 0
    for char in value:
        number = (number << 5) | CROCKFORD.index(char)
    return number >> 80


def passage_id(event_id: str, file_seq: int, start: int, end: int) -> str:
    """按事件、文件序号和字符区间生成稳定的 32 位段落 ID。"""
    if not isinstance(event_id, str):
        raise ValueError("event_id must be a string")
    if not isinstance(file_seq, int) or isinstance(file_seq, bool) or file_seq < 0:
        raise ValueError("file_seq must be a non-negative integer")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or start >= end
    ):
        raise ValueError("start and end must satisfy 0 <= start < end")

    payload = f"{event_id}|{file_seq}|{start}|{end}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

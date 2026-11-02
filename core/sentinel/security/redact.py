"""文本与对象的统一脱敏。"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping

MASK = "***REDACTED***"
MAX_REDACT_DEPTH = 8

_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*")
_HEX_PATTERN = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_SENSITIVE_KEY_PATTERN = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|cookie)")

_secrets: set[str] = set()
_secrets_lock = threading.Lock()


def register_secret(value: str) -> None:
    """登记需要在本进程内按原文屏蔽的密钥。"""
    if not value or not value.strip():
        return
    with _secrets_lock:
        _secrets.add(value)


def clear_secrets() -> None:
    """清空进程内密钥登记。"""
    with _secrets_lock:
        _secrets.clear()


def redact_text(text: str) -> str:
    """按固定顺序屏蔽已登记密钥、令牌和长十六进制串。"""
    with _secrets_lock:
        secrets = sorted(_secrets, key=len, reverse=True)
    for secret in secrets:
        text = text.replace(secret, MASK)

    text = _SK_PATTERN.sub(MASK, text)
    text = _BEARER_PATTERN.sub(lambda match: match.group(1) + MASK, text)
    return _HEX_PATTERN.sub(MASK, text)


def redact_obj(value: object, _depth: int = 0) -> object:
    """递归脱敏对象；敏感键整体替换，并安全处理循环引用。"""
    return _redact(value, _depth, set())


def _redact(value: object, depth: int, seen: set[int]) -> object:
    if depth >= MAX_REDACT_DEPTH:
        return "<max-depth>"
    if isinstance(value, str):
        return redact_text(value)

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in seen:
            return "<cycle>"
        seen.add(identity)
        try:
            result: dict[object, object] = {}
            for key, item in value.items():
                safe_key = redact_text(key) if isinstance(key, str) else key
                if isinstance(key, str) and _SENSITIVE_KEY_PATTERN.search(key):
                    result[safe_key] = MASK
                else:
                    result[safe_key] = _redact(item, depth + 1, seen)
            return result
        finally:
            seen.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in seen:
            return "<cycle>"
        seen.add(identity)
        try:
            items = [_redact(item, depth + 1, seen) for item in value]
            return tuple(items) if isinstance(value, tuple) else items
        finally:
            seen.remove(identity)

    if isinstance(value, (set, frozenset)):
        identity = id(value)
        if identity in seen:
            return "<cycle>"
        seen.add(identity)
        try:
            return [_redact(item, depth + 1, seen) for item in value]
        finally:
            seen.remove(identity)

    return value

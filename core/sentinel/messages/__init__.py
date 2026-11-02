"""用户可见中文文案目录与严格渲染。"""

from __future__ import annotations

from collections.abc import Mapping

from . import app, common, trading

INTERNAL_FALLBACK = "发生了意外错误，请重试。"

MESSAGES: dict[str, str] = common.MESSAGES | app.MESSAGES | trading.MESSAGES


class MessageKeyError(Exception):
    """文案键不存在或模板参数不完整。"""


class _TemplateParams(dict[str, object]):
    def __missing__(self, key: str) -> object:
        raise MessageKeyError(f"missing message parameter: {key}")


def _normalize_params(params: Mapping[str, object]) -> dict[str, object]:
    values = dict(params)
    missing = values.get("missing")
    if isinstance(missing, (list, tuple, set, frozenset)):
        labels = [common.MISSING_LABELS.get(str(item), str(item)) for item in missing]
        values["missing"] = "、".join(labels)
    return values


def render(key: str, params: Mapping[str, object] | None = None) -> str:
    """按文案键渲染模板；未知键或缺参数抛 MessageKeyError。"""
    template = MESSAGES.get(key)
    if template is None:
        raise MessageKeyError(f"unknown message key: {key}")

    try:
        return template.format_map(_TemplateParams(_normalize_params(params or {})))
    except MessageKeyError:
        raise
    except (AttributeError, IndexError, KeyError, ValueError) as exc:
        raise MessageKeyError(f"invalid message template: {key}") from exc


__all__ = [
    "INTERNAL_FALLBACK",
    "MESSAGES",
    "MessageKeyError",
    "render",
]

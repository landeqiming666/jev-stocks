"""统一 UTC 时钟与 ISO 8601 转换。"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime


def parse_iso(value: str) -> datetime:
    """解析带时区的 ISO 8601 时刻，并统一转换为 UTC。"""
    if not isinstance(value, str):
        raise ValueError("ISO 8601 value must be a string")

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        moment = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("invalid ISO 8601 value") from exc

    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("ISO 8601 value must include a timezone")
    return moment.astimezone(UTC)


def to_iso(moment: datetime) -> str:
    """把带时区的时刻格式化为以 Z 结尾的 UTC ISO 8601 字符串。"""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def now() -> datetime:
    """返回当前 UTC 时刻；测试可用 SENTINEL_CLOCK 固定。"""
    configured = os.environ.get("SENTINEL_CLOCK")
    if configured is None:
        return datetime.now(UTC)
    return parse_iso(configured)


def utc_today() -> date:
    """返回按 UTC 计算的当前日期。"""
    return now().date()

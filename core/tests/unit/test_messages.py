"""用户文案目录与渲染的单元测试。"""

from __future__ import annotations

import pytest

from sentinel.errors import ErrorCode
from sentinel.messages import INTERNAL_FALLBACK, MessageKeyError, render


def test_render_fills_placeholders() -> None:
    message = render("error.RATE_LIMITED", {"retryAfterSec": 30})

    assert "30" in message


def test_render_unknown_key_raises_message_key_error() -> None:
    with pytest.raises(MessageKeyError):
        render("error.NOPE")


def test_every_error_code_has_message() -> None:
    assert len(ErrorCode) == 15
    for code in ErrorCode:
        assert render(
            f"error.{code}", {"missing": "Jev 密钥", "requestId": "r-1", "retryAfterSec": 30}
        )
    assert render("core.ready")
    assert "意外错误" in INTERNAL_FALLBACK


def test_render_missing_parameter_is_not_filled_with_a_guess() -> None:
    for key in ("error.RATE_LIMITED", "error.CONFIG_REQUIRED", "error.INTERNAL"):
        with pytest.raises(MessageKeyError):
            render(key)


def test_engine_change_message_is_registered_without_fixture_injection() -> None:
    assert render("engine.changed") == "未找到 JEVDB 扩展，已改用 Jev 直连（同一模型）"


def test_unknown_market_cooldown_does_not_guess_seconds() -> None:
    assert render("prices.rate_limited") == "行情源请求过于频繁，请稍后重试。"

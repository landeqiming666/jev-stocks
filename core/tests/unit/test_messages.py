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
        assert render(f"error.{code}")
    assert render("core.ready")
    assert "意外错误" in INTERNAL_FALLBACK

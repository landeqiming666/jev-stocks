"""错误族、错误码与线上格式的单元测试。"""

from __future__ import annotations

import pytest

from sentinel.errors import CancelledError, InternalError, SourceError


def test_internal_error_wire_requires_request_id() -> None:
    with pytest.raises(ValueError):
        InternalError().to_wire()
    with pytest.raises(ValueError):
        InternalError("SOURCE_UNAVAILABLE")


def test_source_error_wire_marks_retryable() -> None:
    wire = SourceError("SOURCE_UNAVAILABLE").to_wire("r-1")

    assert wire["code"] == "SOURCE_UNAVAILABLE"
    assert wire["data"] == {"retryable": True}
    assert "数据源" in wire["message"]
    assert CancelledError().to_wire()["data"] == {"retryable": False}

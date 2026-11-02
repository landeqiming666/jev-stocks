"""统一的错误码、错误族与 RPC 线上错误对象。"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from .messages import INTERNAL_FALLBACK, MessageKeyError, render


class ErrorCode(StrEnum):
    """RPC 契约定义的 15 个错误码。"""

    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    CONFIG_REQUIRED = "CONFIG_REQUIRED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    MODEL_ERROR = "MODEL_ERROR"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    ORDER_REJECTED = "ORDER_REJECTED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    INTERNAL = "INTERNAL"


RETRYABLE: dict[ErrorCode, bool] = {
    ErrorCode.INVALID_ARGUMENT: False,
    ErrorCode.NOT_FOUND: False,
    ErrorCode.CONFLICT: False,
    ErrorCode.CONFIG_REQUIRED: False,
    ErrorCode.UNAUTHENTICATED: False,
    ErrorCode.ENGINE_UNAVAILABLE: False,
    ErrorCode.SOURCE_UNAVAILABLE: True,
    ErrorCode.RATE_LIMITED: True,
    ErrorCode.MODEL_ERROR: True,
    ErrorCode.BUDGET_EXCEEDED: False,
    ErrorCode.DATA_INSUFFICIENT: False,
    ErrorCode.ORDER_REJECTED: False,
    ErrorCode.TIMEOUT: True,
    ErrorCode.CANCELLED: False,
    ErrorCode.INTERNAL: True,
}


class SentinelError(Exception):
    """所有可映射到 RPC 错误的基类。"""

    _allowed_codes = frozenset(ErrorCode)

    def __init__(
        self,
        code: ErrorCode | str,
        message_key: str | None = None,
        *,
        params: Mapping[str, object] | None = None,
        field: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        try:
            normalized_code = ErrorCode(code)
        except ValueError as exc:
            raise ValueError(f"unknown error code: {code}") from exc
        if normalized_code not in self._allowed_codes:
            raise ValueError(f"{type(self).__name__} does not allow {normalized_code}")

        self.code = normalized_code
        self.message_key = message_key
        self.params = dict(params or {})
        self.field = field
        self.reason = reason
        self.detail = detail
        self.retryable = RETRYABLE[normalized_code] if retryable is None else retryable
        super().__init__(normalized_code.value)

    def to_wire(self, request_id: str | None = None) -> dict[str, object]:
        """转换为 05-接口契约 §3.1 的错误对象。"""
        if self.code is ErrorCode.INTERNAL and request_id is None:
            raise ValueError("INTERNAL errors require request_id")

        data: dict[str, object] = {"retryable": self.retryable}
        reserved = {"retryable", "field", "reason", "detail", "requestId"}
        for key, value in self.params.items():
            if key not in reserved:
                data[key] = value
        if self.field is not None:
            data["field"] = self.field
        if self.reason is not None:
            data["reason"] = self.reason
        if self.detail is not None:
            data["detail"] = self.detail

        key = self.message_key or f"error.{self.code}"
        render_params = dict(self.params)
        if self.code is ErrorCode.INTERNAL:
            render_params["requestId"] = request_id
        try:
            message = render(key, render_params)
        except MessageKeyError:
            message = INTERNAL_FALLBACK
            data["detail"] = f"missing message: {key}"

        if self.code is ErrorCode.INTERNAL:
            data["requestId"] = request_id
        return {"code": self.code.value, "message": message, "data": data}


class UserError(SentinelError):
    """调用方可修正的参数、状态或配置错误。"""

    _allowed_codes = frozenset(
        {
            ErrorCode.INVALID_ARGUMENT,
            ErrorCode.NOT_FOUND,
            ErrorCode.CONFLICT,
            ErrorCode.CONFIG_REQUIRED,
            ErrorCode.ORDER_REJECTED,
            ErrorCode.DATA_INSUFFICIENT,
        }
    )


class SourceError(SentinelError):
    """外部数据源错误。"""

    _allowed_codes = frozenset(
        {ErrorCode.SOURCE_UNAVAILABLE, ErrorCode.RATE_LIMITED, ErrorCode.TIMEOUT}
    )


class EngineError(SentinelError):
    """Jev 引擎错误。"""

    _allowed_codes = frozenset(
        {
            ErrorCode.UNAUTHENTICATED,
            ErrorCode.ENGINE_UNAVAILABLE,
            ErrorCode.MODEL_ERROR,
            ErrorCode.BUDGET_EXCEEDED,
        }
    )


class InternalError(SentinelError):
    """不可归因于调用方的内部错误。"""

    _allowed_codes = frozenset({ErrorCode.INTERNAL})

    def __init__(
        self,
        code: ErrorCode | str = ErrorCode.INTERNAL,
        message_key: str | None = None,
        *,
        params: Mapping[str, object] | None = None,
        field: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(
            code,
            message_key,
            params=params,
            field=field,
            reason=reason,
            detail=detail,
            retryable=retryable,
        )


class CancelledError(SentinelError):
    """请求被用户或父进程取消。"""

    _allowed_codes = frozenset({ErrorCode.CANCELLED})

    def __init__(
        self,
        code: ErrorCode | str = ErrorCode.CANCELLED,
        message_key: str | None = None,
        *,
        params: Mapping[str, object] | None = None,
        field: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(
            code,
            message_key,
            params=params,
            field=field,
            reason=reason,
            detail=detail,
            retryable=retryable,
        )

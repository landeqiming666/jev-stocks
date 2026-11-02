from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ValidationError

from sentinel.errors import InternalError, SentinelError, UserError
from sentinel.logging_setup import get_logger, log_event

from .cancel import CancelToken
from .protocol import METHOD_PATTERN, failure, serialize, success

Handler = Callable[[BaseModel, "RequestContext"], BaseModel | dict[str, object]]


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    method: str
    cancel: CancelToken
    started_at: datetime


@dataclass(frozen=True)
class MethodSpec:
    method: str
    handler: Handler
    params_model: type[BaseModel]
    result_model: type[BaseModel] | None
    timeout_ms: int = 30_000
    cancellable: bool = False


class Dispatcher:
    def __init__(self) -> None:
        self._specs: dict[str, MethodSpec] = {}

    def register(
        self,
        method: str,
        handler: Handler,
        params_model: type[BaseModel],
        result_model: type[BaseModel] | None = None,
        timeout_ms: int = 30_000,
        *,
        cancellable: bool = False,
        replace: bool = False,
    ) -> None:
        if not re.fullmatch(METHOD_PATTERN, method) or timeout_ms <= 0:
            raise ValueError("invalid method specification")
        if method in self._specs and not replace:
            raise ValueError("duplicate method")
        self._specs[method] = MethodSpec(
            method,
            handler,
            params_model,
            result_model,
            timeout_ms,
            cancellable,
        )

    def lookup(self, method: str) -> MethodSpec | None:
        return self._specs.get(method)

    def methods(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def dispatch(
        self,
        spec: MethodSpec | None,
        raw_params: object,
        ctx: RequestContext,
    ) -> dict[str, object]:
        try:
            if spec is None:
                raise UserError("INVALID_ARGUMENT", reason="UNKNOWN_METHOD")
            if not isinstance(raw_params, dict):
                raise UserError("INVALID_ARGUMENT", field="params")
            try:
                params = spec.params_model.model_validate(raw_params, strict=True, extra="forbid")
            except ValidationError as exc:
                field = ".".join(str(part) for part in exc.errors()[0]["loc"])
                raise UserError("INVALID_ARGUMENT", field=field) from exc
            if spec.cancellable:
                ctx.cancel.raise_if_cancelled()
            result = spec.handler(params, ctx)
            if spec.result_model is not None:
                result = spec.result_model.model_validate(result, strict=True, extra="forbid")
            if isinstance(result, BaseModel):
                result = result.model_dump(mode="json", by_alias=True)
            if not isinstance(result, dict):
                raise TypeError("RPC result must be an object")
            response = success(ctx.request_id, result)
            serialize(response)
            return response
        except SentinelError as exc:
            try:
                response = failure(ctx.request_id, exc)
                serialize(response)
                return response
            except Exception as wire_exc:
                return self._internal(ctx, wire_exc)
        except ValidationError as exc:
            field = ".".join(str(part) for part in exc.errors()[0]["loc"])
            return failure(ctx.request_id, UserError("INVALID_ARGUMENT", field=field))
        except Exception as exc:
            return self._internal(ctx, exc)

    def _internal(self, ctx: RequestContext, exc: Exception) -> dict[str, object]:
        log_event(
            get_logger(__name__),
            logging.ERROR,
            event="rpc.dispatch.internal",
            request_id=ctx.request_id,
            method=ctx.method,
            error_code="INTERNAL",
            detail=type(exc).__name__,
        )
        return failure(ctx.request_id, InternalError(detail=type(exc).__name__))

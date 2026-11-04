"""RPC adapters for ``demo.load`` and ``demo.clear``."""

from __future__ import annotations

from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from sentinel.rpc.dispatcher import Handler, RequestContext

from .service import DemoCounts, DemoLoadResult, DemoService


class _WireModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )


class DemoLoadParams(_WireModel):
    pass


class DemoClearParams(_WireModel):
    pass


class OkResult(_WireModel):
    ok: bool


class HandlerRegistrar(Protocol):
    def register(
        self,
        method: str,
        handler: Handler,
        params_model: type[BaseModel],
        result_model: type[BaseModel] | None = None,
        timeout_ms: int = 30_000,
    ) -> None: ...


def demo_load(params: DemoLoadParams, ctx: RequestContext, service: DemoService) -> DemoLoadResult:
    return DemoLoadResult(loaded=True, counts=service.load())


def demo_clear(params: DemoClearParams, ctx: RequestContext, service: DemoService) -> OkResult:
    service.clear()
    return OkResult(ok=True)


def register_handlers(registrar: HandlerRegistrar, service: DemoService) -> None:
    def load(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return demo_load(cast(DemoLoadParams, params), ctx, service)

    def clear(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return demo_clear(cast(DemoClearParams, params), ctx, service)

    for method, handler, params_model, result_model in (
        ("demo.load", load, DemoLoadParams, DemoLoadResult),
        ("demo.clear", clear, DemoClearParams, OkResult),
    ):
        registrar.register(method, handler, params_model, result_model)


__all__ = [
    "DemoClearParams",
    "DemoCounts",
    "DemoLoadParams",
    "DemoLoadResult",
    "OkResult",
    "demo_clear",
    "demo_load",
    "register_handlers",
]

from __future__ import annotations

from typing import Protocol, cast

from pydantic import BaseModel

from sentinel import clock
from sentinel.rpc.dispatcher import Handler, RequestContext

from .models import (
    EmptyParams,
    HoldingIdParams,
    HoldingsListResult,
    HoldingUpsertParams,
    HoldingView,
    OkResult,
    ThesisCreateParams,
    ThesisIdParams,
    ThesisListParams,
    ThesisListResult,
    ThesisUpdateParams,
    ThesisVersionsResult,
    ThesisView,
)
from .service import PortfolioService


class HandlerRegistrar(Protocol):
    def register(
        self,
        method: str,
        handler: Handler,
        params_model: type[BaseModel],
        result_model: type[BaseModel] | None = None,
        timeout_ms: int = 30_000,
    ) -> None: ...


def register_handlers(registrar: HandlerRegistrar, service: PortfolioService) -> None:
    def holdings_list(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return HoldingsListResult(items=service.list_holdings(), as_of=clock.to_iso(clock.now()))

    def upsert(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(HoldingUpsertParams, params)
        return service.upsert_holding(p.instrument_id, p.quantity, p.avg_cost, p.note)

    def archive_holding(params: BaseModel, ctx: RequestContext) -> BaseModel:
        service.archive_holding(cast(HoldingIdParams, params).instrument_id)
        return OkResult(ok=True)

    def theses_list(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(ThesisListParams, params)
        return ThesisListResult(items=service.list_theses(p.instrument_id, p.status))

    def create(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(ThesisCreateParams, params)
        return service.create_thesis(p.instrument_id, p.statement, p.kill_condition)

    def update(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(ThesisUpdateParams, params)
        return service.update_thesis(p.thesis_id, p.statement, p.kill_condition, p.expected_version)

    def archive_thesis(params: BaseModel, ctx: RequestContext) -> BaseModel:
        service.archive_thesis(cast(ThesisIdParams, params).thesis_id)
        return OkResult(ok=True)

    def versions(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return ThesisVersionsResult(
            items=service.list_versions(cast(ThesisIdParams, params).thesis_id)
        )

    for method, handler, params_model, result_model in (
        ("holdings.list", holdings_list, EmptyParams, HoldingsListResult),
        ("holdings.upsert", upsert, HoldingUpsertParams, HoldingView),
        ("holdings.archive", archive_holding, HoldingIdParams, OkResult),
        ("thesis.list", theses_list, ThesisListParams, ThesisListResult),
        ("thesis.create", create, ThesisCreateParams, ThesisView),
        ("thesis.update", update, ThesisUpdateParams, ThesisView),
        ("thesis.archive", archive_thesis, ThesisIdParams, OkResult),
        ("thesis.versions", versions, ThesisIdParams, ThesisVersionsResult),
    ):
        registrar.register(method, handler, params_model, result_model)

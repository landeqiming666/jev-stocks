from __future__ import annotations

from typing import Protocol, cast

from pydantic import BaseModel

from sentinel import clock
from sentinel.rpc.dispatcher import Handler, RequestContext

from .models import (
    BatchParams,
    HistoryParams,
    OkResult,
    RunParams,
    ScanBatchView,
    ScanDetailView,
    ScanHistoryPage,
    ScanRunView,
    StartParams,
    StartResult,
)
from .orchestrator import ScanService


class HandlerRegistrar(Protocol):
    def register(
        self,
        method: str,
        handler: Handler,
        params_model: type[BaseModel],
        result_model: type[BaseModel] | None = None,
        timeout_ms: int = 30_000,
        *,
        cancellable: bool = False,
    ) -> None: ...


def register_handlers(registrar: HandlerRegistrar, service: ScanService) -> None:
    def start(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(StartParams, params)
        return StartResult(
            run_id=service.start(p.market, clock.parse_iso(p.from_) if p.from_ else None)
        )

    def cancel(params: BaseModel, ctx: RequestContext) -> BaseModel:
        service.cancel(cast(RunParams, params).run_id)
        return OkResult(ok=True)

    def status(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return service.status(cast(RunParams, params).run_id)

    def history(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(HistoryParams, params)
        return service.history(p.limit, p.cursor)

    def detail(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return service.detail(cast(RunParams, params).run_id)

    def retry(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return service.retry_batch(cast(BatchParams, params).batch_id, ctx.cancel)

    for method, handler, inputs, output, timeout, cancellable in (
        ("scan.start", start, StartParams, StartResult, 30_000, False),
        ("scan.cancel", cancel, RunParams, OkResult, 30_000, False),
        ("scan.status", status, RunParams, ScanRunView, 30_000, False),
        ("scan.history", history, HistoryParams, ScanHistoryPage, 30_000, False),
        ("scan.detail", detail, RunParams, ScanDetailView, 30_000, False),
        ("scan.retryBatch", retry, BatchParams, ScanBatchView, 60_000, True),
    ):
        registrar.register(method, handler, inputs, output, timeout, cancellable=cancellable)

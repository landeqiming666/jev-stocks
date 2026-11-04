from __future__ import annotations

from typing import Protocol, cast

from pydantic import BaseModel

from sentinel.rpc.dispatcher import Handler, RequestContext

from .account import PaperService
from .models import (
    AccountIdParams,
    AdvanceResult,
    CancelOrderParams,
    CreateAccountParams,
    EmptyParams,
    OkResult,
    OrdersParams,
    PaperAccountsResult,
    PaperAccountView,
    PaperOrderPage,
    PaperOrderView,
    PlaceOrderParams,
    PortfolioView,
    ResetParams,
)
from .rules import OrderIntent


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


def register_handlers(registrar: HandlerRegistrar, service: PaperService) -> None:
    def accounts(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return PaperAccountsResult(items=service.list_accounts())

    def create(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(CreateAccountParams, params)
        return service.create_account(p.name, p.initial_cash, p.start_date)

    def portfolio(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return service.portfolio(cast(AccountIdParams, params).account_id)

    def place(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(PlaceOrderParams, params)
        return service.place_order(
            OrderIntent(
                p.account_id, p.instrument_id, p.side, p.quantity, p.order_type, p.idempotency_key
            )
        )

    def cancel(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return service.cancel_order(cast(CancelOrderParams, params).order_id)

    def orders(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(OrdersParams, params)
        return service.list_orders(p.account_id, p.status, p.limit, p.cursor, p.idempotency_key)

    def advance(params: BaseModel, ctx: RequestContext) -> BaseModel:
        return service.advance(cast(AccountIdParams, params).account_id)

    def reset(params: BaseModel, ctx: RequestContext) -> BaseModel:
        p = cast(ResetParams, params)
        service.reset(p.account_id, p.confirm_text)
        return OkResult(ok=True)

    for method, handler, params_model, result_model in (
        ("paper.accounts", accounts, EmptyParams, PaperAccountsResult),
        ("paper.createAccount", create, CreateAccountParams, PaperAccountView),
        ("paper.portfolio", portfolio, AccountIdParams, PortfolioView),
        ("paper.order.place", place, PlaceOrderParams, PaperOrderView),
        ("paper.order.cancel", cancel, CancelOrderParams, PaperOrderView),
        ("paper.orders", orders, OrdersParams, PaperOrderPage),
        ("paper.advance", advance, AccountIdParams, AdvanceResult),
        ("paper.reset", reset, ResetParams, OkResult),
    ):
        registrar.register(method, handler, params_model, result_model, cancellable=False)

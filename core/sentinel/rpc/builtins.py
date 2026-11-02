from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from sentinel import clock

from .dispatcher import Dispatcher, RequestContext

PING_METHOD = "app.ping"
SHUTDOWN_METHOD = "app.shutdown"


class EmptyParams(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class ShutdownParams(EmptyParams):
    force: bool = False


class OkResult(BaseModel):
    ok: bool


class PingResult(OkResult):
    uptime_ms: int = Field(alias="uptimeMs", ge=0)


def register_builtins(dispatcher: Dispatcher, started_at: datetime) -> None:
    def ping(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        return {
            "ok": True,
            "uptimeMs": max(0, int((clock.now() - started_at).total_seconds() * 1000)),
        }

    def shutdown(params: BaseModel, ctx: RequestContext) -> dict[str, object]:
        return {"ok": True}

    if dispatcher.lookup(PING_METHOD) is None:
        dispatcher.register(PING_METHOD, ping, EmptyParams, PingResult)
    if dispatcher.lookup(SHUTDOWN_METHOD) is None:
        dispatcher.register(SHUTDOWN_METHOD, shutdown, ShutdownParams, OkResult)

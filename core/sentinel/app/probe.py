"""连接探针：只读引擎健康与 SEC 可达性，不发送持仓或逻辑内容。"""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from sentinel import __version__
from sentinel.http import HttpClient
from sentinel.markets.instruments.source import TICKERS_URL
from sentinel.settings.models import MODEL_ID, ProbeResult

from .engines import EngineRuntime

SEC_HOST = "www.sec.gov"


class EngineProbe:
    """C-04 的 ConnectionProbe 实现。"""

    def __init__(
        self,
        runtime: EngineRuntime,
        *,
        http: HttpClient,
        offline: bool,
    ) -> None:
        self._runtime, self._http, self._offline = runtime, http, offline

    @staticmethod
    def _ms(started: float) -> int:
        return max(0, int((time.monotonic() - started) * 1000))

    def check_jev(self, model_id: str) -> ProbeResult:
        if self._offline:
            return ProbeResult(ok=False, message="")
        if model_id != MODEL_ID:
            return ProbeResult(ok=False, message="")
        started = time.monotonic()
        _, state = self._runtime.health()
        return ProbeResult(ok=state == "ok", latency_ms=self._ms(started), message="")

    def check_sec(self, email: str) -> ProbeResult:
        if self._offline or not isinstance(email, str) or "@" not in email:
            return ProbeResult(ok=False, message="")
        if urlsplit(TICKERS_URL).hostname != SEC_HOST:  # 防御性：只允许官方域名
            return ProbeResult(ok=False, message="")
        started = time.monotonic()
        try:
            response = self._http.get(
                TICKERS_URL,
                source="sec",
                headers={
                    "User-Agent": f"Sentinel/{__version__} {email}",
                    "Accept": "application/json",
                },
                use_cache=True,
            )
        except Exception:
            return ProbeResult(ok=False, message="")
        return ProbeResult(ok=response.status == 200, latency_ms=self._ms(started), message="")

    def check_jevdb(self) -> ProbeResult:
        if self._offline or not self._runtime.jevdb_available():
            return ProbeResult(ok=False, message="")
        started = time.monotonic()
        try:
            loaded = self._runtime.load_jevdb()
        except Exception:
            loaded = False
        return ProbeResult(ok=loaded, latency_ms=self._ms(started), message="")


__all__ = ["EngineProbe"]

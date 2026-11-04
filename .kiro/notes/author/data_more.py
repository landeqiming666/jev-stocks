"""示例数据（二）：模拟交易、风险、设置、清单、启动信息。"""
from __future__ import annotations

import math
from decimal import Decimal

from data import (
    D, EV, HOLDINGS, HOLD_BY, INST, LAST_SCAN_END, LAST_TRADING_DAY, MODEL_ID, NOW, R1, R2, TH, dec, ulid,
)

# ---------------------------------------------------------------- 数据状态与启动
DATA_STATUS_OK = {
    "market": "us", "marketState": "closed", "nextOpenAt": "2026-11-02T14:30:00Z",
    "source": {"name": "SEC EDGAR", "state": "ok", "lastSuccessAt": LAST_SCAN_END, "message": None},
    "engine": {"active": "jev_direct", "modelId": MODEL_ID, "state": "ok"},
    "budget": {"usedTokens": 18420, "limitTokens": 2000000, "resetAt": "2026-11-03T00:00:00Z"},
    "offline": False,
}


def with_status(**overrides):
    s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DATA_STATUS_OK.items()}
    for k, v in overrides.items():
        s[k] = v
    return s


BOOTSTRAP_READY = {
    "protocolVersion": "1.0", "appVersion": "0.1.0", "dbSchemaVersion": 1, "platform": "macos",
    "engine": {"requested": "auto", "active": "jev_direct", "modelId": MODEL_ID, "jevdbAvailable": False},
    "markets": ["us"], "configured": {"jevKey": True, "secEmail": True},
    "demoDataLoaded": True, "offline": False, "now": NOW,
}


def bootstrap(**kw):
    b = dict(BOOTSTRAP_READY)
    b["engine"] = dict(b["engine"])
    b["configured"] = dict(b["configured"])
    for k, v in kw.items():
        b[k] = v
    return b


# ---------------------------------------------------------------- 清单
def scan_brief(r):
    return {"runId": r["runId"], "status": r["status"], "finishedAt": r["finishedAt"],
            "stats": {k: r["stats"][k] for k in ("instruments", "skippedNoThesis", "filings", "passages", "decisions")},
            "error": r["error"]}


def acted(d, action, note=None, when="2026-11-02T00:37:00Z"):
    c = dict(d)
    c["action"] = {"action": action, "note": note, "actedAt": when}
    return c


def inbox(items, uncertain, processed, last_scan, status, setup):
    return {
        "asOf": NOW,
        "summary": {
            "pendingCount": len(items),
            "overturnCount": sum(1 for i in items if i["relation"] == "overturn"),
            "weakenCount": sum(1 for i in items if i["relation"] == "weaken"),
            "uncertainCount": len(uncertain), "processedCount": len(processed),
        },
        "items": items, "uncertain": uncertain, "processed": processed,
        "lastScan": last_scan, "dataStatus": status, "setup": setup,
    }


SETUP_FULL = {"holdings": 6, "activeTheses": 5, "scannableInstruments": 4}
PENDING_ITEMS = sorted([D["d1"], D["d2"], D["d3"]], key=lambda d: (0 if d["relation"] == "overturn" else 1, -d["headline"]))
INBOX_PENDING = inbox(PENDING_ITEMS, [D["d4"], D["d5"]], [D["d6"]], scan_brief(R1), DATA_STATUS_OK, SETUP_FULL)
INBOX_EMPTY = inbox(
    [], [], [acted(D["d1"], "exit_intent", "先观察一周"), acted(D["d2"], "revise"), acted(D["d3"], "ignore"), D["d6"]],
    scan_brief(R1), DATA_STATUS_OK, SETUP_FULL)
FAILED_RUN = dict(R2)
FAILED_RUN = {
    "runId": ulid(9, 4), "status": "failed", "finishedAt": "2026-11-02T00:36:02Z",
    "stats": {"instruments": 0, "skippedNoThesis": 0, "filings": 0, "passages": 0, "decisions": 0},
    "error": {"code": "SOURCE_UNAVAILABLE", "message": "无法连接 SEC，请检查网络后重试。已显示 11 月 2 日 08:31 的结果。"},
}
INBOX_SCAN_FAILED = inbox(
    PENDING_ITEMS, [D["d4"], D["d5"]], [D["d6"]], FAILED_RUN,
    with_status(source={"name": "SEC EDGAR", "state": "down", "lastSuccessAt": LAST_SCAN_END,
                        "message": "SEC 暂时无法访问，当前显示的是 11 月 2 日 08:31 的结果"}),
    SETUP_FULL)
INBOX_NO_HOLDINGS = inbox([], [], [], None, with_status(budget={"usedTokens": 0, "limitTokens": 2000000, "resetAt": "2026-11-03T00:00:00Z"}),
                          {"holdings": 0, "activeTheses": 0, "scannableInstruments": 0})
INBOX_NEVER_SCANNED = inbox([], [], [], None, DATA_STATUS_OK | {"budget": {"usedTokens": 0, "limitTokens": 2000000, "resetAt": "2026-11-03T00:00:00Z"}}, SETUP_FULL)
INBOX_OFFLINE = inbox(PENDING_ITEMS, [D["d4"], D["d5"]], [D["d6"]], scan_brief(R1),
                      with_status(offline=True, source={"name": "SEC EDGAR", "state": "down", "lastSuccessAt": LAST_SCAN_END, "message": "当前离线"}),
                      SETUP_FULL)

# ---------------------------------------------------------------- 模拟交易
ACCOUNT = {
    "accountId": ulid(1, 6), "name": "回放账户 A", "baseCurrency": "USD",
    "initialCash": "100000.0000", "startDate": "2026-09-01", "clockDate": "2026-10-14",
    "createdAt": "2026-10-30T02:00:00Z",
}


def fill(n, on, price, qty, fee="0.0000"):
    amount = dec(Decimal(price) * qty, 4)
    return {"fillId": ulid(n, 7), "filledOn": on, "price": price, "quantity": qty, "amount": amount, "fee": fee}


def order(n, symbol, side, qty, status, created, fills=None, reject=None, reserved=None, est=None):
    return {
        "orderId": ulid(n, 8), "accountId": ACCOUNT["accountId"], "instrument": INST[symbol],
        "side": side, "quantity": qty, "orderType": "market_open", "status": status,
        "rejectReason": reject, "createdClockDate": created, "reservedCash": reserved,
        "idempotencyKey": "idem-%03d" % n, "fills": fills or [],
        "estimate": est,
    }


O1 = order(1, "ZZFD", "buy", 200, "filled", "2026-09-01", [fill(1, "2026-09-02", "22.411200", 200)])
O2 = order(2, "ZZAR", "buy", 50, "filled", "2026-09-14", [fill(2, "2026-09-15", "49.824900", 50)])
O3 = order(3, "ZZCL", "sell", 500, "rejected", "2026-10-13",
           reject={"code": "INSUFFICIENT_POSITION", "message": "可卖数量不足：持仓 0 股，要卖出 500 股。"})
O4 = order(4, "ZZCL", "buy", 100, "pending", "2026-10-14", reserved="2841.4200",
           est={"price": "28.414200", "amount": "2841.4200", "fee": "0.0000"})

POSITIONS = [
    {"instrument": INST["ZZFD"], "quantity": 200, "sellableQuantity": 200, "avgCost": "22.411200", "lastClose": 22.95,
     "marketValue": "4590.0000", "unrealizedPnl": "107.7600", "unrealizedPnlPct": round(22.95 / 22.4112 - 1, 4)},
    {"instrument": INST["ZZAR"], "quantity": 50, "sellableQuantity": 50, "avgCost": "49.824900", "lastClose": 51.10,
     "marketValue": "2555.0000", "unrealizedPnl": "63.7550", "unrealizedPnlPct": round(51.10 / 49.8249 - 1, 4)},
]
CASH = Decimal("100000.0000") - Decimal("4482.2400") - Decimal("2491.2450")
PORTFOLIO = {
    "account": ACCOUNT, "cash": dec(CASH), "reservedCash": "2841.4200", "availableCash": dec(CASH - Decimal("2841.4200")),
    "positions": POSITIONS, "equity": dec(CASH + Decimal("4590.0000") + Decimal("2555.0000")),
    "asOf": ACCOUNT["clockDate"], "pendingOrders": 1,
}
PORTFOLIO_NEW = {
    "account": dict(ACCOUNT, accountId=ulid(2, 6), name="新账户", clockDate="2026-09-01", initialCash="50000.0000"),
    "cash": "50000.0000", "reservedCash": "0.0000", "availableCash": "50000.0000", "positions": [],
    "equity": "50000.0000", "asOf": "2026-09-01", "pendingOrders": 0,
}
_est = Decimal("51.10") * Decimal("1.0005") * 1800
ORDER_ERR_CASH = {
    "code": "ORDER_REJECTED",
    "message": "资金不足：预计需要 $%s，可用现金 $%s。" % (format(_est.quantize(Decimal("0.01")), ","), format(Decimal(PORTFOLIO["availableCash"]).quantize(Decimal("0.01")), ",")),
    "data": {"reason": "INSUFFICIENT_CASH", "retryable": False,
             "required": dec(_est), "available": PORTFOLIO["availableCash"]},
}
O4_FILLED = dict(O4, status="filled", reservedCash=None, fills=[fill(4, "2026-10-15", "28.564275", 100)])
ADVANCE_RESULT = {
    "clockDate": "2026-10-15", "tradingDay": True, "filled": [O4_FILLED], "rejected": [], "pendingRemaining": 0,
    "portfolio": dict(PORTFOLIO, account=dict(ACCOUNT, clockDate="2026-10-15"), reservedCash="0.0000",
                      cash=dec(CASH - Decimal("2856.4275")), availableCash=dec(CASH - Decimal("2856.4275")), pendingOrders=0),
}

# ---------------------------------------------------------------- 风险
SYMS = ["ZZAR", "ZZFD", "ZZCL", "ZZBK", "ZZEN"]
CORR = [
    [1.00, 0.21, 0.58, 0.34, 0.12],
    [0.21, 1.00, 0.09, 0.27, 0.31],
    [0.58, 0.09, 1.00, 0.22, -0.05],
    [0.34, 0.27, 0.22, 1.00, 0.41],
    [0.12, 0.31, -0.05, 0.41, 1.00],
]


def cholesky_ok(m):
    n = len(m)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                v = m[i][i] - s
                if v <= 1e-9:
                    return False
                L[i][j] = math.sqrt(v)
            else:
                L[i][j] = (m[i][j] - s) / L[j][j]
    return True


assert cholesky_ok(CORR), "相关矩阵不是正定的"

_mv = {s: Decimal(HOLD_BY[s]["marketValue"]) for s in SYMS}
_tot = sum(_mv.values())
WEIGHTS = {s: float(_mv[s] / _tot) for s in SYMS}
EFF = 1.0 / sum(w * w for w in WEIGHTS.values())
_top = sorted(WEIGHTS.items(), key=lambda kv: -kv[1])[:3]
LOADINGS = [("ZZAR", 0.55), ("ZZCL", 0.50), ("ZZBK", 0.47), ("ZZEN", 0.40), ("ZZFD", 0.26)]
assert abs(sum(v * v for _, v in LOADINGS) - 1) < 0.01
EXPLAINED = [0.46, 0.22, 0.15, 0.10, 0.07]
assert abs(sum(EXPLAINED) - 1) < 1e-9
RISK_OK = {
    "asOf": LAST_TRADING_DAY,
    "window": {"label": "1Y", "from": "2025-10-30", "to": LAST_TRADING_DAY, "observations": 251},
    "currency": "USD", "annualizedVol": 0.187, "maxDrawdown": 0.214,
    "effectiveHoldings": round(EFF, 2),
    "topWeights": [{"instrumentId": "us:" + s, "symbol": s, "weight": round(w, 4)} for s, w in _top],
    "correlation": {"instrumentIds": ["us:" + s for s in SYMS], "symbols": SYMS, "matrix": CORR},
    "svd": {"explained": EXPLAINED, "loadings": [{"symbol": s, "value": v} for s, v in LOADINGS]},
    "conditionNumberRaw": 14.8, "conditionNumberShrunk": 9.3,
    "warnings": [], "excluded": [{"instrumentId": "us:ZZMD", "symbol": "ZZMD", "reason": "只关注，数量为 0，不计入权重"}],
}
RISK_INSUFFICIENT = {
    "code": "DATA_INSUFFICIENT",
    "message": "样本不足：共同交易日 42 天，至少需要 60 天。",
    "data": {"retryable": False, "observations": 42, "required": 60},
}

# ---------------------------------------------------------------- 设置
SETTINGS = {
    "engine": "auto", "modelId": MODEL_ID, "secContactEmail": "name@example.com",
    "dailyTokenBudget": 2000000, "firstScanLookbackDays": 7, "demoDataLoaded": True,
    "language": "zh-CN",
    "allowedDomains": [
        {"domain": "api.typesafe.ai", "purpose": "Jev 判定", "sends": "逻辑正文、失效条件、披露段落；不含持仓数量、成本、备注"},
        {"domain": "www.sec.gov", "purpose": "披露与标的表", "sends": "请求 URL 与含联系邮箱的 User-Agent"},
        {"domain": "data.sec.gov", "purpose": "披露与标的表", "sends": "请求 URL 与含联系邮箱的 User-Agent"},
        {"domain": "web.ifzq.gtimg.cn", "purpose": "日线行情（主源，覆盖美股/港股/A 股）", "sends": "股票代码与市场前缀"},
        {"domain": "api.nasdaq.com", "purpose": "日线行情（美股备源）", "sends": "股票代码"},
    ],
}
SETTINGS_EMPTY = dict(SETTINGS, secContactEmail=None, demoDataLoaded=False)
SECRETS_OK = {"jevKey": True}
SECRETS_NONE = {"jevKey": False}
TEST_OK = {
    "ok": True, "engine": "jev_direct", "modelId": MODEL_ID,
    "checks": [
        {"name": "Jev", "ok": True, "latencyMs": 412, "message": "模型 jev-1.14.0 可用"},
        {"name": "SEC", "ok": True, "latencyMs": 236, "message": "data.sec.gov 可访问"},
        {"name": "JEVDB", "ok": False, "latencyMs": None, "message": "未找到 JEVDB 扩展，已使用 Jev 直连（同一模型）"},
    ],
}
TEST_FAILED = {
    "ok": False, "engine": "jev_direct", "modelId": MODEL_ID,
    "checks": [
        {"name": "Jev", "ok": False, "latencyMs": None, "message": "密钥无效（401）。请重新填写 Jev 密钥。"},
        {"name": "SEC", "ok": True, "latencyMs": 251, "message": "data.sec.gov 可访问"},
        {"name": "JEVDB", "ok": False, "latencyMs": None, "message": "未找到 JEVDB 扩展，已使用 Jev 直连（同一模型）"},
    ],
}

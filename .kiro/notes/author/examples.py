"""把示例数据组织成 EXAMPLES[方法名][示例名] = {"params": ..., "result": ...} 或 {"params": ..., "error": ...}。

这是原型 mock.js 与 contracts/ 里 examples 的唯一来源。
"""
from __future__ import annotations

import copy

import data as d
import data_more as m


def ok(params, result):
    return {"params": params, "result": result}


def err(params, code, message, **data):
    e = {"code": code, "message": message}
    e["data"] = dict({"retryable": code in ("SOURCE_UNAVAILABLE", "RATE_LIMITED", "MODEL_ERROR", "TIMEOUT", "INTERNAL")}, **data)
    return {"params": params, "error": e}


EX: dict = {}


def put(method, name, value):
    EX.setdefault(method, {})[name] = value


# ---- 生命周期 -------------------------------------------------------
put("app.ping", "ok", ok({}, {"ok": True, "uptimeMs": 183420}))
put("app.shutdown", "ok", ok({}, {"ok": True}))
put("app.bootstrap", "ready", ok({}, m.BOOTSTRAP_READY))
put("app.bootstrap", "unconfigured", ok({}, m.bootstrap(configured={"jevKey": False, "secEmail": False}, demoDataLoaded=False)))
put("app.bootstrap", "engine_fallback", ok({}, m.bootstrap(engine={"requested": "jevdb", "active": "jev_direct", "modelId": d.MODEL_ID, "jevdbAvailable": False})))
put("app.bootstrap", "offline", ok({}, m.bootstrap(offline=True)))
put("app.bootstrap", "windows", ok({}, m.bootstrap(platform="windows")))

# ---- 设置与密钥 -----------------------------------------------------
put("settings.get", "configured", ok({}, m.SETTINGS))
put("settings.get", "unconfigured", ok({}, m.SETTINGS_EMPTY))
put("settings.update", "ok", ok({"secContactEmail": "name@example.com", "dailyTokenBudget": 2000000}, m.SETTINGS))
put("settings.update", "invalid_email", err({"secContactEmail": "not-an-email"}, "INVALID_ARGUMENT", "联系邮箱格式不正确", field="secContactEmail"))
put("settings.testConnection", "ok", ok({}, m.TEST_OK))
put("settings.testConnection", "failed", ok({}, m.TEST_FAILED))
put("secrets.set", "ok", ok({"name": "jevKey", "value": "<secret>"}, {"ok": True}))
put("secrets.clear", "ok", ok({"name": "jevKey"}, {"ok": True}))
put("secrets.status", "configured", ok({}, m.SECRETS_OK))
put("secrets.status", "none", ok({}, m.SECRETS_NONE))

# ---- 标的与持仓 -----------------------------------------------------
put("instruments.search", "ze", ok({"query": "ze", "limit": 20},
    {"items": [d.INST["ZZAR"], d.INST["ZZEN"], d.INST["ZZMD"], d.INST_EXTRA["ZZNW"]]}))
put("instruments.search", "empty", ok({"query": "qqqq", "limit": 20}, {"items": []}))
put("holdings.list", "default", ok({}, {"items": d.HOLDINGS, "asOf": d.NOW}))
put("holdings.list", "empty", ok({}, {"items": [], "asOf": d.NOW}))
put("holdings.upsert", "ok", ok({"instrumentId": "us:ZZAR", "quantity": "120", "avgCost": "48.20", "note": "核心仓位"}, d.HOLD_BY["ZZAR"]))
put("holdings.upsert", "negative", err({"instrumentId": "us:ZZAR", "quantity": "-5"}, "INVALID_ARGUMENT", "数量不能为负数", field="quantity"))
put("holdings.archive", "ok", ok({"instrumentId": "us:ZZMD"}, {"ok": True}))
put("prices.refresh", "ok", ok({"instrumentIds": ["us:ZZAR"]}, {"updated": 1, "failed": [], "asOf": d.LAST_TRADING_DAY}))
put("prices.refresh", "offline", err({}, "SOURCE_UNAVAILABLE", "行情源暂时无法访问，已使用 10 月 30 日的收盘价。"))

# ---- 投资逻辑 -------------------------------------------------------
zzar = [d.TH["t1"], d.TH["t2"]]
put("thesis.list", "zzar", ok({"instrumentId": "us:ZZAR", "status": "active"}, {"items": zzar}))
put("thesis.list", "zzfd", ok({"instrumentId": "us:ZZFD", "status": "active"}, {"items": [d.TH["t3"]]}))
put("thesis.list", "zzcl", ok({"instrumentId": "us:ZZCL", "status": "active"}, {"items": [d.TH["t4"]]}))
put("thesis.list", "zzbk", ok({"instrumentId": "us:ZZBK", "status": "active"}, {"items": [d.TH["t5"]]}))
put("thesis.list", "empty", ok({"instrumentId": "us:ZZMD", "status": "active"}, {"items": []}))
new_t = d.thesis(6, "ZZEN", "油价高位时公司现金流保持充裕", "资本开支超过经营现金流", 1, 1, d.NOW, d.NOW)
put("thesis.create", "ok", ok({"instrumentId": "us:ZZEN", "statement": new_t["statement"], "killCondition": new_t["killCondition"]}, new_t))
put("thesis.create", "empty", err({"instrumentId": "us:ZZEN", "statement": "   "}, "INVALID_ARGUMENT", "逻辑内容不能为空", field="statement"))
put("thesis.create", "too_long", err({"instrumentId": "us:ZZEN", "statement": "字" * 501}, "INVALID_ARGUMENT", "逻辑最多 500 字，当前 501 字", field="statement", length=501, max=500))
put("thesis.create", "limit_reached", err({"instrumentId": "us:ZZAR", "statement": "第六条逻辑"}, "INVALID_ARGUMENT", "每只股票最多 5 条有效逻辑", field="instrumentId", max=5))
t1b = copy.deepcopy(d.TH["t1"]); t1b.update(version=3, versionCount=3, statement="控股股东长期持股，不会大幅减持或质押股份", updatedAt=d.NOW)
put("thesis.update", "ok", ok({"thesisId": d.TH["t1"]["thesisId"], "statement": t1b["statement"], "killCondition": t1b["killCondition"], "expectedVersion": 2}, t1b))
put("thesis.update", "conflict", err({"thesisId": d.TH["t1"]["thesisId"], "statement": "x", "expectedVersion": 1}, "CONFLICT", "这条逻辑已被修改，请刷新后再试", currentVersion=2))
put("thesis.archive", "ok", ok({"thesisId": d.TH["t2"]["thesisId"]}, {"ok": True}))
versions = [
    {"version": 2, "statement": d.TH["t1"]["statement"], "killCondition": d.TH["t1"]["killCondition"], "createdAt": "2026-10-12T11:03:00Z"},
    {"version": 1, "statement": "控股股东长期持股", "killCondition": None, "createdAt": "2026-09-02T02:10:00Z"},
]
put("thesis.versions", "default", ok({"thesisId": d.TH["t1"]["thesisId"]}, {"items": versions}))

# ---- 清单与判定 -----------------------------------------------------
put("inbox.list", "pending", ok({}, m.INBOX_PENDING))
put("inbox.list", "empty", ok({}, m.INBOX_EMPTY))
put("inbox.list", "scan_failed", ok({}, m.INBOX_SCAN_FAILED))
put("inbox.list", "no_holdings", ok({}, m.INBOX_NO_HOLDINGS))
put("inbox.list", "never_scanned", ok({}, m.INBOX_NEVER_SCANNED))
put("inbox.list", "offline", ok({}, m.INBOX_OFFLINE))


def detail(dec_):
    c = copy.deepcopy(dec_)
    c["actions"] = [] if not dec_["action"] else [dec_["action"]]
    c["thesisIsLatest"] = True
    return c


put("decision.get", "overturn", ok({"decisionId": d.D["d1"]["decisionId"]}, detail(d.D["d1"])))
put("decision.get", "weaken", ok({"decisionId": d.D["d3"]["decisionId"]}, detail(d.D["d3"])))
put("decision.get", "uncertain", ok({"decisionId": d.D["d4"]["decisionId"]}, detail(d.D["d4"])))
put("decision.get", "title_only", ok({"decisionId": d.D["d5"]["decisionId"]}, detail(d.D["d5"])))
put("decision.get", "processed", ok({"decisionId": d.D["d6"]["decisionId"]}, detail(d.D["d6"])))
put("decision.get", "not_found", err({"decisionId": "01JC8Z5V3QZZZZZZZZZZZZZZZZ"}, "NOT_FOUND", "没有找到这条判定"))
put("decision.act", "still_valid", ok({"decisionId": d.D["d1"]["decisionId"], "action": "still_valid", "note": None}, m.acted(d.D["d1"], "still_valid")))
put("decision.reopen", "ok", ok({"decisionId": d.D["d6"]["decisionId"]}, dict(d.D["d6"], action=None)))

# ---- 扫描 -----------------------------------------------------------
put("scan.start", "ok", ok({"market": "us"}, {"runId": d.RUNNING["runId"]}))
put("scan.start", "config_required", err({"market": "us"}, "CONFIG_REQUIRED", "请先填写 Jev 密钥和 SEC 联系邮箱", missing=["jevKey", "secEmail"]))
put("scan.start", "conflict", err({"market": "us"}, "CONFLICT", "扫描正在进行"))
put("scan.start", "budget", err({"market": "us"}, "BUDGET_EXCEEDED", "今日预算已用完（2,000,000 / 2,000,000 tokens），明天 08:00 后可继续", usedTokens=2000000, limitTokens=2000000))
put("scan.cancel", "ok", ok({"runId": d.RUNNING["runId"]}, {"ok": True}))
put("scan.status", "running", ok({"runId": d.RUNNING["runId"]}, d.RUNNING))
put("scan.status", "done", ok({"runId": d.R1["runId"]}, d.R1))
put("scan.history", "default", ok({"limit": 20}, {"items": [d.R1, d.R2, d.R3, d.R4], "budget": m.DATA_STATUS_OK["budget"]}))
put("scan.history", "empty", ok({"limit": 20}, {"items": [], "budget": m.DATA_STATUS_OK["budget"]}))
put("scan.history", "budget_exhausted", ok({"limit": 20}, {"items": [d.R1, d.R2], "budget": {"usedTokens": 2000000, "limitTokens": 2000000, "resetAt": "2026-11-03T00:00:00Z"}}))
put("scan.history", "running", ok({"limit": 20}, {"items": [d.RUNNING, d.R1, d.R2, d.R3, d.R4], "budget": m.DATA_STATUS_OK["budget"]}))
put("scan.detail", "with_failures", ok({"runId": d.R2["runId"]}, {"run": d.R2, "batches": d.BATCHES_R2}))
put("scan.retryBatch", "ok", ok({"batchId": d.BATCHES_R2[2]["batchId"]}, dict(d.BATCHES_R2[2], status="succeeded", attempts=4, error=None, decisions=1, inputTokens=1000)))

# ---- 模拟交易 -------------------------------------------------------
put("paper.accounts", "default", ok({}, {"items": [m.ACCOUNT]}))
put("paper.accounts", "empty", ok({}, {"items": []}))
put("paper.createAccount", "ok", ok({"name": "回放账户 A", "initialCash": "100000.00", "startDate": "2026-09-01"}, m.ACCOUNT))
put("paper.portfolio", "default", ok({"accountId": m.ACCOUNT["accountId"]}, m.PORTFOLIO))
put("paper.portfolio", "new_account", ok({"accountId": m.PORTFOLIO_NEW["account"]["accountId"]}, m.PORTFOLIO_NEW))
put("paper.order.place", "pending", ok(
    {"accountId": m.ACCOUNT["accountId"], "instrumentId": "us:ZZCL", "side": "buy", "quantity": 100, "orderType": "market_open", "idempotencyKey": "idem-004"},
    m.O4))
put("paper.order.place", "insufficient_cash", err(
    {"accountId": m.ACCOUNT["accountId"], "instrumentId": "us:ZZAR", "side": "buy", "quantity": 1800, "orderType": "market_open", "idempotencyKey": "idem-005"},
    "ORDER_REJECTED", m.ORDER_ERR_CASH["message"], **{k: v for k, v in m.ORDER_ERR_CASH["data"].items() if k != "retryable"}))
put("paper.order.place", "insufficient_position", err(
    {"accountId": m.ACCOUNT["accountId"], "instrumentId": "us:ZZCL", "side": "sell", "quantity": 500, "orderType": "market_open", "idempotencyKey": "idem-003"},
    "ORDER_REJECTED", "可卖数量不足：持仓 0 股，要卖出 500 股。", reason="INSUFFICIENT_POSITION", held=0, requested=500))
put("paper.order.cancel", "ok", ok({"orderId": m.O4["orderId"]}, dict(m.O4, status="cancelled", reservedCash=None)))
put("paper.orders", "default", ok({"accountId": m.ACCOUNT["accountId"], "limit": 50}, {"items": [m.O4, m.O3, m.O2, m.O1]}))
put("paper.advance", "filled", ok({"accountId": m.ACCOUNT["accountId"]}, m.ADVANCE_RESULT))
put("paper.advance", "no_price", err({"accountId": m.ACCOUNT["accountId"]}, "DATA_INSUFFICIENT", "没有 2026-10-16 的行情。请先刷新行情，或选择更早的回放日期。", nextDay="2026-10-16"))
put("paper.reset", "ok", ok({"accountId": m.ACCOUNT["accountId"], "confirmText": "回放账户 A"}, {"ok": True}))

# ---- 风险 -----------------------------------------------------------
put("risk.compute", "ok", ok({"scope": "holdings", "window": "1Y", "currency": "USD"}, m.RISK_OK))
import copy as _c
_three = _c.deepcopy(m.RISK_OK); _three["window"] = {"label": "3Y", "from": "2025-10-30", "to": d.LAST_TRADING_DAY, "observations": 251}
_three["warnings"] = ["数据不足三年，实际从 2025-10-30 起"]
put("risk.compute", "three_year", ok({"scope": "holdings", "window": "3Y", "currency": "USD"}, _three))
_one = _c.deepcopy(m.RISK_OK); _one["topWeights"] = [{"instrumentId": "us:ZZAR", "symbol": "ZZAR", "weight": 1.0}]
_one["effectiveHoldings"] = 1.0; _one["correlation"] = {"instrumentIds": ["us:ZZAR"], "symbols": ["ZZAR"], "matrix": [[1.0]]}
_one["svd"] = {"explained": [1.0], "loadings": [{"symbol": "ZZAR", "value": 1.0}]}; _one["conditionNumberRaw"] = None; _one["conditionNumberShrunk"] = None
_one["warnings"] = ["只有 1 只持仓，相关系数与 SVD 没有意义"]
put("risk.compute", "single", ok({"scope": "holdings", "window": "1Y", "currency": "USD"}, _one))
put("risk.compute", "insufficient", {"params": {"scope": "holdings", "window": "6M", "currency": "USD"}, "error": {
    "code": "DATA_INSUFFICIENT", "message": m.RISK_INSUFFICIENT["message"], "data": m.RISK_INSUFFICIENT["data"]}})

# ---- 演示数据 -------------------------------------------------------
put("demo.load", "ok", ok({}, {"loaded": True, "counts": {"instruments": 6, "holdings": 6, "theses": 5, "events": 6, "decisions": 6, "prices": 1500}}))
put("demo.clear", "ok", ok({}, {"ok": True}))

# ---- 补齐其余错误码的示例（09 要求 15 个错误码每个至少出现在一个示例里）----
put("scan.start", "rate_limited", err({"market": "us"}, "RATE_LIMITED", "请求过于频繁，约 20 秒后重试", retryAfterSec=20, source="SEC EDGAR"))
put("scan.start", "unauthenticated", err({"market": "us"}, "UNAUTHENTICATED", "Jev 密钥无效（401）。请重新填写 Jev 密钥。"))
put("scan.start", "engine_unavailable", err({"market": "us"}, "ENGINE_UNAVAILABLE", "JEVDB 扩展无法加载。请在设置里把引擎改为“自动”或“Jev 直连”。", engine="jevdb"))
put("scan.retryBatch", "model_error", err({"batchId": d.BATCHES_R2[2]["batchId"]}, "MODEL_ERROR", "Jev 暂时不可用（529），稍后会自动重试。", status=529))
put("scan.retryBatch", "timeout", err({"batchId": d.BATCHES_R2[2]["batchId"]}, "TIMEOUT", "请求超时，请重试。"))
put("scan.retryBatch", "internal", err({"batchId": d.BATCHES_R2[2]["batchId"]}, "INTERNAL", "发生了未预期的错误，错误编号 r-17-k3j9。", requestId="r-17-k3j9"))
put("instruments.search", "cancelled", err({"query": "zenith"}, "CANCELLED", "已取消"))

# ---- 通知 -----------------------------------------------------------
NOTIFICATIONS = {
    "app.ready": {"version": "0.1.0", "migrationsApplied": 0},
    "scan.progress": {"runId": d.RUNNING["runId"], "market": "us", "stage": "decide", "done": 9, "total": 17, "message": "正在判定 ZZCL 的 6-K"},
    "scan.finished": d.R1,
    "inbox.updated": {"newItems": 3, "pendingCount": 3},
    "engine.changed": {"from": "jevdb", "to": "jev_direct", "reason": "未找到 JEVDB 扩展，已改用 Jev 直连（同一模型）"},
    "source.degraded": {"source": "SEC EDGAR", "reason": "连续 5 次请求失败，10 分钟后重试"},
    "budget.updated": m.DATA_STATUS_OK["budget"],
}

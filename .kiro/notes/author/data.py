"""示例数据创作脚本（一次性创作工具，不属于产品代码）。

同一份数据同时产出：
  - design/prototype/data/mock.js     原型使用
  - contracts/methods/*.json          接口契约里的 examples（后续步骤）

约定见 docs/00-术语与约定.md。全部公司为虚构；时间为 UTC；金额与成交价是十进制字符串。
"""
from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP

NOW = "2026-11-02T00:35:00Z"          # 原型的"当前时间"：北京时间 2026-11-02 周一 08:35
LAST_SCAN_END = "2026-11-02T00:31:12Z"
LAST_TRADING_DAY = "2026-10-30"       # 周五；美东 11-01 已转冬令时
MODEL_ID = "jev-1.14.0"
QSET = "qs-2026-11-02.1"

_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid(n: int, kind: int = 0) -> str:
    """确定性的假 ULID：固定时间部分 + 编号。"""
    value = kind * 100000 + n
    tail = ""
    for _ in range(16):
        tail = _B32[value % 32] + tail
        value //= 32
    return "01JC8Z5V3Q" + tail


def dec(x, places=4) -> str:
    q = Decimal(1).scaleb(-places)
    return str(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- 标的
def inst(symbol, name, name_zh, exchange):
    return {
        "instrumentId": "us:" + symbol, "market": "us", "symbol": symbol,
        "name": name, "nameZh": name_zh, "exchange": exchange,
        "currency": "USD", "isActive": True,
    }


INST = {
    "ZZAR": inst("ZZAR", "Zenith Arc Robotics Inc.", "天顶弧机器人", "NASDAQ"),
    "ZZFD": inst("ZZFD", "Zephyr Foods Corp.", "和风食品", "NYSE"),
    "ZZCL": inst("ZZCL", "Zhongzhi Cloud Ltd.", "众智云", "NASDAQ"),
    "ZZBK": inst("ZZBK", "Zinc Bay Bancorp", "锌湾银行", "NASDAQ"),
    "ZZEN": inst("ZZEN", "Zeta Energy Partners", "泽塔能源", "NYSE"),
    "ZZMD": inst("ZZMD", "Zenmed Diagnostics Inc.", "泽美诊断", "NASDAQ"),
}
INST_EXTRA = {"ZZNW": inst("ZZNW", "Zenwave Networks Corp.", "泽波网络", "NASDAQ")}

# (数量, 成本, 最近收盘, 日涨跌, 备注)
POS = {
    "ZZAR": ("120", "48.20", "52.38", 0.012, "核心仓位"),
    "ZZFD": ("300", "22.10", "23.40", -0.004, None),
    "ZZCL": ("150", "31.75", "27.95", -0.031, None),
    "ZZBK": ("200", "17.90", "18.62", 0.006, None),
    "ZZEN": ("100", "38.50", "40.10", 0.009, None),
    "ZZMD": ("0", None, "64.20", -0.002, "只关注"),
}


# ---------------------------------------------------------------- 披露与段落
ABBREV = ("Inc.", "Ltd.", "Corp.", "Co.", "No.", "U.S.", "Mr.", "Ms.", "Dr.", "St.", "vs.", "approx.")


def split_sentences(text):
    """与 S-01 规格一致的简化版：句号加空格处切分，但缩写表里的词不切。"""
    parts, start = [], 0
    for i, ch in enumerate(text):
        if ch != "." or not (i + 1 == len(text) or text[i + 1] == " "):
            continue
        word = text[:i + 1].split(" ")[-1].split("(")[-1]
        if any(word.endswith(a) for a in ABBREV) and i + 1 != len(text):
            continue
        parts.append((start, i + 1))
        start = i + 2
    if start < len(text):
        parts.append((start, len(text)))
    return parts


def event(n, symbol, title, form, published, fname):
    acc = "0009990001-26-%06d" % n
    return {
        "eventId": "us:" + acc, "instrumentId": "us:" + symbol, "title": title,
        "formType": form, "publishedAt": published,
        "url": "https://www.sec.gov/Archives/edgar/data/9990001/%s/%s" % (acc.replace("-", ""), fname),
    }


EV = {
    "E1": event(1, "ZZAR", "8-K: Other Events — Notice of proposed sale by controlling stockholder", "8-K", "2026-10-30T20:12:00Z", "zzar-8k.htm"),
    "E2": event(2, "ZZCL", "6-K: Zhongzhi Cloud Reports Third Quarter 2026 Results", "6-K", "2026-10-30T11:30:00Z", "zzcl-ex991.htm"),
    "E3": event(3, "ZZAR", "8-K: Results of Operations — Third Quarter 2026", "8-K", "2026-10-29T20:05:00Z", "zzar-ex991.htm"),
    "E4": event(4, "ZZFD", "8-K: Quarterly dividend and share repurchase update", "8-K", "2026-10-29T13:02:00Z", "zzfd-8k.htm"),
    "E5": event(5, "ZZBK", "8-K: Third quarter 2026 net interest margin", "8-K", "2026-10-27T21:15:00Z", "zzbk-ex991.htm"),
    "E6": event(6, "ZZCL", "6-K: Notice of Extraordinary General Meeting", "6-K", "2026-10-28T09:45:00Z", "zzcl-6k.htm"),
}

PASS = {
    "E1": 'Item 8.01 Other Events. On October 29, 2026, Zenith Arc Robotics Inc. (the "Company") was notified by Atlas Holdings LP, its controlling stockholder, that Atlas intends to sell up to 4.5% of the Company\'s outstanding common stock in a registered secondary offering during the next sixty days. Following the proposed sale, Atlas would continue to hold approximately 31.0% of the outstanding common stock. The Company will not receive any proceeds from the sale.',
    "E2": "Zhongzhi Cloud Ltd. today announced unaudited financial results for the third quarter ended September 30, 2026. Cloud services revenue was RMB 1,284 million, an increase of 8.6% year-over-year, compared with an increase of 14.2% in the second quarter. Total revenue was RMB 2,031 million, an increase of 11.3% year-over-year. The Company expects cloud services revenue growth to remain in the single digits for the fourth quarter as it completes the migration of legacy customers.",
    "E3": "Zenith Arc Robotics reported third quarter revenue of $214.6 million, up 9% from a year earlier. Research and development expenses were $28.8 million, or 13.4% of revenue, compared with $31.9 million, or 16.1% of revenue, in the prior-year quarter. The Company said it is prioritizing near-term profitability and has paused two early-stage programs.",
    "E4": "The Board of Directors of Zephyr Foods Corp. declared a quarterly cash dividend of $0.20 per share, unchanged from the prior quarter, payable on December 15, 2026 to stockholders of record on November 30, 2026. During the quarter the Company repurchased 0.4 million shares, compared with 1.1 million shares in the prior quarter. The Company said the pace of repurchases may vary with market conditions.",
    "E5": "Zinc Bay Bancorp announced that its net interest margin was 3.12% for the third quarter, compared with 3.15% in the second quarter. The average cost of deposits was unchanged at 1.84%. Management said it expects the margin to stabilize in the fourth quarter.",
    "E6": EV["E6"]["title"],
}

# 证据句：从 1 开始的句子序号；None 表示整段兜底，"title" 表示只有标题
EVIDENCE_SENTENCE = {"E1": 2, "E2": 2, "E3": 2, "E5": 1}


def evidence(key):
    passage = PASS[key]
    if key == "E6":
        return {"kind": "title", "text": passage, "passageText": passage,
                "sentenceStart": None, "sentenceEnd": None, "filePart": "标题"}
    part = {"E1": "主文档", "E4": "主文档"}.get(key, "EX-99.1")
    idx = EVIDENCE_SENTENCE.get(key)
    if idx is None:
        return {"kind": "passage", "text": passage, "passageText": passage,
                "sentenceStart": None, "sentenceEnd": None, "filePart": part}
    s, e = split_sentences(passage)[idx - 1]
    return {"kind": "sentence", "text": passage[s:e], "passageText": passage,
            "sentenceStart": s, "sentenceEnd": e, "filePart": part}


# ---------------------------------------------------------------- 逻辑
def thesis(n, symbol, statement, kill, version, vcount, created, updated):
    return {
        "thesisId": ulid(n, 2), "instrumentId": "us:" + symbol, "version": version,
        "statement": statement, "killCondition": kill, "status": "active",
        "createdAt": created, "updatedAt": updated, "versionCount": vcount, "lastDecision": None,
    }


TH = {
    "t1": thesis(1, "ZZAR", "控股股东长期持股，不会大幅减持", "控股股东减持超过 2%", 2, 2, "2026-09-02T02:10:00Z", "2026-10-12T11:03:00Z"),
    "t2": thesis(2, "ZZAR", "Management keeps R&D spending above 15% of revenue", None, 1, 1, "2026-09-02T02:15:00Z", "2026-09-02T02:15:00Z"),
    "t3": thesis(3, "ZZFD", "公司持续回购股票并维持分红", "暂停回购或削减分红", 1, 1, "2026-09-03T08:20:00Z", "2026-09-03T08:20:00Z"),
    "t4": thesis(4, "ZZCL", "云业务收入保持两位数增长，同比不低于 10%", "云业务收入同比增速低于 10%", 2, 2, "2026-09-05T01:40:00Z", "2026-10-20T03:00:00Z"),
    "t5": thesis(5, "ZZBK", "存款成本保持稳定，净息差不收窄", None, 1, 1, "2026-09-08T03:00:00Z", "2026-09-08T03:00:00Z"),
}


def probs(relevant, against, contradicts, kill, supports):
    return {"relevant": relevant, "against": against, "contradicts": contradicts,
            "killMet": kill, "supports": supports}


def headline(p):
    return max(p["against"], p["contradicts"], p["killMet"] or 0.0)


def decision(n, t, ev_key, relation, p, action=None, content="full_text", created=LAST_SCAN_END, ver=None, statement=None):
    th = TH[t]
    ev = EV[ev_key]
    return {
        "decisionId": ulid(n, 3),
        "thesisId": th["thesisId"], "thesisVersion": ver or th["version"], "thesisCurrentVersion": th["version"],
        "instrument": INST[th["instrumentId"][3:]],
        "thesisStatement": statement or th["statement"], "killCondition": th["killCondition"],
        "relation": relation, "headline": headline(p), "probabilities": p,
        "engine": "jev_direct", "modelId": MODEL_ID, "questionSetVersion": QSET,
        "event": ev, "evidence": evidence(ev_key), "contentStatus": content,
        "createdAt": created, "action": action,
    }


D = {
    "d1": decision(1, "t1", "E1", "overturn", probs(0.97, 0.89, 0.84, 0.93, 0.03)),
    "d2": decision(2, "t4", "E2", "overturn", probs(0.98, 0.92, 0.81, 0.88, 0.02), ver=1, statement="云业务收入保持两位数增长"),
    "d3": decision(3, "t2", "E3", "weaken", probs(0.95, 0.74, 0.41, None, 0.06)),
    "d4": decision(4, "t3", "E4", "uncertain", probs(0.93, 0.55, 0.22, 0.31, 0.18)),
    "d5": decision(5, "t4", "E6", "uncertain", probs(0.58, 0.42, 0.20, 0.35, 0.10), content="title_only", ver=1, statement="云业务收入保持两位数增长"),
    "d6": decision(
        6, "t5", "E5", "weaken", probs(0.96, 0.72, 0.30, None, 0.08),
        action={"action": "still_valid", "note": "只收窄了 3 个基点，管理层预计稳定", "actedAt": "2026-10-28T02:40:00Z"},
        created="2026-10-28T00:20:00Z",
    ),
}
# 逻辑的最近一次判定（简版）
for t_key, d_key in (("t1", "d1"), ("t2", "d3"), ("t3", "d4"), ("t4", "d2"), ("t5", "d6")):
    d = D[d_key]
    TH[t_key]["lastDecision"] = {
        "decisionId": d["decisionId"], "relation": d["relation"], "headline": d["headline"],
        "createdAt": d["createdAt"], "eventTitle": d["event"]["title"],
    }


# ---------------------------------------------------------------- 持仓
def holding(symbol):
    qty, cost, close, chg, note = POS[symbol]
    theses = [t for t in TH.values() if t["instrumentId"] == "us:" + symbol]
    ds = [d for d in D.values() if d["instrument"]["symbol"] == symbol and d["action"] is None]
    pending = sum(1 for d in ds if d["relation"] in ("overturn", "weaken"))
    unsure = sum(1 for d in ds if d["relation"] == "uncertain")
    status = "unguarded" if not theses else ("attention" if pending else "guarded")
    mv = Decimal(qty) * Decimal(close)
    return {
        "holdingId": ulid(int(symbol[2:].encode().hex(), 16) % 1000, 1),
        "instrument": INST[symbol], "quantity": dec(qty, 4), "avgCost": (dec(cost, 4) if cost else None), "note": note,
        "lastClose": float(close), "lastCloseDate": LAST_TRADING_DAY, "dayChangePct": chg,
        "marketValue": dec(mv), "thesisCount": len(theses), "pendingCount": pending,
        "uncertainCount": unsure, "status": status,
    }


HOLDINGS = [holding(s) for s in ("ZZAR", "ZZFD", "ZZCL", "ZZBK", "ZZEN", "ZZMD")]
HOLD_BY = {h["instrument"]["symbol"]: h for h in HOLDINGS}

# ---------------------------------------------------------------- 扫描
RUN_STATS = {"instruments": 4, "skippedNoThesis": 2, "filings": 6, "passages": 17, "decisions": 21,
              "cachedDecisions": 0, "requests": 17, "inputTokens": 18420, "estCostUsd": "0.0008",
              "durationMs": 31000}


def cost(tokens):
    return dec(Decimal(tokens) * Decimal("0.042") / Decimal(1000000), 6)


def run(n, status, start, end, stats=None, error=None, trigger="manual", window=("2026-10-26T00:00:00Z", "2026-11-02T00:30:41Z")):
    s = dict(RUN_STATS)
    if stats:
        s.update(stats)
    s["estCostUsd"] = cost(s["inputTokens"])
    return {
        "runId": ulid(n, 4), "trigger": trigger, "market": "us", "status": status,
        "windowStart": window[0], "windowEnd": window[1], "stats": s,
        "engine": "jev_direct", "modelId": MODEL_ID, "startedAt": start, "finishedAt": end,
        "error": error, "batchSummary": {"total": 17, "succeeded": 17, "failed": 0, "pending": 0},
    }


R1 = run(1, "succeeded", "2026-11-02T00:30:41Z", LAST_SCAN_END)
R2 = run(2, "partial", "2026-10-31T09:10:02Z", "2026-10-31T09:11:20Z",
         stats={"filings": 2, "passages": 5, "decisions": 6, "requests": 5, "inputTokens": 6110, "estCostUsd": "0.0003", "durationMs": 78000},
         window=("2026-10-28T00:00:00Z", "2026-10-31T09:10:00Z"),
         error={"code": "MODEL_ERROR", "message": "1 个批次判定失败，已保留其余结果，下次扫描会自动重试"})
R2["batchSummary"] = {"total": 5, "succeeded": 4, "failed": 1, "pending": 0}
R3 = run(3, "succeeded", "2026-10-28T00:15:10Z", "2026-10-28T00:15:48Z",
         stats={"filings": 3, "passages": 6, "decisions": 7, "requests": 6, "inputTokens": 7240, "estCostUsd": "0.0003", "durationMs": 38000},
         window=("2026-10-26T00:00:00Z", "2026-10-28T00:15:00Z"))
R3["batchSummary"] = {"total": 6, "succeeded": 6, "failed": 0, "pending": 0}
R4 = run(4, "cancelled", "2026-10-26T01:02:00Z", "2026-10-26T01:02:09Z",
         stats={"filings": 1, "passages": 1, "decisions": 0, "requests": 0, "inputTokens": 0, "estCostUsd": "0.0000", "durationMs": 9000},
         window=("2026-10-19T00:00:00Z", "2026-10-26T01:02:00Z"))
R4["batchSummary"] = {"total": 8, "succeeded": 0, "failed": 0, "pending": 8}
RUNNING = run(5, "running", "2026-11-02T00:34:20Z", None,
              stats={"filings": 6, "passages": 17, "decisions": 9, "requests": 9, "inputTokens": 9800, "estCostUsd": "0.0004", "durationMs": 40000})
RUNNING["batchSummary"] = {"total": 17, "succeeded": 9, "failed": 0, "pending": 8}


def batch(n, run_id, ev_key, status, attempts=1, error=None, passages=1, decisions=1, tokens=1100):
    ev = EV[ev_key]
    return {
        "batchId": ulid(n, 5), "runId": run_id, "instrumentId": ev["instrumentId"],
        "eventId": ev["eventId"], "eventTitle": ev["title"], "status": status,
        "attempts": attempts, "error": error, "passages": passages, "decisions": decisions,
        "inputTokens": tokens,
    }


BATCHES_R2 = [
    batch(1, R2["runId"], "E3", "succeeded", passages=2, decisions=4, tokens=2300),
    batch(2, R2["runId"], "E4", "succeeded", passages=1, decisions=1, tokens=1200),
    batch(3, R2["runId"], "E6", "failed", attempts=3, passages=1, decisions=0, tokens=0,
          error={"code": "MODEL_ERROR", "message": "Jev 返回 529（服务过载），已重试 3 次"}),
    batch(4, R2["runId"], "E5", "succeeded", passages=1, decisions=1, tokens=900),
]


def delta(a, b):
    return round(a - b, 4)

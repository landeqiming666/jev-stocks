"""风险文案由本包提供，组合根可合并 MESSAGES。"""

from __future__ import annotations

from collections.abc import Mapping

MESSAGES: dict[str, str] = {
    "risk.no_holdings": "没有可计算的持仓",
    "risk.insufficient": "样本不足：共同交易日 {observations} 天，至少需要 {required} 天。",
    "risk.limiting_symbol": "{symbol} 的有效一日收益最少，请刷新该标的行情。",
    "risk.unadjusted": "价格未复权",
    "risk.singular": "协方差矩阵接近奇异",
    "risk.single": "至少需要 2 只持仓",
    "risk.zero_variance": "资产无波动，相关性与主成分无法计算。",
    "risk.partial_zero_variance": "部分资产无波动，已保留权重；相关性为空，主成分不包含该资产。",
    "risk.stale": "{symbol} 最新行情落后超过 3 个交易日，请刷新行情。",
    "risk.short_history": "数据不足三年，实际从 {start} 起",
    "risk.watch_only": "只关注，数量为 0，不计入权重",
    "risk.no_baseline": "没有有效价格基线，不计入权重",
}


def text(key: str, params: Mapping[str, object] | None = None) -> str:
    return MESSAGES[key].format_map(dict(params or {}))

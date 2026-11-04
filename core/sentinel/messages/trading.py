"""拒单模板使用规则返回的变量名；金额显示格式由调用方准备。"""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    "trading.no_price": "没有 {date} 的收盘价，无法估算所需资金。请先刷新行情。",
    "trading.insufficient_cash": "资金不足：预计需要 ${required}，可用现金 ${available}。",
    "trading.insufficient_position": "可卖数量不足：持仓 {held} 股，要卖出 {requested} 股。",
    "trading.no_price_at_fill": "连续 {n} 个交易日没有行情，订单已取消。",
    "trading.insufficient_cash_at_fill": (
        "开盘价高于预估，资金不足：需要 ${required}，可用 ${available}。"
    ),
    "trading.insufficient_position_at_fill": "成交时持仓不足，订单已取消。",
    "trading.order_type_unsupported": "暂不支持限价单，请使用开盘市价单。",
}

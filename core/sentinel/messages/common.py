"""通用错误与配置文案。"""

from __future__ import annotations

MISSING_LABELS: dict[str, str] = {
    "jevKey": "Jev 密钥",
    "secEmail": "SEC 联系邮箱",
}

MESSAGES: dict[str, str] = {
    "error.INVALID_ARGUMENT": "填写的内容不正确，请检查后重试。",
    "error.NOT_FOUND": "没有找到对应的内容，请刷新后重试。",
    "error.CONFLICT": "数据已发生变化，请刷新后重试。",
    "error.CONFIG_REQUIRED": "还需要完成设置：{missing}。",
    "error.UNAUTHENTICATED": "Jev 密钥无效或没有权限，请在设置中重新填写。",
    "error.ENGINE_UNAVAILABLE": "指定的判定引擎不可用，请在设置中切换引擎。",
    "error.SOURCE_UNAVAILABLE": "数据源暂时不可用，请稍后重试。",
    "error.RATE_LIMITED": "请求过于频繁，请在 {retryAfterSec} 秒后重试。",
    "error.MODEL_ERROR": "模型服务暂时出错，稍后会重试该批次。",
    "error.BUDGET_EXCEEDED": "今日模型用量额度已用完，请等待额度重置。",
    "error.DATA_INSUFFICIENT": "可用数据不足，暂时无法计算。",
    "error.ORDER_REJECTED": "模拟订单未通过校验，请检查订单信息。",
    "error.TIMEOUT": "操作超时，请重试。",
    "error.CANCELLED": "操作已取消。",
    "error.INTERNAL": "发生了意外错误，请复制错误编号 {requestId} 并重试。",
}

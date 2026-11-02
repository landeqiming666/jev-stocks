"""C-04 文案；公共目录由主 agent 注册。"""

MESSAGES: dict[str, str] = {
    "settings.email_invalid": "联系邮箱格式不正确，请检查后重试。",
    "settings.secret_invalid": "密钥须为 1–512 字符且不能含内部空白，请重新填写。",
    "settings.keyring_unavailable": "系统钥匙串不可用，请解锁后重试。",
    "settings.data_corrupt": "设置数据损坏，请复制错误编号并联系支持。",
    "settings.jev_ok": "模型 {modelId} 可用",
    "settings.jev_failed": "Jev 连接未通过，请检查密钥和网络后重试。",
    "settings.sec_ok": "data.sec.gov 可访问",
    "settings.sec_failed": "SEC 连接未通过，请检查联系邮箱和网络后重试。",
    "settings.jevdb_ok": "JEVDB 扩展可用",
    "settings.jevdb_fallback": (
        "JEVDB 检查未通过；可用引擎允许日常 Jev 直连降级，最终 I-02 真实 JEVDB 验收仍是硬门槛。"
    ),
}

DOMAIN_RULES: list[dict[str, str]] = [
    {
        "domain": "api.typesafe.ai",
        "purpose": "Jev 判定",
        "sends": "逻辑正文、失效条件、披露段落；不含持仓数量、成本、备注",
    },
    {
        "domain": "www.sec.gov",
        "purpose": "披露与标的表",
        "sends": "请求 URL 与含联系邮箱的 User-Agent",
    },
    {
        "domain": "data.sec.gov",
        "purpose": "披露与标的表",
        "sends": "请求 URL 与含联系邮箱的 User-Agent",
    },
    {
        "domain": "web.ifzq.gtimg.cn",
        "purpose": "日线行情（主源，覆盖美股/港股/A 股）",
        "sends": "股票代码与市场前缀",
    },
    {"domain": "api.nasdaq.com", "purpose": "日线行情（美股备源）", "sends": "股票代码"},
]

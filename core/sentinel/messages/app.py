"""核心进程生命周期文案。"""

from __future__ import annotations

MESSAGES: dict[str, str] = {
    "engine.changed": "未找到 JEVDB 扩展，已改用 Jev 直连（同一模型）",
    "core.starting": "核心服务正在启动。",
    "core.ready": "核心服务已就绪。",
    "core.restarting": "核心服务正在重启。",
    "core.shuttingDown": "核心服务正在关闭。",
    "core.stopped": "核心服务已停止。",
    "core.startupFailed": "核心服务启动失败。",
    "core.logLevelInvalid": "日志级别无效，已使用 info。",
}

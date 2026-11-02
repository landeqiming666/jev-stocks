# CR-20261102-windows-mypy-platform

- 提出者（工作包 ID）：W-00
- 类型：平台问题
- 基线：`5b79539708557884c925138daa4776d1b2321c7c`
- 状态：待协调者评审

## 现象与复现

Windows 11 x64、CPython 3.12.15，在项目锁定依赖下运行：

```powershell
py -3 scripts\check.py
# 退出码 1：通过 13 · 失败 1 · 跳过 3
# 失败步骤：uv run mypy sentinel（工作目录 core）
```

关键输出：

```text
sentinel\platform\posix.py:42: error: Module has no attribute "flock" [attr-defined]
sentinel\platform\posix.py:42: error: Module has no attribute "LOCK_EX" [attr-defined]
sentinel\platform\posix.py:42: error: Module has no attribute "LOCK_NB" [attr-defined]
sentinel\platform\posix.py:48: error: Module has no attribute "flock" [attr-defined]
sentinel\platform\posix.py:48: error: Module has no attribute "LOCK_UN" [attr-defined]
```

Windows 下的类型检查仍扫描 POSIX 实现，并采用 Windows 对标准库的类型视图，导致上述属性不存在。运行时平台路由和 Python 通用测试可以通过，不能消除这项静态检查失败。

## 依据

- [Windows 车道协议](../../10-协作与工作包规范.md#9-windows-车道协议)：共享代码的问题先提变更申请。
- [W-00](../mvp0/W-00-windows-survey.md)：运行完整检查并记录 B 类失败。
- [平台层代码](../../../core/sentinel/platform/posix.py)与[类型配置](../../../core/pyproject.toml)。

## 方案与影响

1. 在平台层采用类型检查器能识别的平台条件或类型封装，使 POSIX 实现在 Windows 检查时不会错误使用 Windows 的 `fcntl` 属性集合。影响平台层实现及相应类型测试；保持公开接口和严格检查。
2. 为平台实现设置明确的分平台类型检查目标：Windows 目标验证 Windows 实现与共享代码，macOS 目标验证 POSIX 实现与共享代码。影响共享检查入口、配置和双平台验证方式；须确保两类实现都持续被检查。

W-00 未应用任何修复。

- 阻塞的工作包：Windows 的共享工程全绿验收；不阻塞 macOS 主线。
- 决定：待协调者填写。


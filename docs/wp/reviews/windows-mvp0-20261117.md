# Windows MVP-0 实现与审核交接

日期：2026-11-17。交付分支：`codex/windows-dev`。共享基线：`codex/mac-mvp-final18@4f9e9d4`。

Windows 的 W-01 至 W-05 实现、共享代码修复和本机验证已整理在此分支。工程自动门禁、离线真实核心联调及原生六页专项验证通过。完整 Windows 验收仍有人工项目，详见下方待验清单。

[查看相对共享基线的全部改动](https://github.com/landeqiming666/jev-stocks/compare/codex/mac-mvp-final18...codex/windows-dev)。各任务记录见 [W-01](../status/W-01.md)、[W-02](../status/W-02.md)、[W-03](../status/W-03.md)、[W-04](../status/W-04.md)、[W-05](../status/W-05.md)。

## 本次交付

| 范围 | 实现和修复 |
|---|---|
| Windows 基础 | PowerShell 开发入口、平台路径与权限、进程管理、MSVC 工具链检查、Windows 外壳样式和快捷键 |
| C-02 桥接 | Tauri 与 Python 核心的 Windows 启停、管道通信、取消及退出清理 |
| JEVDB | 固定构建来源及哈希的 MSVC 构建流程，实际扩展加载探测，自动降级和扩展替换后的重新选择 |
| 系统凭据 | C-07 在 Windows 显式选择 WinVault，初始化失败保持未配置，保存和清除返回既定错误 |
| 演示数据 | 按表使用参数化 JSON 批量写入，保留事务回滚、字段类型及登记簿保护 |
| 联调与验收 | 真实组合根夹具、Edge 测试、六个原生业务页截图、测试计数检查、启动失败和窗口关闭后的定向进程清理 |

关键提交：`81c8a40` 合入共享基线，`6dea7bb` 完成集成和主要修复，`ee6baa3` 修复启动边界与验收遗漏，`1e3b1a9` 更新验证记录。完整自动运行对应 `6dea7bb`；`ee6baa3` 的启动清理变更另有双 PowerShell 专项验证。

## 请优先审核的改动

1. [C-07 凭据装配](../../../core/sentinel/app/container.py)：Windows 显式选择凭据后端。请核对后端不可用时的未配置状态、保存和清除语义，并在 macOS 复跑共享回归。
2. [引擎选择](../../../core/sentinel/app/engines.py)：选择 JEVDB 前执行实际 `LOAD`，失败后关闭候选连接。自动模式降级直连，显式 JEVDB 模式返回错误。文件身份、大小和时间戳变化触发重新探测，专项覆盖有效、损坏、缺失及恢复。
3. [演示载入](../../../core/sentinel/demo/loader.py)：白名单表使用参数化 JSON SQL，在同一事务内更新登记簿。请重点核对批量写入的类型保真、回滚和清除范围。本机载入从 48.246 秒降至 0.200 秒，清除从 9.347 秒降至 0.074 秒。
4. [原生窗口证据采集与清理](../../../apps/desktop/e2e/windows/collect-evidence.ps1)及[验收编排](../../../scripts/windows_smoke.ps1)：用进程 ID 与创建时间识别本次进程，处理窗口出现前启动器退出的情况，保留原始失败报告。请重点查看隔离保护和错误证据交接。
5. [资源换行规则](../../../.gitattributes)与真实核心测试夹具：演示和评测资源固定 LF，避免 Windows 检出后破坏 manifest 哈希。测试使用独立数据目录和内存凭据。200 步账本压力测试预算为 120 秒；120 段落、60 判定的累计扫描等待预算为 10 秒，工作量和断言保留。

## 验证结果

完整自动运行使用 Windows x64、离线模式和 `-NoLaunch`。原始总结果为 **`fail`，退出码 `3`**，原因是必需人工项尚未验收。`WM-1=pass`，`WM-2/3/4/5=not_run`。随后完成的原生窗口专项证据单独提供，未改写该次自动报告。

| 验证 | 实际结果 | 已发布证据 |
|---|---|---|
| 工程门禁 | 16 通过、0 失败、1 跳过 | [工程日志](../evidence/windows-20261117/engineering-check.log) |
| 脚本测试 | 336 通过、3 跳过，含 4418 个通过子测试 | [运行摘要](../evidence/windows-20261117/acceptance-summary.json) |
| 核心单元测试 | 2826 通过、8 跳过，21 项集成测试另行执行 | [工程日志](../evidence/windows-20261117/engineering-check.log) |
| 前端单元测试 | 465 通过 | [工程日志](../evidence/windows-20261117/engineering-check.log) |
| Windows 桥接 | 7 通过，1 项生产凭据入口测试默认忽略 | [运行摘要](../evidence/windows-20261117/acceptance-summary.json) |
| I-01 真实核心 | 20 通过、1 跳过 | [逐项摘要](../evidence/windows-20261117/core-integration-summary.json) |
| Edge | 模拟界面 4 通过，真实核心 11 通过、0 跳过、0 失败、0 flaky | [真实核心逐项摘要](../evidence/windows-20261117/real-core-browser-summary.json) |
| WinVault | 14 通过，隔离探针读、写、删除均成功 | [运行摘要](../evidence/windows-20261117/acceptance-summary.json) |
| 原生六页 | 实际 Tauri、生产 C-02 与真实核心，六页显示演示数据且无横向溢出 | [页面测量](../evidence/windows-20261117/native-routes.json)、[初始化](../evidence/windows-20261117/native-verification.json) |
| 原生退出 | 关窗后 20 个已观测进程在 0.6905 秒内全部退出 | [退出摘要](../evidence/windows-20261117/native-exit-summary.json) |
| JEVDB 加载 | 实际本机扩展加载、损坏和缺失时降级、恢复后重新选择通过；模型请求数为 0 | [加载证据](../evidence/windows-20261117/jev-runtime.json) |
| 演示性能 | 六表计数 6/5/6/6/12/1560，登记簿 1652 行 | [计时与计数](../evidence/windows-20261117/demo-performance.json) |
| 清理边界 | Windows PowerShell 5.1 与 PowerShell 7 均完成进程清理、启动失败及编排衔接验证 | [PS 5.1 清理](../evidence/windows-20261117/cleanup-ps51.json)、[PS 7 清理](../evidence/windows-20261117/cleanup-ps7.json)、[PS 5.1 启动失败](../evidence/windows-20261117/startup-cleanup-ps51.json)、[PS 7 启动失败](../evidence/windows-20261117/startup-cleanup-ps7.json) |

I-01 跳过的是演示数据没有失败批次时的真实重试取消用例，受控取消另有测试。真实核心浏览器运行仍记录一条未知响应 ID 警告，测试全部通过。符号链接能力不足等跳过原因保留在原日志中。

六张原生截图：[今天](../evidence/windows-20261117/screenshots/today-1024.png)、[持仓](../evidence/windows-20261117/screenshots/holdings-1024.png)、[扫描](../evidence/windows-20261117/screenshots/scan-1024.png)、[交易](../evidence/windows-20261117/screenshots/trading-1024.png)、[风险](../evidence/windows-20261117/screenshots/risk-1024.png)、[设置](../evidence/windows-20261117/screenshots/settings-1024.png)。CSS 视口实测为 1024×700，本机 DPI 为 1.5，Win32 客户区为 1023×700。

## 待验项目

- 在专用 Windows 用户下验证默认生产凭据启动入口，完成系统凭据管理器截图及设置页保存、重启读取、清除的完整流程。
- 完成 US-01 至 US-15 的连续原生操作录屏。
- 确定 [Windows JEVDB 最终门槛](../cr/CR-20261104-windows-jevdb-acceptance.md)，再执行真实模型、SEC 和 M8 请求验证。本轮模型请求为 0，未消耗实际模型额度。
- 共享 Python、资源和测试夹具改动由 macOS 端复核。本轮运行环境为 Windows。

## 证据与复现

[证据清单](../evidence/windows-20261117/manifest.json)记录发布文件与本地原始文件的 SHA-256。截图和部分 JSON 为原样拷贝；摘要提取原报告字段，工程日志将本机工作区前缀替换为 `<workspace>`、统一换行和路径分隔符并清除行尾空白，一份 PowerShell 5.1 JSON 从 UTF-16 转为 UTF-8。清单逐项标明变换方式。数据库、扩展二进制和完整原始运行目录保留在本地，原始位置见 [W-05](../status/W-05.md)。

按 [Windows 验收说明](../../../apps/desktop/e2e/windows/README.md)准备环境后，在仓库根目录复现自动项：

```powershell
powershell.exe -NoProfile -File scripts/windows_smoke.ps1 -Offline -NoLaunch -SkipInstall -ReportDir ../tmp/windows-review
```

该命令跳过原生窗口采集，人工项未补齐时退出码为 3。真实核心联调和原生六页专项使用内存凭据；系统凭据后端另由隔离探针验证。

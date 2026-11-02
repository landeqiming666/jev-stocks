---
id: W-05
title: Windows MVP-0 联调与验收
phase: mvp0
platform: windows
lane: windows
deps: [W-02, W-04, I-01]
size: M
owns: [scripts/windows_smoke.ps1, apps/desktop/e2e/windows/]
appends: []
stubs: []
---

# W-05 Windows MVP-0 联调与验收

## 0. 一眼看懂

- **目标**：在 Windows 11 x64 开发模式下跑完 WM-1～WM-5，保存截图、录屏清单、桥接与凭据证据；结论单独记录，不影响 macOS 交付。
- **完成后解锁**：Windows MVP-0 验收状态，不阻塞 I-02 的 macOS 结果。
- **预计规模**：约 460 行，PowerShell 220 行、Playwright 与清单 240 行。

## 1. 背景与边界

### 1.1 为什么需要它
共享测试全绿只证明代码能跑；Windows 还要证明原生标题栏、WebView2 布局、含空格/中文路径、凭据持久化和进程树清理在真实窗口里成立。Windows 的失败不得伪装成 macOS 通过，也不得拖住 Mac。

### 1.2 范围内
1. 自动执行 `setup.ps1`、`check.ps1`、I-01 集成测试、W-02 桥接测试、W-04 凭据测试。
2. 在临时数据目录载入 E-01 演示数据，运行 Windows UI Playwright 场景。
3. 首次窗口启动、原生标题栏、六页布局、离线、WM-3 的 15 条用户故事人工证据。
4. 生成独立 `acceptance.json`、截图目录与状态文件。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 修改共享代码、契约、页面或 Mac 验收 | 禁止 |
| NSIS 安装包、托盘、自启 | v1 |
| 把 JEVDB 失败当作 macOS M-8 的直连替代 | W-03 只记录 Windows 开发结果；macOS M-8 仍须真实 JEVDB |
| 覆盖 macOS 的 I-02 报告 | 分目录、分平台 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [01-产品需求.md](../../01-产品需求.md) | 第 8 节 Windows 车道验收、US-01～US-15 | WM-1～WM-5 |
| [09-测试与评测.md](../../09-测试与评测.md) | 11.3 Windows 车道 | 人工检查项 |
| [10-协作与工作包规范.md](../../10-协作与工作包规范.md) | 9 Windows 车道协议 | 单独记录、不阻塞 Mac |
| [decisions.md](../../decisions.md) | [ADR-016](../../decisions.md#adr-016--mac-与-windows-分车道并行开发平台差异隔离在平台层) | 平台隔离 |
| [I-02-acceptance.md](I-02-acceptance.md) | 5.2 报告字段、§7 演示表 | 复用报告口径 |
| [W-02-windows-bridge.md](W-02-windows-bridge.md) | 9.1 桥接命令 | 复用桥接结果 |

## 3. 前置条件

- W-02、W-04、I-01 均已合并。
- Windows 11 x64，WebView2、VS Build Tools、Node、pnpm、uv、Rust MSVC 已安装。
- 能打开交互式桌面；远程/无头会话只能跑 `-NoLaunch` 自动项，不能给 WM-2/WM-3 通过。
- 测试网络可选：默认 `-Offline` 使用演示数据；联网扫描只作为附加证据。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `scripts/windows_smoke.ps1` | 新建 | Windows 验收编排、退出码、结果 JSON |
| `apps/desktop/e2e/windows/playwright.config.ts` | 新建 | Windows 桌面视口与截图目录 |
| `apps/desktop/e2e/windows/windows-ui.spec.ts` | 新建 | 六页、1024 布局、离线、错误边界 |
| `apps/desktop/e2e/windows/manual-checklist.md` | 新建 | WM-3 的 15 条人工步骤与录屏要求 |
| `apps/desktop/e2e/windows/collect-evidence.ps1` | 新建 | 窗口、版本、截图、进程清单收集 |
| `apps/desktop/e2e/windows/results/acceptance.json` | 运行时生成 | 独立 Windows 报告 |
| `apps/desktop/e2e/windows/results/screenshots/` | 运行时生成 | 六页与凭据管理器截图 |

## 5. 接口规格

### 5.1 脚本参数
```powershell
param(
  [switch]$Offline,
  [switch]$NoLaunch,
  [switch]$SkipInstall,
  [string]$ReportDir = "$PSScriptRoot\..\apps\desktop\e2e\windows\results"
)
```
默认行为等同 `-Offline`。`-NoLaunch` 只跑非窗口项，输出 `WM-2/WM-3=not_run` 且总结果 `fail`。退出码：`0` 全部 pass；`1` 有 fail；`2` 前置环境不满足；`3` 有 not_run。

### 5.2 报告字段
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `platform` | str | 是 | 固定 `windows` | 平台 |
| `osBuild` | str | 是 | `winver` 原文 | 系统版本 |
| `repoPath` | str | 是 | 含空格/中文 | 路径证据 |
| `checks.WM-1`～`WM-5` | object | 是 | `pass/fail/not_run` + evidence | 五项标准 |
| `bridge` | object | 是 | 来自 W-02 | 桥接结果 |
| `credentials` | object | 是 | 来自 W-04 | 凭据结果 |
| `jevdb` | object | 是 | 来自 W-03 | `built/fallback` |
| `overall` | str | 是 | `pass/fail` | Windows 独立结论 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `WINDOW_TITLE` | `投资逻辑哨兵` | 脚本 | 启动断言 |
| `START_TIMEOUT_S` | `180` | 脚本 | 首次 `pnpm tauri dev` 编译等待 |
| `VIEWPORT` | `1440×900` | Playwright | 桌面 |
| `MIN_VIEWPORT` | `1024×700` | Playwright | 无横向滚动 |
| `RESULT_SCHEMA` | `"windows-acceptance/1"` | JSON | 报告版本 |

## 6. 实现步骤

1. 记录 `winver`、`systeminfo` 的 OS/架构、仓库绝对路径，断言路径含空格和中文。
2. 未指定 `-SkipInstall` 时运行 `scripts\setup.ps1`；随后运行 `scripts\check.ps1`，保存完整输出为 WM-1 证据。
3. 运行 `uv run pytest tests/integration -q -m "integration and not network"` 与 W-02 的 `cargo test --test bridge_windows`。
4. 运行 W-04 真实凭据测试；保存 `probe()` JSON（不含 secret）和凭据管理器前后截图。
5. 创建 `%TEMP%\sentinel-windows-验收 空格\<random>`，设置 `SENTINEL_DATA_DIR`、`SENTINEL_OFFLINE=1`、`SENTINEL_CLOCK`。
6. 运行 `py -3 scripts\load_demo.py --data-dir <tmp> --json`；断言 `6/5/6/6/12/1560`。
7. 在 `VITE_RPC=mock` 下运行 Windows Playwright，检查六页、1024×700、离线、错误提示；保存截图和 trace。
8. `-NoLaunch` 时到此结束并写 `WM-2/WM-3=not_run`；否则启动 `scripts\dev.ps1`，最多等 180 秒。
9. 用 `Get-Process` 找到主进程，读取窗口标题与路径；断言标题恰为“投资逻辑哨兵”，任务管理器 PID 与启动 PID 对应。
10. 人工按 `manual-checklist.md` 走 US-01～US-15，保存一段连续录屏；每一步勾选并写时间戳，不能只写“已通过”。
11. 在 1024×700 下逐页截图；若存在页面级横向滚动、文字截断或 WebView2 控件异常，WM-2 fail。
12. 关闭窗口后 5 秒检查 `python.exe`/`uv.exe`/`node.exe` 无本次子进程残留；残留则 WM-1 或 WM-3 fail。
13. 汇总 W-03 的 `build-result.json`：记录 JEVDB 结果和 `fallback=jev_direct`；该记录不替代 macOS M-8，伪装 `built` 才 fail。
14. 写 `acceptance.json`，终端打印 `WINDOWS ACCEPTANCE PASS/FAIL WM1..WM5`；不在任何共享目录写 pass。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码/状态 | 用户可见结果 |
|---|---|---|---|
| 非 Windows 运行 | 立即退出 | 2 | 终端说明只能在 Windows 执行 |
| 无交互桌面 | WM-2/WM-3 `not_run` | 3 | 不宣布通过 |
| `check.ps1` 失败 | WM-1 fail，停止窗口步骤 | 1 | 保存完整输出 |
| 启动 180 秒超时 | WM-2 fail，保留控制台日志 | 1 | 不反复重启掩盖 |
| 窗口标题或标题栏不对 | WM-2 fail | 1 | 截图证据 |
| 六页任一溢出 | WM-2 fail | 1 | 截图与视口路径 |
| 凭据测试失败 | WM-4 fail | 1 | 不退回内存后端 |
| JEVDB 加载失败 | WM-5 记 `fallback=jev_direct` | 0 可 pass | 只表示 Windows 开发可用，明确不能替代 macOS M-8 |
| 子进程残留 | WM-3 fail | 1 | 任务管理器导出 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_windows_six_pages_render` | `windows-ui.spec.ts` | demo mock | 六页标题与主内容存在 |
| `test_windows_1024_has_no_horizontal_scroll` | 同上 | 1024×700 | 六页 `scrollWidth <= innerWidth` |
| `test_windows_offline_banner` | 同上 | 离线状态 | 有提示且已有数据可读 |
| `test_windows_error_boundary_keeps_shell` | 同上 | 注入 `INTERNAL` | 侧栏可用，显示错误编号 |
| `test_no_launch_marks_wm2_wm3_not_run` | `windows_smoke.ps1 -SelfTest` | `-NoLaunch` | overall fail，两项 not_run |
| `test_result_json_has_five_checks` | 同上 | 完整报告 | WM-1～WM-5 均存在 |
| `test_repo_path_contains_space_and_chinese` | 同上 | 当前路径 | 条件满足 |
| `test_no_child_processes_after_close` | 同上 | 启动后关闭 | 5 秒内 0 残留 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `apps/desktop/e2e/windows/fixtures/offline.json` | 离线 bootstrap 示例 | 从 C-06 契约复制，不新增字段 |
| `apps/desktop/e2e/windows/fixtures/internal-error.json` | 错误边界示例 | 按 05 错误对象构造 |
| `results/` | 运行产物 | 每次运行前清空，不提交截图或 trace |

## 9. 验收

### 9.1 命令与期望输出
```powershell
scripts\windows_smoke.ps1 -Offline
# 期望：WINDOWS ACCEPTANCE PASS WM1..WM5；退出 0
scripts\windows_smoke.ps1 -Offline -NoLaunch
# 期望：退出 3；WM-2/WM-3=not_run
Get-Content apps\desktop\e2e\windows\results\acceptance.json | ConvertFrom-Json
# 期望：platform=windows；overall=pass（窗口验收完成后）
scripts\check.ps1
# 期望：失败 0
```

### 9.2 完成清单
- [ ] WM-1～WM-5 各有状态和证据路径
- [ ] US-01～US-15 在 Windows 上逐条录屏并勾选
- [ ] 原生标题栏、1024×700、离线、子进程无残留有截图/进程证据
- [ ] 凭据管理器真实往返通过；JEVDB 结果如实记录
- [ ] 未修改共享接口、共享页面或 macOS 验收
- [ ] 已写 `docs/wp/status/W-05.md`；协调者据此更新对等矩阵

## 10. 给下游的交接

| 下游对象 | 它会使用 | 约定 |
|---|---|---|
| 协调者 | `results/acceptance.json`、状态文件 | 单独记录 Windows，不改写 I-02 |
| 课程报告 | WM-1～WM-5 和截图 | 只有 pass 可称 Windows 已验证 |
| v1 工作包 | 未通过的桥接/凭据证据 | 修复前不得做 NSIS 安装包结论 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| WebView2 与 Chromium 渲染差异 | 截图布局不同 | 以 WebView2 截图为准，Playwright 只作自动前置 |
| 首次 Rust 编译超 3 分钟 | 启动超时 | 先预热 `cargo build`，验收仍按 180 秒记录 |
| 录屏包含密钥或持仓 | 人工检查发现 | 立即删除产物，重录；报告中只留文件名 |

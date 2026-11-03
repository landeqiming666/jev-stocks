---
id: I-01
title: 联调：真实核心进程 + 真实前端
phase: mvp0
platform: shared
lane: integration
deps: [C-02, C-07, P-03, P-05, P-06, E-01, U-03, U-04, U-05, U-06, U-07, U-08]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [core/tests/integration/, apps/desktop/e2e/real-core/]
appends: []
stubs: []
---

# I-01 联调：真实核心进程 + 真实前端

## 0. 一眼看懂

- **目标**：把“真实 Python 核心进程 + 真实 React 页面”一次接通，证明 RPC、演示数据、六个页面、取消、错误与重启在同一个进程里成立，而不是各测各的。
- **完成后解锁**：I-02。
- **预计规模**：约 650 行，Python 集成测试约 320 行，Playwright 桥接与场景约 330 行。

## 1. 背景与边界

### 1.1 为什么需要它
前端 E2E 默认跑 mock，核心测试默认不经过 UI。两类测试都绿仍可能在字段名、错误形状、核心就绪时序和页面刷新上失败。本包用仅测试环境存在的桥接，把两边接起来。

### 1.2 范围内
1. 启动真实核心进程，走 stdin/stdout NDJSON，完成 `app.ready`、`app.bootstrap`、`demo.load`、清单、交易和风险场景。
2. Playwright 用 `page.exposeFunction` 与初始化脚本模拟 Tauri IPC，只转发到真实核心，不新增应用端口或生产代码。
3. 六页响应式检查、RPC 错误可见、核心重启、取消和含空格/中文的数据目录。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 修改 RPC 契约、Rust 核心监督逻辑或业务接口 | C-01、C-02；本包只消费 |
| 真实 Jev/SEC/行情调用 | G0、D-01；本包固定 `SENTINEL_OFFLINE=1` |
| 像素基线图与页面组件实现 | U-01～U-08 |
| 5 分钟最终验收报告 | I-02 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [02-技术架构.md](../../02-技术架构.md) | 6 Rust/前端/核心桥接、8 启动退出与心跳、12 稳定性 | 连接、超时、重启行为 |
| [05-接口契约.md](../../05-接口契约.md) | 2 消息格式、3 错误、5.9 演示数据 | 线格式与错误形状 |
| [09-测试与评测.md](../../09-测试与评测.md) | 1 测试分层、2 确定性、6 端到端场景 | 标记、假数据与用户故事 |
| [01-产品需求.md](../../01-产品需求.md) | 7 用户故事、8 M-1/M-2 | 要证明的产品行为 |
| [E-01-demo-data.md](E-01-demo-data.md) | 5.2 固定计数 | 页面断言值 |

## 3. 前置条件

- C-02 导出 `CoreProcess`，至少含 `spawn(config)`、`send_line(str)`、`recv_line(timeout)`、`status()`、`shutdown()`、`restart()`；字段与线格式按 §5.1。
- C-05 的 RPC 客户端最终走 Tauri `invoke("rpc_send", {line})`，且监听 `core://message`；测试桥只模拟这两个入口。
- E-01 的 `demo.load` 能通过真实 RPC 返回 `6/5/6/6/12/1560`。
- Playwright Chromium、Node 20+、`uv` 与项目依赖已由 WP-00 安装；不新增依赖。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/tests/integration/conftest.py` | 新建 | `real_core`、`isolated_data_dir`、`rpc` fixture |
| `core/tests/integration/harness.py` | 新建 | 子进程、行读取、超时、清理与日志收集 |
| `core/tests/integration/test_core_lifecycle.py` | 新建 | 启动、心跳、错误、取消、退出 |
| `core/tests/integration/test_demo_flow.py` | 新建 | 演示载入、清单、处理、清除 |
| `core/tests/integration/test_paper_risk_flow.py` | 新建 | 交易、推进、风险、离线 |
| `apps/desktop/e2e/real-core/fixture.ts` | 新建 | 启动核心、Playwright Tauri IPC 模拟、清理 |
| `apps/desktop/e2e/real-core/global-setup.ts` | 新建 | 检查 `uv`、Vite 与临时目录 |
| `apps/desktop/e2e/real-core/demo-flow.spec.ts` | 新建 | 六页真实数据场景 |
| `apps/desktop/e2e/real-core/failures.spec.ts` | 新建 | 500/离线/核心重启可见 |
| `apps/desktop/e2e/real-core/playwright.config.ts` | 新建 | 仅跑本目录，串行，30 秒超时 |

## 5. 接口规格

### 5.1 集成辅助接口
```python
@dataclass(frozen=True)
class CoreConfig:
    data_dir: Path; resource_dir: Path; env: Mapping[str, str]; startup_timeout_s: float = 30.0

class CoreHarness:
    def start(self) -> None: ...
    def send(self, payload: dict[str, object]) -> str: ...
    def recv_until(self, predicate: Callable[[dict], bool], timeout_s: float) -> dict: ...
    def request(self, method: str, params: dict | None = None, timeout_s: float = 30.0) -> dict: ...
    def stderr(self) -> str: ...
    def stop(self, force: bool = False) -> int: ...
```
`start` 必须等到 `app.ready` 后才返回；`request` 生成 `r-01` 起的确定性 ID，并把通知交给 `recv_until`。`stop` 先发 `app.shutdown`，3 秒未退再杀进程树；测试结束必须在 `finally` 调用。

### 5.2 IPC 模拟字段
| 字段/函数 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `window.__TAURI_INTERNALS__.invoke` | function | 是 | 只接受 `rpc_send`、只读 `core_status`、`plugin:event|listen/unlisten` | 模拟 Tauri 命令；状态快照返回真实 harness 当前状态 |
| `window.__SENTINEL_TEST_EMIT__` | function | 是 | 参数 `{event,payload}` | Node 向页面派发核心行 |
| `window.__sentinelSend` | function | 是 | 返回 Promise<void> | 页面把一行写给 Python |
| `core://message.payload` | string | 是 | 一行 JSON，≤ 1 MB | 核心响应或通知 |
| `core://status` | object | 是 | `starting/ready/restarting/failed` | 顶栏状态 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `STARTUP_TIMEOUT_S` | `30` | `harness.py` | Python 子进程首次就绪上限 |
| `REQUEST_TIMEOUT_S` | `30` | `harness.py` | 一般请求超时 |
| `SHUTDOWN_TIMEOUT_S` | `3` | `harness.py` | 优雅退出等待 |
| `PLAYWRIGHT_TIMEOUT_MS` | `30000` | `playwright.config.ts` | 单场景超时 |
| `DESKTOP_VIEWPORT` | `1440×900` | `demo-flow.spec.ts` | 桌面视口 |
| `MIN_VIEWPORT` | `1024×700` | `demo-flow.spec.ts` | 最小视口 |

## 6. 实现步骤

1. 在临时目录 `含 空格 目录/sentinel` 创建数据目录，复制只读 `resources/`，设置 `SENTINEL_OFFLINE=1`、`SENTINEL_CLOCK=2026-11-02T08:35:00Z`。
2. 用 `uv run --project core python -m sentinel --data-dir … --parent-pid … --resource-dir …` 启动；读取 stderr 捕获启动失败原文。
3. 等 `app.ready`；发送 `app.bootstrap`，断言 `protocolVersion` 以 `1.` 开头、`platform=macos|windows`、`demoDataLoaded=false`。
4. 调用 `demo.load`，再调用 `inbox.list`；断言 3 条待处理、1 条待确认、顺序 `0.93/0.78/0.71`。
5. 选择第一张卡调用 `decision.get`，再 `decision.act(action="still_valid")`，刷新后待处理为 2；`reopen` 后恢复 3。
6. 调用 `paper.accounts`、`paper.portfolio`、`paper.advance`；断言返回的 `clockDate` 严格前进，权益字段齐全。
7. 调用 `risk.compute(window="6M", currency="USD")`；断言 `observations ≥ 60`，相关矩阵对角线全为 `1.0`。
8. 发送未知方法和格式错误参数，分别断言 `INVALID_ARGUMENT` 与可展示中文 `message`。
9. 启动长请求并发送 `$/cancel`；从发送到收到 `CANCELLED` 必须 ≤ 200 ms。
10. Playwright 启 Vite；初始化脚本安装 §5.2 的 IPC；页面加载后等待“投资逻辑哨兵”标题和核心就绪。
11. 在 1440×900 与 1024×700 依次打开今日、持仓、扫描、交易、风险、设置；断言无页面级横向滚动、无未捕获控制台错误。
12. 注入 `core://status=restarting`，断言进行中的按钮禁用且有提示；重启核心后重新 bootstrap，不丢已有数据。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码/结果 | 用户可见文案（messages 键） |
|---|---|---|---|
| 核心 30 秒未 ready | 测试失败，附 stderr 最后 50 行 | `TIMEOUT` | `error.TIMEOUT` |
| 收到非 JSON stdout | 测试失败，打印原始行 | `INTERNAL` | `error.INTERNAL` |
| 响应 ID 不匹配 | 丢弃并失败，不串到其他请求 | `INTERNAL` | 测试专用断言 |
| 离线时请求刷新行情 | 页面保留缓存并提示 | `SOURCE_UNAVAILABLE` | `error.SOURCE_UNAVAILABLE` |
| 核心崩溃 | 状态变 `restarting`，未完成调用失败 | `INTERNAL` | `核心已重启，请重试` |
| 1024×700 横向溢出 | 场景失败并保存截图 | — | 不适用 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_core_ready_then_bootstrap` | `test_core_lifecycle.py` | 新临时目录 | 通知顺序 `app.ready`；bootstrap 成功 |
| `test_cancel_returns_within_200ms` | 同上 | 人为延迟处理器 + `$/cancel` | 耗时 ≤ 200 ms，code=`CANCELLED` |
| `test_shutdown_exits_within_three_seconds` | 同上 | `app.shutdown` | 退出码 0，≤ 3 s |
| `test_spaces_and_chinese_path` | 同上 | `含 空格 目录` | 启动成功，日志文件存在 |
| `test_demo_inbox_exact_counts` | `test_demo_flow.py` | `demo.load` | `3` 待处理、`1` 待确认 |
| `test_decision_act_and_reopen` | 同上 | 第一条判定 | 处理后 2，重开后 3 |
| `test_paper_advance_moves_clock_exactly_one_day` | `test_paper_risk_flow.py` | 演示账户 | `2026-10-29 → 2026-10-30` |
| `test_risk_has_60_observations` | 同上 | 6M、USD | `observations ≥ 60`，对角 `1.0` |
| `test_offline_scan_fails_without_losing_inbox` | 同上 | `scan.start` | `SOURCE_UNAVAILABLE`，清单仍 3 |
| `test_real_core_six_pages_have_data` | `demo-flow.spec.ts` | 1440 与 1024 | 六页有内容，无控制台错误 |
| `test_core_restart_keeps_local_data` | `failures.spec.ts` | 注入重启 | 重启后仍见 3 条待处理 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `core/tests/integration/fixtures/bad_line.txt` | 一行非 JSON | 手工写入 |
| `core/tests/integration/fixtures/restart.json` | 重启通知序列 | 手工构造，字段按 05 通知表 |
| `apps/desktop/e2e/real-core/.auth/` | 无 | 不保存任何密钥或登录态 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd core && uv run pytest tests/integration -q -m integration
# 期望：11 passed，0 failed；总耗时 < 120 s
cd apps/desktop && pnpm exec playwright test -c e2e/real-core/playwright.config.ts
# 期望：11 passed，0 failed；无网络请求
scripts/check.sh
# 期望：失败 0
```

### 9.2 完成清单
- [ ] 真实核心和真实前端在同一场景中跑通，不只 mock
- [ ] §8.1 的 11 个测试全部存在且通过
- [ ] 先失败证据已写状态文件
- [ ] 离线、取消、重启、空格/中文路径均有记录
- [ ] 未修改契约、业务代码或生产 IPC
- [ ] 已写 `docs/wp/status/I-01.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| I-02 | 六页场景、固定计数、离线模式 | 验收复用 fixture，不复制页面逻辑 |
| W-05 | 同一 RPC 场景与临时目录规则 | Windows 结果单独记录 |
| U-08 | 重启和错误提示断言 | 文案变更必须同步 i18n 与测试 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| Tauri 内部 API 版本变化 | 模拟 invoke 后页面无响应 | 锁定 C-05 使用的 API 版本；测试桥只跟随已锁版本 |
| 核心与 Vite 启动竞争 | bootstrap 早于 ready | fixture 必须等 `app.ready`，禁止固定 sleep |
| 测试污染真实数据 | 临时目录外出现 DuckDB | 断言 `SENTINEL_DATA_DIR` 在 `tmp_path` 下，否则拒绝运行 |

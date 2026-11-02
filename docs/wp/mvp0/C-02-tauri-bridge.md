---
id: C-02
title: Rust 桥接：核心进程监督与消息转发
phase: mvp0
platform: shared
lane: core
deps: [C-01]
size: M
owns: [apps/desktop/src-tauri/src/bridge.rs, apps/desktop/src-tauri/src/bridge/process.rs, apps/desktop/src-tauri/src/bridge/commands.rs, apps/desktop/src-tauri/src/bridge/security.rs, apps/desktop/src-tauri/src/lib.rs, apps/desktop/src-tauri/tests/bridge.rs]
appends: []
stubs: []
---

# C-02 Rust 桥接：核心进程监督与消息转发

## 0. 一眼看懂

- **目标**：让 Tauri 主进程只负责启动、监督和转发 Python 核心进程；把一行请求写进 stdin，把核心进程 stdout 的每一行作为 `core://message` 事件交给前端。
- **完成后解锁**：W-02、I-01；前端可以接真实核心进程，不再只依赖 mock。
- **预计规模**：Rust 约 520 行，测试约 220 行；`bridge.rs`、3 个 `bridge/` 子模块和一个集成测试文件。
## 1. 背景与边界

### 1.1 为什么需要它

核心进程是独立子进程，生命周期比一个 Tauri 命令长。Rust 若只做 `Command::spawn()`，会在崩溃后留下孤儿进程、让前端永远等 Promise、或者把内部心跳响应误当成业务响应。桥接层把进程监督、内部请求、外部请求和事件转发分开。

### 1.2 范围内

1. 按 `SENTINEL_CORE_CMD` 启动核心进程；默认命令为 `uv run --project core python -m sentinel`（C-07 的入口）。
2. 注入 `--data-dir`、`--parent-pid`、`--resource-dir`、`--log-level`，设置 UTF-8 环境变量。
3. 读取 stdout/stderr；stdout 每行发 `core://message`，以 `rs-` 开头的响应只交给桥接内部。
4. 提供 `rpc_send` 和 `open_external` 两个 Tauri 命令。
5. 心跳、崩溃重启、退出时杀进程树；状态发 `core://status`。
6. 提供最终 CSP 常量，禁止远程脚本、远程字体、`eval` 和非同源连接。

### 1.3 明确不做

| 不做 | 由谁做 |
|---|---|
| JSON-RPC 方法分发、参数模型、业务错误 | C-01 与各业务工作包 |
| 前端 Promise、超时和 mock | C-05 |
| 修改 `src/main.rs`、`tauri.conf.json` | 不改；本包只改 `src/lib.rs` 的装配行，调用 `bridge::install(builder)` |
| 解析用户持仓、逻辑、行情或账本 | 所有业务逻辑只在 Python |
| Windows 控制台隐藏和 `taskkill` 细节 | W-01 的 `Platform` 实现 |
| v1 安装包中的 PyInstaller 资源路径 | M-pack（v1） |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | 3.2 代码命名、4 时间与数值、5 环境变量 | 命令、事件和超时 |
| [02-技术架构.md](../../02-技术架构.md) | 6.1 Rust 与核心进程、6.2 Rust 与前端、8 启动与退出、13 安全 | 必须实现的桥接语义 |
| [05-接口契约.md](../../05-接口契约.md) | 1 传输、2 消息格式、6 通知 | stdout 行和事件格式 |
| [09-测试与评测.md](../../09-测试与评测.md) | 2.2 确定性、5 安全与隔离 | 不联网测试与安全断言 |
| [WP-00-skeleton.md](WP-00-skeleton.md) | 5.9 `Platform` trait、5.8 `lib.rs` | 启动、结束和装配接缝 |
## 3. 前置条件

- C-01 已合并：`python -m sentinel.rpc` 能接受 stdin 并输出 NDJSON；`app.ping` 和 `app.shutdown` 可用。自定义入口 `python -m sentinel` 由 C-07 交付；在 C-07 合并前，测试用 `SENTINEL_CORE_CMD` 指向假核心。
- WP-00 已合并：`Platform::prepare_core_command`、`kill_process_tree`、`init_script` 可用。
- Rust 依赖只使用 WP-00 锁定的 `tauri`、`serde`、`serde_json`；不新增 crate。
- 测试不需要启动真实 WebView，不访问网络，不读取用户数据目录。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `apps/desktop/src-tauri/src/bridge.rs` | 新建 | 模块根：`BridgeState`、`CoreStatus`、`install`、错误类型 |
| `apps/desktop/src-tauri/src/bridge/process.rs` | 新建 | 命令解析、启动、stdin/stdout/stderr、重启与退出 |
| `apps/desktop/src-tauri/src/bridge/commands.rs` | 新建 | `rpc_send`、`open_external` 的参数校验 |
| `apps/desktop/src-tauri/src/bridge/security.rs` | 新建 | CSP 常量、URL 校验、1 MiB 限制 |
| `apps/desktop/src-tauri/src/lib.rs` | 修改 | 在 `run()` 的 Builder 上调用 `bridge::install(builder)`，其余保持 WP-00 结构 |
| `apps/desktop/src-tauri/tests/bridge.rs` | 新建 | §8.1 的 Rust 测试 |
## 5. 接口规格

### 5.1 公开接口

```rust
#[derive(Clone, serde::Serialize)]
pub struct CoreStatus { pub state: CoreState, pub attempt: u8 }
#[derive(Clone, Copy, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum CoreState { Starting, Ready, Restarting, Failed }

pub struct BridgeState { /* manager: Mutex<CoreManager>, status: RwLock<CoreStatus> */ }
pub struct BridgeError { pub code: BridgeErrorCode, pub message: String }
pub enum BridgeErrorCode { NotReady, LineTooLarge, InvalidUrl, SpawnFailed, WriteFailed, Timeout }

pub fn install<R: tauri::Runtime>(builder: tauri::Builder<R>) -> tauri::Builder<R>;
pub fn send_line(state: &BridgeState, line: &str) -> Result<(), BridgeError>;
pub fn shutdown(state: &BridgeState) -> Result<(), BridgeError>;
pub fn status(state: &BridgeState) -> CoreStatus;
pub fn csp() -> &'static str;

#[tauri::command]
pub async fn rpc_send(line: String, state: tauri::State<'_, BridgeState>)
    -> Result<(), String>;
#[tauri::command]
pub async fn open_external(url: String, app: tauri::AppHandle) -> Result<(), String>;
```

`install` 只安装 state、命令和事件 handler，不创建业务窗口；`send_line` 在 `CoreState::Ready` 之外返回 `NotReady`；`open_external` 只接受 `https://` 且主机名非空的 URL。所有公开函数不 panic，错误通过 `BridgeError` 或 Tauri 的 `Result` 返回。

### 5.2 数据结构

| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `CoreStatus` | `state` | `CoreState` | 是 | 四个枚举值 | 进程状态 |
| | `attempt` | `u8` | 是 | 0–3 | 当前重启尝试 |
| 内部请求 | `rs-ping-<n>` | `String` | 是 | 以 `rs-` 开头 | 心跳请求 |
| | `rs-shutdown-<n>` | `String` | 是 | 以 `rs-` 开头 | 关闭请求 |
| 外部请求 | `line` | `String` | 是 | UTF-8 字节数 ≤ 1,048,576 | 前端原始 JSON 行 |
| URL | `url` | `String` | 是 | `https` scheme，host 非空 | 外链 |

### 5.3 常量与配置

| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MAX_LINE_BYTES` | `1_048_576` | `security.rs` | 单行上限 |
| `CORE_HEARTBEAT_INTERVAL` | `5 s` | `process.rs` | 心跳间隔 |
| `CORE_HEARTBEAT_TIMEOUT` | `2 s` | `process.rs` | 心跳响应超时 |
| `CORE_MAX_RESTARTS` | `3` | `process.rs` | 最多重启次数 |
| `RESTART_DELAYS_MS` | `[1000, 2000, 4000]` | `process.rs` | 重启退避 |
| `SHUTDOWN_GRACE` | `3 s` | `process.rs` | 等待优雅退出 |
| `CSP_POLICY` | 见 §6.6 | `security.rs` | Tauri CSP |

## 6. 实现步骤

1. **解析命令**：读取 `SENTINEL_CORE_CMD`；为空时用默认命令。按 ASCII 空白分割，第一段是可执行文件，其余是参数；空命令、含引号的命令或空可执行文件返回 `SpawnFailed`。**不执行 shell**。
2. **组装参数**：追加 `--data-dir <app_data_dir>`、`--parent-pid <std::process::id()>`、`--resource-dir <resource_dir>`、`--log-level <SENTINEL_LOG_LEVEL 或 info>`；调用 `Platform::prepare_core_command`。
3. **启动**：设置 `stdin/stdout/stderr = piped`，设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`；立即发 `core://status {state:"starting",attempt:0}`。进程启动失败时发 `failed` 并返回 `SpawnFailed`。
4. **读 stdout**：按 `\n` 切行，去掉 `\r`；空行跳过；每行若以 `{"jsonrpc":"2.0","id":"rs-` 对应的内部 id 开头，则交给内部 pending map，否则 `app.emit("core://message", line)`。单行超过 1 MiB 时记录并丢弃，不改写。
5. **心跳**：每 5 s 发送 `app.ping`，id 为 `rs-ping-<单调递增>`；2 s 内没有响应记一次失败；连续 3 次失败调用 `restart()`。收到任意 `app.ready` 或成功 `app.ping` 响应后把状态置为 `ready`、`attempt=0`。
6. **退出与重启**：等待线程检测到 `child.wait()`；若用户主动关闭则状态 `failed` 并停止；否则发 `restarting`，按 1/2/4 s 等待后重试。第 3 次仍失败发 `failed`，不无限重试。
7. **关闭**：发送 `rs-shutdown-<n>` 的 `app.shutdown`，等待 3 s；超时后调用 `Platform::kill_process_tree`；关闭 stdin，清空 pending map（每个 Promise 返回 `Timeout`），不把内部响应转发给前端。
8. **CSP**：`csp()` 返回 `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src ipc: http://ipc.localhost; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`。**禁止** `eval`、`unsafe-eval`、远程 `https:` 脚本或字体。
9. **装配**：在 `src/lib.rs` 的 `run()` 中，对 `tauri::Builder` 调用 `bridge::install(builder)`，再调用 `.run(...)`；这是本包对 `lib.rs` 的唯一修改。`main.rs` 继续调用 `sentinel_lib::run()`，不改。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码/事件 | 用户可见文案 |
|---|---|---|---|
| 核心未启动或重启中调用 `rpc_send` | 不写入 pipe | `NotReady` | “核心进程尚未就绪，请稍后重试。” |
| 行超过 1 MiB | 不发送 | `LineTooLarge` | “请求超过 1 MB，无法发送。” |
| 子进程启动失败 | 状态 `failed` | `SpawnFailed` | “核心进程无法启动，请查看日志。” |
| pipe 写入失败 | 触发一次重启 | `WriteFailed` | “核心进程已断开，正在重启。” |
| 心跳连续 3 次超时 | 杀进程并重启 | `core://status` | “核心进程无响应，正在重启。” |
| 重启 3 次仍失败 | 不再自动重试 | `core://status failed` | “核心进程无法启动。” |
| 非 https 或空 host | 不打开外链 | `InvalidUrl` | “只允许打开 https 链接。” |
| stdout 出现非 JSON 行 | 仍作为 `core://message` 转发，前端解析失败并记录 | — | 不暴露 stderr 给用户 |

## 8. 测试（先写）

### 8.1 测试清单

| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_parse_core_command_uses_whitespace` | `tests/bridge.rs` | `"uv run --project core python -m sentinel"` | 7 个 argv，第一项 `uv` |
| `test_empty_core_command_is_rejected` | 同上 | `""` | `BridgeErrorCode::SpawnFailed` |
| `test_build_args_contains_data_and_parent` | 同上 | `data=/tmp/a b`，`pid=42` | 包含 `--data-dir`、`/tmp/a b`、`--parent-pid`、`42` |
| `test_rpc_send_rejects_over_one_mib` | 同上 | `String` 长度 `1_048_577` | `LineTooLarge`，没有写入 pipe |
| `test_rpc_send_rejects_before_ready` | 同上 | 新 `BridgeState`，状态 `Starting` | `NotReady` |
| `test_rs_response_is_not_forwarded` | 同上 | stdout 行 id `rs-ping-1` | 不进 `core://message`，pending 收到结果 |
| `test_restart_delays_are_one_two_four_seconds` | 同上 | 三次失败 | 记录 `1000`、`2000`、`4000` |
| `test_open_external_rejects_http_and_file` | 同上 | `http://a`、`file:///x` | 都返回 `InvalidUrl` |
| `test_csp_forbids_eval_and_remote_scripts` | 同上 | `csp()` | 不含 `unsafe-eval`，不含 `script-src https:` |

### 8.2 Fixture

| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增 fixture | 使用 `std::process::Command::new("sh")` 的固定脚本模拟 stdout | 测试内创建临时脚本，不访问网络 |
| 进程测试 | `while read line; do printf ...; done` | 仅 Unix 测试标记 `#[cfg(unix)]`；Windows 由 W-02 用等价命令验证 |

## 9. 验收

### 9.1 命令与期望输出

```bash
cd apps/desktop/src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test --test bridge
# 期望：9 passed；0 failed
```

### 9.2 完成清单

- [ ] 第 4 节每个文件已创建
- [ ] 第 8.1 节 9 个测试全部存在且通过
- [ ] stdin/stdout 只有一行一个 JSON 对象，不打印调试文本
- [ ] `csp()` 的字符串与 §6.6 完全一致
- [ ] 没有修改 `owns` 之外的路径，没有新增 crate
- [ ] 已写 `docs/wp/status/C-02.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| W-02 | `Platform::prepare_core_command`、`kill_process_tree` | Windows 必须隐藏控制台并清理进程树 |
| I-01 | `bridge::install`、`core://message`、`core://status` | 由装配根调用 `install`；前端不解析 `rs-` 响应 |
| C-05 | `rpc_send` 参数与错误文案 | 任何非 `https` 外链都在 Rust 侧拒绝 |
| 所有前端页面 | `core://status` | `starting/ready/restarting/failed` 只改变外壳状态，不阻塞读取已有数据 |

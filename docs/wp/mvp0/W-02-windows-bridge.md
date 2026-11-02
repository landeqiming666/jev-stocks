---
id: W-02
title: Windows 核心进程桥接对等
phase: mvp0
platform: windows
lane: windows
deps: [W-01, C-02]
size: M
owns: [apps/desktop/src-tauri/src/bridge/windows.rs, apps/desktop/src-tauri/tests/bridge_windows.rs]
appends: []
stubs: []
---

# W-02 Windows 核心进程桥接对等

## 0. 一眼看懂

- **目标**：在 Windows 11 x64 上用真实 C-02 桥接驱动真实/受控核心进程，证明启动、NDJSON、超限、取消、崩溃、重启、路径与退出行为与 macOS 一致。
- **完成后解锁**：W-05。
- **预计规模**：约 430 行，其中 Windows 测试辅助 120 行、集成测试 310 行。

## 1. 背景与边界

### 1.1 为什么需要它
Windows 最常见的问题不是编译失败，而是控制台窗口闪出、`.cmd` 解析错误、CRLF 污染 NDJSON、强杀留下 `python.exe`、含中文路径导致启动失败。W-01 已实现平台原语，本包验证 C-02 真正使用它们。

### 1.2 范围内
1. `bridge/windows.rs` 只提供测试辅助，不复制生产逻辑。
2. 通过 C-02 公开 API 做真实桥接测试。
3. 覆盖 `app.ready`、请求/响应 ID、UTF-8、1 MB 上限、取消、子进程退出、重启和进程树清理。
4. 结果写入 Windows 对等矩阵。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 修改 `CoreProcess`、RPC 线格式或 `platform/mod.rs` 接口 | 禁止；发现问题走变更申请 |
| 重写 `prepare_core_command`、`kill_process_tree` | W-01 已实现 |
| 安装包、托盘、自启 | v1 |
| 真实 SEC/Jev 网络调用 | G0、D-01 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [02-技术架构.md](../../02-技术架构.md) | 6 Rust/核心桥接、8 启动退出与心跳、12 稳定性 | 行为基线 |
| [05-接口契约.md](../../05-接口契约.md) | 1 传输、2 消息格式、3.2 错误码 | NDJSON 与错误形状 |
| [10-协作与工作包规范.md](../../10-协作与工作包规范.md) | 9 Windows 车道协议 | 不改共享接口 |
| [decisions.md](../../decisions.md) | [ADR-016](../../decisions.md#adr-016--mac-与-windows-分车道并行开发平台差异隔离在平台层) | 平台隔离 |
| [W-01-windows-platform-layer.md](W-01-windows-platform-layer.md) | 5.2 `windows.rs`、8.1 手工项 | 已交付的平台原语 |

## 3. 前置条件

- W-01 已通过，`scripts\check.ps1` 全绿。
- C-02 导出：
  ```rust
  pub struct CoreProcessConfig { pub command: Vec<OsString>, pub cwd: PathBuf, pub env: Vec<(OsString, OsString)> }
  pub struct CoreProcess;
  impl CoreProcess {
      pub fn spawn(config: CoreProcessConfig) -> Result<Self, BridgeError>;
      pub fn send_line(&self, line: &str) -> Result<(), BridgeError>;
      pub fn recv_line(&self, timeout: Duration) -> Result<String, BridgeError>;
      pub fn status(&self) -> CoreStatus;
      pub fn restart(&mut self) -> Result<(), BridgeError>;
      pub fn shutdown(&mut self) -> Result<i32, BridgeError>;
  }
  ```
- C-02 已规定：超过 1 MB 的请求在 Rust 层拒绝；`core://message` 原样转发一行，不重新序列化。
- Windows 测试使用临时目录，不读写用户真实数据目录。

## 4. 交付物清单

| 路径 | 动作 | 新建/覆盖 | 职责 |
|---|---|---|---|
| `apps/desktop/src-tauri/src/bridge/windows.rs` | 新建 | 新建 | 仅测试辅助：临时目录、配置构造、进程/文件探测 |
| `apps/desktop/src-tauri/tests/bridge_windows.rs` | 新建 | 新建 | Windows 桥接集成测试与 fake core fixture 生成器 |

`bridge/windows.rs` 只有在 `tests/bridge_windows.rs` 中通过 `#[path = "../src/bridge/windows.rs"] mod bridge_probe;` 编译；共享生产模块不得 `mod bridge;` 引用它。

## 5. 接口规格

### 5.1 测试辅助接口
```rust
pub(crate) struct BridgeProbeConfig {
    pub root: PathBuf,
    pub data_dir: PathBuf,
    pub python: OsString,
}

pub(crate) fn make_probe_config(label: &str) -> BridgeProbeConfig;
pub(crate) fn fake_core_config(cfg: &BridgeProbeConfig, script: &Path) -> CoreProcessConfig;
pub(crate) fn real_core_config(cfg: &BridgeProbeConfig) -> CoreProcessConfig;
pub(crate) fn write_fake_core(cfg: &BridgeProbeConfig, body: &str) -> PathBuf;
pub(crate) fn count_child_processes(root_pid: u32) -> usize;
```
所有辅助函数只在 Windows 目标编译，返回路径必须是绝对路径。`make_probe_config` 使用 `temp_dir()/sentinel-bridge-<pid>-<atomic>`，目录名含空格与中文 `桥 接`，测试结束由调用方删除。

### 5.2 测试数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `root` | PathBuf | 是 | 绝对、含空格/中文 | 仓库临时映射根 |
| `data_dir` | PathBuf | 是 | 位于 `root` 下 | 核心数据目录 |
| `python` | OsString | 是 | 来自 `py -3` 探测 | 子进程解释器 |
| `startsFile` | PathBuf | 是 | fake core 每次启动追加一行 | 重启计数 |
| `readyLine` | String | 是 | 合法 NDJSON，含 `app.ready` | 握手 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `START_TIMEOUT` | `30s` | 测试 | 首次编译/启动等待 |
| `IO_TIMEOUT` | `5s` | 测试 | 单行读写 |
| `MAX_LINE_BYTES` | `1048576` | C-02 | 1 MB 上限 |
| `RESTART_LIMIT` | `3` | C-02 | 最多重启次数 |
| `SHUTDOWN_WAIT` | `3s` | C-02 | 优雅退出等待 |

## 6. 实现步骤

1. 先写 `test_bridge_*`，用尚不存在或未接通的辅助运行，记录失败输出。
2. `make_probe_config` 用进程 ID 和 `AtomicU64` 生成唯一目录，调用 `create_dir_all`；路径显式包含 `含 空格 中文`。
3. `write_fake_core` 写 UTF-8 脚本到临时目录；脚本只使用标准库，接收 `--data-dir`，按 JSON Lines 回显固定响应。
4. `test_bridge_startup_handshake_and_bootstrap` 启动 fake core，读到 `app.ready` 后发送 `app.bootstrap`，断言 `id`、`result.protocolVersion`。
5. `test_bridge_preserves_utf8_chinese_around_newlines` 发送含“投资逻辑哨兵”的参数，收到同一 UTF-8 字节，行尾仅一个 `\n`。
6. `test_bridge_rejects_line_over_1mb` 构造 `1_048_577` 字节字符串；`send_line` 返回 `BridgeError::LineTooLarge`，子进程未收到请求。
7. `test_bridge_forwards_cancel_response_within_200ms` 用 fake core 延迟 2 秒，再发送 `$/cancel`，记录 `Instant`，断言 `CANCELLED` ≤ 200 ms。
8. `test_bridge_reports_child_exit` 让 fake core 以 7 退出；桥状态为 `failed`，错误包含退出码 7，不无限等待。
9. `test_bridge_restarts_after_crash` 按 C-02 策略重启；`startsFile` 从 1 行变 2 行，窗口内状态序列为 `failed→restarting→ready`。
10. `test_bridge_stops_without_orphan` 启动 `python -c "import time; time.sleep(60)"` 的父/子链，调用 `shutdown` 和平台 `kill_process_tree`；3 秒内无子进程。
11. `test_real_core_accepts_bootstrap_on_windows` 通过 `real_core_config` 启动真实 `python -m sentinel`，离线完成 `app.bootstrap` 与 `app.shutdown`。
12. 在 `docs/wp/windows-matrix.md` 为 C-02 和 W-02 各写一行，附命令、结果和截图路径。

## 7. 错误与边界情况

| 情形 | 行为 | 错误 | 用户可见文案（messages 键） |
|---|---|---|---|
| 启动命令不存在 | 30 秒内失败，保留 OS 错误 | `BRIDGE_SPAWN_FAILED` | 前端显示核心无法启动 |
| 单行超 1 MB | 不写 stdin，立即拒绝 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| CRLF 出现在核心输出 | 去掉末尾 `\r` 后按一行处理 | — | 日志记 warn，不展示 |
| 非法 UTF-8 | 状态 failed，记录偏移与长度 | `INTERNAL` | `error.INTERNAL` |
| 子进程退出 | 未完成请求 `INTERNAL`，允许重启 | `INTERNAL` | `核心已重启，请重试` |
| 3 次重启仍失败 | 状态 failed，不继续拉起 | `INTERNAL` | `核心进程无法启动` |
| 强杀留下子进程 | 测试失败，标 A/B 类并记录 | — | 不适用 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_bridge_startup_handshake_and_bootstrap` | `tests/bridge_windows.rs` | fake core | `app.ready` 后 bootstrap 成功 |
| `test_bridge_preserves_utf8_chinese_around_newlines` | 同上 | “投资逻辑哨兵/多行” | 字节等价，仅 `\n` |
| `test_bridge_rejects_line_over_1mb` | 同上 | `1_048_577` 字节 | `LineTooLarge`，无 stdin 写入 |
| `test_bridge_forwards_cancel_response_within_200ms` | 同上 | 2 秒延迟任务 | `≤ 200 ms`，`CANCELLED` |
| `test_bridge_reports_child_exit` | 同上 | exit 7 | status failed，含 7 |
| `test_bridge_restarts_after_crash` | 同上 | fake core 首次退出 | starts 文件 2 行，最多 3 次 |
| `test_bridge_stops_without_orphan` | 同上 | 父子 sleep 进程 | 3 秒内子进程 0 |
| `test_real_core_accepts_bootstrap_on_windows` | 同上 | 真实核心、离线 | bootstrap 成功，shutdown 0 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `tests/bridge_windows.rs` 内联 `FAKE_CORE` | 标准库 JSON 行回显、延迟、崩溃模式 | 测试运行时写临时 `.py`，不入库 |
| `tmp/含 空格 中文/sentinel` | 隔离数据目录 | `make_probe_config` 创建 |
| 无真实密钥、无 SEC 缓存 | — | 全部离线 |

## 9. 验收

### 9.1 命令与期望输出
```powershell
cd apps\desktop\src-tauri
cargo test --test bridge_windows -- --test-threads=1
# 期望：8 passed；0 failed；无残留 python.exe
cargo fmt --check
# 期望：退出码 0
cargo clippy --all-targets -- -D warnings
# 期望：退出码 0
cd ..\..\..
scripts\check.ps1
# 期望：失败 0
```

### 9.2 完成清单
- [ ] 8 个测试全部存在，先失败证据已记录
- [ ] 真实核心在 Windows 上完成 bootstrap/shutdown
- [ ] 1 MB、取消、崩溃、重启、孤儿进程五类边界有证据
- [ ] `bridge/windows.rs` 未被生产模块引用，未改共享接口
- [ ] 对等矩阵已更新
- [ ] 已写 `docs/wp/status/W-02.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| W-05 | `BridgeProbeConfig`、无孤儿测试 | 复用临时目录规则，不启动真实用户实例 |
| C-02 维护者 | Windows 失败样本 | 只附复现测试和变更申请，不直接改共享代码 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| C-02 没有可注入配置 | W-02 无法启动 fake core | 停写并提接口变更申请，禁止复制桥接实现 |
| Windows 杀软拦截 `python.exe` | 测试超时或文件被锁 | 使用本地临时目录，记录为环境 C 类，不降低断言 |
| WebView 未启动导致窗口测试失败 | 与桥接无关 | 桥接测试保持 headless；窗口验收留 W-05 |

---
id: C-01
title: RPC 服务端：线程模型、分发、取消
phase: mvp0
platform: shared
lane: core
deps: [C-00]
size: M
owns: [core/sentinel/rpc/, core/tests/unit/rpc/]
appends: []
stubs: []
---

# C-01 RPC 服务端：线程模型、分发、取消
## 0. 一眼看懂
- **目标**：实现 Python 核心进程的 NDJSON JSON-RPC 2.0 服务端，包括 reader、writer、4 个 worker、取消登记、错误封装和 `app.ping` / `app.shutdown` 两个内置方法。
- **完成后解锁**：C-02、C-04、P-01、P-05、P-06；后续业务工作包只需注册处理器，不修改传输层。
- **预计规模**：实现约 520 行，测试约 260 行；7 个实现文件和 5 个测试文件。

## 1. 背景与边界
### 1.1 为什么需要它
Rust 通过 stdin/stdout 转发请求，前端只认「一个请求对应一个响应」和 `core://message`。如果不把读取、线程池、取消和 writer 统一实现，心跳可能被长任务堵住，取消可能等不到 worker，两个线程也可能同时污染 stdout。
### 1.2 范围内
1. 解析单行 JSON 请求，校验 JSON-RPC 2.0 子集和 1 MiB 上限。
2. reader 线程直接处理 `app.ping` 与 `$/cancel`，其余请求提交固定 4 线程池。
3. `Dispatcher` 完成方法查找、参数校验、结果序列化和错误映射；`CancelRegistry` 保证 200 ms 内写出 `CANCELLED`。
4. 唯一 writer 线程写 stdout；日志只走 stderr 或 `logging_setup` 的文件 handler；内置 `app.shutdown` 和 `python -m sentinel.rpc` 入口。
### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| `app.bootstrap`、`settings.*`、`secrets.*` 的业务实现 | C-04 |
| 扫描取消、Jev 请求取消和批次落库 | P-02、S-05 |
| Rust 进程启动、重启和前端事件转发 | C-02 |
| 前端 Promise、超时和 mock | C-05 |
| 生成业务方法的参数与结果模型 | 各方法所属工作包 |
| 修改 `sentinel/__main__.py` | **不做**；产品入口由 C-07 创建（`python -m sentinel`），本包只提供 `python -m sentinel.rpc` 供单元测试 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | 3.1 业务 ID、3.2 代码命名、4 时间与数值、5 环境变量 | `id`、时间、布尔和错误字段 |
| [02-技术架构.md](../../02-技术架构.md) | 6.1 Rust 与核心进程、7 线程模型与取消、8 启动与超时 | 必须实现的线程和生命周期 |
| [05-接口契约.md](../../05-接口契约.md) | 1 传输、2 消息格式、3 错误、7.3 订单状态、8 并发与幂等 | wire 格式与错误语义 |
| [09-测试与评测.md](../../09-测试与评测.md) | 4 契约测试、5 安全与隔离、6 端到端场景 | 测试命名与断言 |
## 3. 前置条件
- WP-00 已合并：`core/pyproject.toml` 可运行 `uv run pytest`，`sentinel.rpc` 在分层规则中属于 `app` 层。
- C-00 已合并：可导入 `CancelledError`、`UserError`、`InternalError`、`get_logger`、`render`、`clock.now`。
- 只使用标准库和已锁定的 `pydantic>=2`；不新增依赖，不访问网络。
- `sentinel.platform.is_process_alive` 已由 WP-00 提供；C-01 只用它实现 `--parent-pid` 看门狗。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/rpc/__init__.py` | 新建 | 导出 `RpcServer`、`Dispatcher`、`CancelToken`、`ServerConfig`、`main` |
| `core/sentinel/rpc/protocol.py` | 新建 | 请求/响应数据类、解析、序列化和 1 MiB 限制 |
| `core/sentinel/rpc/cancel.py` | 新建 | `CancelToken`、`CancelRegistry` 和 200 ms 取消响应 |
| `core/sentinel/rpc/dispatcher.py` | 新建 | `MethodSpec`、`RequestContext`、处理器注册和错误转换 |
| `core/sentinel/rpc/writer.py`、`server.py` | 新建 | 有界写队列、唯一 writer、reader、worker、watchdog、启动和停止 |
| `core/sentinel/rpc/builtins.py` | 新建 | `app.ping` 与 `app.shutdown` |
| `core/sentinel/rpc/__main__.py` | 新建 | 命令行参数解析和 `main()` |
| `core/tests/unit/rpc/test_{protocol,cancel,dispatcher,server,builtins}.py` | 新建 | §8.1 的 13 个测试 |

## 5. 接口规格
### 5.1 公开接口
```python
@dataclass(frozen=True)
class ServerConfig:
    max_line_bytes: int = 1_048_576
    workers: int = 4
    cancel_deadline_ms: int = 200
    shutdown_timeout_s: float = 3.0
    ping_timeout_s: float = 2.0
class CancelToken:
    def cancel(self) -> None: ...
    @property
    def cancelled(self) -> bool: ...
    def is_cancelled(self) -> bool: ...   # cancelled 的方法形式；供 semantic 层的 Protocol 结构化匹配
    def raise_if_cancelled(self) -> None: ...  # 抛出 CancelledError
class CancelRegistry:
    def register(self, request_id: str, token: CancelToken, *, cancellable: bool = False) -> None: ...
    def cancel(self, request_id: str) -> bool: ...  # 已登记且可取消返回 True；未知或不可取消返回 False（不置位）
    def unregister(self, request_id: str) -> None: ...
Handler = Callable[[BaseModel, "RequestContext"], BaseModel | dict[str, object]]
@dataclass(frozen=True)
class MethodSpec:
    method: str
    handler: Handler
    params_model: type[BaseModel]
    result_model: type[BaseModel] | None
    timeout_ms: int = 30_000
    cancellable: bool = False
class Dispatcher:
    def register(
        self, method: str, handler: Handler, params_model: type[BaseModel],
        result_model: type[BaseModel] | None = None, timeout_ms: int = 30_000,
        *, cancellable: bool = False, replace: bool = False,
    ) -> None: ...
    def dispatch(self, spec: MethodSpec, raw_params: object, ctx: RequestContext) -> dict[str, object]: ...
    def lookup(self, method: str) -> MethodSpec | None: ...
    def methods(self) -> tuple[str, ...]: ...
class RpcServer:
    def __init__(self, stdin: BinaryIO, stdout: BinaryIO, dispatcher: Dispatcher,
                 config: ServerConfig = ServerConfig(), *, parent_pid: int | None = None) -> None: ...
    def start(self) -> None: ...
    def serve_forever(self) -> None: ...
    def stop(self) -> None: ...
    def notify(self, method: str, params: Mapping[str, object]) -> None: ...
    @property
    def stopped(self) -> bool: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```
参数规则：`method` 必须匹配 `^[a-z][a-z0-9]*(\.[A-Za-z][A-Za-z0-9]*)+$`；`request_id` 长度为 1–64，字符为可打印 ASCII；`raw_params` 必须是 JSON 对象。`register(..., replace=False)` 遇到重复方法抛 `ValueError`；`replace=True` 只允许测试和覆盖内置方法时使用。`RpcServer.start` 只能调用一次，重复调用抛 `RuntimeError`。`stop` 可重复调用，第二次为空操作。

**取消边界**：默认 `cancellable=False`，收到 `$/cancel` 时**不置位、不响应**；只有显式声明 `cancellable=True` 的长任务（例如 `risk.compute`、导出）可以被取消。所有会改写账本或判定状态的方法（`holdings.*`、`thesis.*`、`decision.*`、`paper.*`、`settings.update`、`secrets.*`、`demo.*`）必须保持默认值。这样不会出现“回了 CANCELLED，但订单或处理动作已经提交”的状态。
### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| 请求 | `jsonrpc` | str | 是 | 等于 `"2.0"` | 协议标记 |
| | `id` | str | 是 | 1–64 字符；同一连接唯一 | 请求编号 |
| | `method` | str | 是 | §5.1 的方法名规则 | 方法名 |
| | `params` | object | 是 | 无 `null`；默认 `{}` 只用于无参方法 | 参数 |
| 错误响应 | `code` | str | 是 | [05] 15 个错误码之一 | 机器错误码 |
| | `message` | str | 是 | 非空中文 | 用户文案 |
| | `data.retryable` | bool | 是 | [05] 3.2 的固定值 | 是否可重试 |
| | `data.requestId` | str | INTERNAL 是 | 与请求 ID 相同 | 错误编号 |
| `RequestContext` | `request_id` | str | 是 | 当前请求 | 日志关联 |
| | `method` | str | 是 | 当前方法 | 日志关联 |
| | `cancel` | CancelToken | 是 | 请求独有 | 取消信号 |
| | `started_at` | datetime | 是 | UTC | 耗时计算 |
### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MAX_LINE_BYTES` | `1048576` | `protocol.py` | 单行 UTF-8 字节上限 |
| `CANCEL_DEADLINE_MS` | `200` | `server.py` | 取消响应上限 |
| `WORKER_COUNT` | `4` | `server.py` | 一般请求线程数 |
| `WRITE_QUEUE_SIZE` | `1024` | `writer.py` | 写队列上限 |
| `PING_METHOD` | `"app.ping"` | `builtins.py` | 心跳方法 |
| `SHUTDOWN_METHOD` | `"app.shutdown"` | `builtins.py` | 关闭方法 |
| `CANCELLED_MESSAGE_KEY` | `"error.CANCELLED"` | `messages` | 取消文案 |
## 6. 实现步骤
1. **writer**：创建 `queue.Queue(maxsize=1024)` 和 `threading.Thread(name="rpc-writer")`。`send` 把 `bytes` 放入队列；队列满时阻塞不超过 1 s，仍失败则记录 `rpc.writer.backpressure` 并丢弃通知，响应不得丢弃。
2. **reader**：输入已是 `BinaryIO`，使用 `stdin.readline(MAX_LINE_BYTES + 1)`；超限时丢弃该行余下字节，随后继续读下一完整行，不把残余字节当成新请求。有可校验 `id` 则写 `INVALID_ARGUMENT`，无 `id` 则只记日志。空行跳过。
3. **ping**：reader 解析 `app.ping` 后直接构造 `{"ok": True, "uptimeMs": int((now - started).total_seconds() * 1000)}`，不经过线程池。
4. **普通请求**：创建 `CancelToken`，调用 `CancelRegistry.register(id, token, cancellable=spec.cancellable)`，提交固定 4 个 worker 的线程池；提交前将请求状态保存为 `in_flight`。为保证不合作 handler 不阻塞解释器退出，允许使用 daemon worker。ping、cancel、shutdown 属于 reader 直通控制请求。
5. **分发**：`Dispatcher.lookup` 找不到方法时抛 `UserError("INVALID_ARGUMENT", reason="UNKNOWN_METHOD")`；用 `params_model.model_validate(raw_params)`，`ValidationError` 取第一条错误的点号路径作为 `data.field`。
6. **取消**：reader 收到 `$/cancel` 后解析 `params.id`，调用 `CancelRegistry.cancel`；该方法只在登记项存在且 `cancellable=True` 时置位并返回 `True`，未知或不可取消返回 `False`（不回 `CANCELLED`、不置位）。成功且状态仍未响应时，writer 立即写 `CANCELLED`，状态改为 `responded`；worker 返回时看到 `responded` 就丢弃结果。处理器必须在自己的写事务前调用 `raise_if_cancelled()`；RPC 层无法替处理器回滚已开始的事务。
7. **错误**：处理器抛 `SentinelError` 时调用 `to_wire(request_id)`；抛 `pydantic.ValidationError` 转为 `INVALID_ARGUMENT`；其他异常包装为 `InternalError("INTERNAL", detail=type(exc).__name__)`，再由 `to_wire(request_id)` 关联错误编号。日志不得写用户正文。
8. **关闭**：`app.shutdown` 返回 `{"ok": true}` 后设置 `stop_event`；server 停止接受新请求，worker 排空 3 s，writer 冲刷队列，最后关闭线程池。`force=true` 时不等待 worker。
9. **看门狗**：`parent_pid` 不为空时每 2 s 调用 `platform.is_process_alive`；连续 1 次为假就设置 `stop_event`，并以退出码 0 结束。每次检查间隔固定 2.0 s。
## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 请求不是 JSON 对象 | 有 id 则响应错误；无 id 只记日志 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 缺少 `jsonrpc` 或版本不是 2.0 | 拒绝该请求 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 未知方法 | 不执行处理器 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT`，`data.reason=UNKNOWN_METHOD` |
| 参数多字段或类型错误 | 不合并、不忽略 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT`，`data.field` |
| 单行超过 1 MiB | 不读取该行剩余部分；有 id 时响应 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 未知 id 或已完成请求被取消 | 空操作，不产生响应 | — | 不适用 |
| 处理器抛未预期异常 | 记录 `request_id`，响应带错误编号 | `INTERNAL` | `error.INTERNAL` |
| writer 队列满 | 通知可丢弃；响应最多等 1 s 后写 stderr 错误 | `INTERNAL` | `error.INTERNAL` |
| 父进程退出 | 看门狗停止服务并退出 | `CANCELLED` 或 `INTERNAL` 仅用于已登记请求 | `error.CANCELLED` |

## 8. 测试（先写）
### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_protocol_parses_minimal_ping_request` | `test_protocol.py` | `{"jsonrpc":"2.0","id":"r-1","method":"app.ping","params":{}}` | `request.id == "r-1"`，`request.method == "app.ping"` |
| `test_protocol_rejects_line_over_one_mib` | 同上 | `b"x" * 1048577` | `LineTooLarge`，`bytes == 1048577` |
| `test_protocol_serializes_one_line_with_lf_only` | 同上 | `{"jsonrpc":"2.0","id":"r-1","result":{"ok":true}}` | `payload.endswith(b"\n")` 且 `b"\r" not in payload` |
| `test_cancel_sets_token_and_raises_cancelled` | `test_cancel.py` | 新 token 调用 `cancel()` 后 `raise_if_cancelled()` | 抛 `CancelledError`，`code == "CANCELLED"` |
| `test_unknown_method_maps_to_invalid_argument` | 同上 | `lookup("nope.method")` | `None`；`dispatch` 抛 `INVALID_ARGUMENT`，`reason == "UNKNOWN_METHOD"` |
| `test_validation_error_reports_first_field` | 同上 | 需要整数的 `quantity` 传字符串 | `INVALID_ARGUMENT`，`data.field == "quantity"` |
| `test_server_ping_does_not_use_worker_pool` | `test_server.py` | 启动 server 后立即发送 `app.ping`，worker 执行 `sleep(2)` | `app.ping` 在 200 ms 内返回 `{ok:true}` |
| `test_server_cancel_responds_within_200_ms` | 同上 | worker 处理 `slow.method`，reader 发送 `$/cancel` | `CANCELLED` 在 200 ms 内出现；之后没有第二条同 id 响应 |
| `test_non_cancellable_method_ignores_cancel` | 同上 | 注册 `cancellable=False` 的 `paper.order.place`，发送 `$/cancel` | 无 `CANCELLED` 响应；处理器正常返回一次结果 |
| `test_server_writes_only_ndjson` | 同上 | 处理器调用 `print("noise")` | stdout 每行可 `json.loads`；不含 `noise` |
| `test_builtin_shutdown_returns_ok_before_stop` | `test_builtins.py` | `app.shutdown` | 先得到 `{"ok":true}`，随后 `stopped is True` |
### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增文件 | 请求、处理器和错误都在测试内构造 | `io.BytesIO` 与 fake handler |
| `core/tests/unit/rpc/conftest.py` | 提供 `pipe_pair()`、`wait_for_line()` 和 `SlowHandler` | 测试作者编写，不联网 |

## 9. 验收
### 9.1 命令与期望输出
```bash
cd core
uv run pytest tests/unit/rpc -q
# 期望：11 passed，0 failed
uv run ruff check sentinel/rpc tests/unit/rpc
# 期望：exit=0
```
### 9.2 完成清单
- [ ] 第 4 节每个文件都已创建
- [ ] 第 8.1 节 10 个测试全部存在且通过
- [ ] `scripts/check.sh` 全绿
- [ ] 没有修改 `owns` 之外的路径，没有新增依赖
- [ ] 已写 `docs/wp/status/C-01.md`
## 10. 给下游的交接
| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| C-02 | stdout 的 NDJSON 行、`app.ping`、`app.shutdown` | Rust 只转发非 `rs-` 响应；不要解析业务字段 |
| C-04 | `Dispatcher.register`、`RequestContext` | `app.bootstrap` 由 C-04 注册，不修改 server.py |
| P-01、P-05、P-06 | `Dispatcher.register` 和 `CancelledError` | 写事务和网络请求不得在同一个锁内 |
| C-05 | 错误码与通知字段 | 前端只读 wire JSON，不导入 Python 类型 |

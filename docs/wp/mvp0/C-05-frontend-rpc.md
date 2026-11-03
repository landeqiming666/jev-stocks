---
id: C-05
title: 前端 RpcClient、mock 与契约类型生成
phase: mvp0
platform: shared
lane: core
deps: [C-06, WP-00]
size: L
size_approval: cr/N10-01-execution-clarifications.md
owns: [apps/desktop/src/rpc/, apps/desktop/src/mocks/, scripts/gen_ts_types.py, scripts/tests/test_gen_ts_types.py]
appends: []
stubs: []
---

# C-05 前端 RpcClient、mock 与契约类型生成

## 0. 一眼看懂
- **目标**：让 React 只通过一个有类型的 `RpcClient` 调用 40 个方法、接收 7 个通知，并能在没有后端时用契约示例驱动全部页面。
- **完成后解锁**：U-00；页面开发从 mock 开始，I-01 再切真实核心进程。
- **预计规模**：TypeScript 约 360 行，生成脚本约 320 行，测试约 180 行；不新增前端依赖。

## 1. 背景与边界

### 1.1 为什么需要它
如果每个页面直接 `invoke("rpc_send")`，超时、取消、错误码和通知会各写一遍；手写接口类型又必然和 `contracts/` 漂移。C-05 把 wire 解析收口到客户端，把类型和 mock 示例从契约生成，页面只依赖方法名和类型。

### 1.2 范围内
1. `RpcClient.call`、`subscribe`、`status`，含默认超时、abort、取消和错误映射。
2. `core://message` 响应/通知解析，`core://status` 状态切换。
3. 从契约生成 `types.ts`、`methods.ts`、`mock-data.ts`。
4. `VITE_RPC=mock` 的 mock 客户端、场景选择和通知注入。
5. 组件测试和 TypeScript 类型检查所需的测试辅助函数。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 页面、路由、Zustand store | U-00 及后续页面工作包 |
| Rust `rpc_send` 与进程监督 | C-02 |
| 契约 JSON 的权威定义 | C-06 |
| 真实网络、真实 Jev、真实 DuckDB | 业务工作包 |
| 引入 axios、react-query、zod 或 UI 库 | 禁止，保持轻量 |
| 前端轮询核心进程 | 禁止；通知丢失时由页面焦点/刷新查询 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [02-技术架构.md](../../02-技术架构.md) | 6.2 Rust 与前端、6.3 前端 RpcClient、14 性能预算 | 命令、事件、超时 |
| [05-接口契约.md](../../05-接口契约.md) | 1 传输、2 消息格式、4 公共类型、5 方法清单、6 通知、11 契约目录 | 40 个方法和 7 个通知 |
| [03-界面设计规范.md](../../03-界面设计规范.md) | 6 页面状态总表、7 文案规范 | mock 场景名与错误显示 |
| [09-测试与评测.md](../../09-测试与评测.md) | 6 端到端场景、7 像素比对 | 组件测试和 mock 断言 |

## 3. 前置条件
- WP-00 已合并：React、TypeScript、Vite、Vitest 已锁定；`@tauri-apps/api` 可用。
- C-06 已合并：`contracts/index.json`、`types.schema.json`、`methods/*.json`、`notifications.json` 存在。
- C-02 已提供 `rpc_send`、`core://message`、`core://status`；本包不在浏览器外发网络请求。
- 生成脚本只使用 Python 3.9 标准库，不导入 `pydantic` 或 `jsonschema`。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `apps/desktop/src/rpc/client.ts` | 新建 | `RpcClient`、pending map、超时、abort、事件订阅 |
| `apps/desktop/src/rpc/errors.ts` | 新建 | `RpcError` 与 wire error 转换 |
| `apps/desktop/src/rpc/index.ts` | 新建 | 按 `VITE_RPC` 选择真实或 mock 客户端 |
| `apps/desktop/src/rpc/generated/types.ts` | 生成 | 公共类型的 TypeScript 版本 |
| `apps/desktop/src/rpc/generated/methods.ts` | 生成 | `MethodMap`、`MethodName`、参数/结果类型 |
| `apps/desktop/src/rpc/generated/mock-data.ts` | 生成 | 契约示例和通知的只读对象 |
| `apps/desktop/src/rpc/mock/client.ts` | 新建 | mock 调用、通知注入和延迟开关 |
| `apps/desktop/src/mocks/scenarios.ts` | 新建 | 页面状态到方法/示例名的映射 |
| `apps/desktop/src/rpc/client.test.ts` | 新建 | 客户端单元测试 |
| `apps/desktop/src/rpc/mock/client.test.ts` | 新建 | mock 测试 |
| `scripts/gen_ts_types.py` | 新建 | 契约到 TypeScript 的确定性生成器及 `--check` |

## 5. 接口规格

### 5.1 公开接口
```ts
export type MethodName = keyof MethodMap;
export type ParamsOf<M extends MethodName> = MethodMap[M]["params"];
export type ResultOf<M extends MethodName> = MethodMap[M]["result"];
export type NotificationName = keyof NotificationMap;
export type ParamsOfNotification<N extends NotificationName> = NotificationMap[N];
export class RpcError extends Error {
  code: ErrorCode; retryable: boolean; data: Record<string, unknown>;
}
export interface RpcClient {
  call<M extends MethodName>(
    method: M, params: ParamsOf<M>,
    options?: { timeoutMs?: number; signal?: AbortSignal },
  ): Promise<ResultOf<M>>;
  subscribe<N extends NotificationName>(
    name: N, handler: (params: ParamsOfNotification<N>) => void,
  ): () => void;
  status(): "starting" | "ready" | "restarting" | "failed";
  whenReady(options?: { timeoutMs?: number; signal?: AbortSignal }): Promise<void>;
  dispose(): void;
}
export function createRpcClient(options?: RpcClientOptions): RpcClient;
export function createMockRpcClient(options: { scenario?: string }): RpcClient;
```
`createRpcClient` 通过 `invoke("rpc_send", { line })` 发送紧凑 JSON，通过 `listen("core://message", ...)` 接收响应/通知，通过 `listen("core://status", ...)` 更新状态；监听建立后只读一次 `core_status`。`call` 默认使用生成的 `METHOD_TIMEOUTS`，调用方 `timeoutMs` 可覆盖：普通方法 30,000 ms、`settings.testConnection` 20,000 ms、`scan.retryBatch` 60,000 ms、`app.ping` 2,000 ms、`app.shutdown` 5,000 ms。`scan.start` 立即返回 `runId`，后续靠通知。

`whenReady` 不轮询，等待监听与快照初始化后实际进入 ready；取消、失败、dispose 或等待超时均拒绝。`dispose` 释放监听、所有 pending 和就绪等待者，重复调用安全。U-00 的握手使用两步合计 30 秒预算，不能分别等待两次 30 秒。

### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| pending | `id` | string | 是 | `r-<n>-<8 hex>` | 请求编号 |
| | `method` | MethodName | 是 | 已生成 | 用于超时 |
| | `resolve/reject` | function | 是 | — | Promise |
| | `timer` | number | 是 | 默认 30 s | 超时计时器 |
| wire error | `code` | ErrorCode | 是 | 15 个错误码 | 机器码 |
| | `message` | string | 是 | 非空中文 | 用户文案 |
| | `data.retryable` | boolean | 是 | 固定 | 是否重试 |
| mock scenario | `id` | string | 是 | 与 [03] §6 一致 | 页面状态 |
| | `examples` | map | 是 | 方法 → 示例名 | 选择返回 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `DEFAULT_TIMEOUT_MS` | `30_000` | `client.ts` | 查询默认超时 |
| `CONNECTION_TIMEOUT_MS` | `20_000` | 同上 | 连接测试 |
| `EXPORT_TIMEOUT_MS` | `60_000` | 同上 | 导出类方法 |
| `ID_PREFIX` | `"r-"` | 同上 | 前端请求 ID |
| `MOCK_ENV` | `"mock"` | `index.ts` | `VITE_RPC` 取值 |
| `GENERATED_HEADER` | `"/* Generated by scripts/gen_ts_types.py. Do not edit. */"` | 生成器 | 禁止手改 |

## 6. 实现步骤
1. **启动客户端**：注册两个事件监听，初始状态 `starting`；收到 `core://status.ready` 后为 `ready`，收到 `restarting` 或 `failed` 时拒绝所有 pending 并清空 map，错误为 `RpcError("INTERNAL", ...)`。
2. **发送**：生成 `id = "r-" + counter + "-" + randomHex(4)`；把 `{jsonrpc:"2.0",id,method,params}` 用 `JSON.stringify`（无空格）编码；先设 timer 和 pending，再调用 `invoke`；`invoke` 失败时移除 pending 并 reject `RpcError`。
3. **接收**：`JSON.parse(line)` 必须是对象；有 `id` 且 pending 存在时，`error` 走 `RpcError.fromWire`，`result` resolve；无 `id` 且 `method` 是已订阅通知时广播；未知 id 和未知通知只记录一次，不抛到页面。
4. **超时**：timer 到点时若仍 pending，先发送 `$/cancel`，删除并 reject `RpcError("TIMEOUT", "请求超时，请重试。", true)`；不要重复发送同一个请求。
   `RpcClient` 不得修改或重新生成 `params`；`paper.order.place` 的 `idempotencyKey` 由调用方（U-05）持有并在重试时复用。
5. **abort**：绑定 `signal.addEventListener("abort", ...)`；中止时直接发送 `{"jsonrpc":"2.0","method":"$/cancel","params":{"id":id}}`，删除 pending 并 reject `CANCELLED`；已完成的请求不再发送取消。
6. **通知**：`subscribe` 先注册本地 handler 再返回 unsubscribe；同一通知允许多个订阅；通知不缓存，丢失后由页面主动查询。
7. **mock**：`createMockRpcClient` 从 `mocks/scenarios.ts` 读取 `scenario` 的方法映射；每个方法取 `generated/mock-data.ts` 的第一个指定示例；未指定方法时取第一个成功示例；mock 的 `subscribe` 和 `status` 与真实客户端同形。
8. **生成类型**：`gen_ts_types.py` 读取 `types.schema.json` 和 `index.json`；按 `$defs` 顺序生成接口，按 `$ref`、`enum`、`oneOf`、`array`、`object`、`type` 递归映射；方法按 `index.json` 顺序生成 `MethodMap`，通知生成 `NotificationMap`。
9. **生成 mock-data**：从每个 `methods/*.json` 复制 `examples`，保留示例名和字段顺序；生成 `export const MOCK_EXAMPLES = {...} as const;` 和 `MOCK_NOTIFICATIONS`；`--check` 用临时文件逐字节比较，发现漂移返回 1。

## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户文案 |
|---|---|---|---|
| 核心未就绪 | 不发送，返回可重试错误 | `INTERNAL` | “核心进程尚未就绪，请稍后重试。” |
| wire error 的 code 未知 | 公共 code 归一为 INTERNAL；原值仅安全诊断，`retryable=false` | `INTERNAL` | “发生了意外错误，请重试。” |
| 请求超时 | 删除 pending，保留请求在核心侧的自然取消 | `TIMEOUT` | “请求超时，请重试。” |
| abort 已发生 | 先 reject，不发请求 | `CANCELLED` | “已取消” |
| `core://message` 不是 JSON | 忽略并记录一次 | — | 不显示 |
| mock 场景缺少方法 | 使用第一个成功示例 | — | 开发日志 WARN |
| 生成器遇到未知 schema | 退出码 2，打印路径 | — | 构建失败，不生成半成品 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `call_resolves_result_and_uses_expected_id_shape` | `client.test.ts` | fake invoke 返回 `result` | Promise 得到 result；line id 匹配 `^r-\d+-[0-9a-f]{8}$` |
| `wire_error_becomes_rpc_error` | 同上 | `error.code="INVALID_ARGUMENT"` | reject 的 `code`、`message`、`retryable` 与 wire 相同 |
| `timeout_sends_cancel_and_rejects_timeout` | 同上 | `timeoutMs=10`，无响应 | 发出 `$/cancel`；reject `TIMEOUT`，无第二个响应 |
| `restart_rejects_all_pending_calls` | 同上 | 两个 pending 后发 `core://status restarting` | 两个都 reject `INTERNAL` |
| `subscribe_receives_scan_progress` | 同上 | `core://message` 无 id 通知 | handler 收到 `{runId:"run-1",done:9,total:17}` |
| `mock_today_pending_returns_inbox_pending` | `mock/client.test.ts` | `scenario:"today.pending"` 调 `inbox.list` | `summary.pendingCount === 3` |
| `mock_settings_configured_returns_configured_email` | 同上 | `scenario:"settings.configured"` | `secContactEmail === "name@example.com"` |
| `mock_unknown_method_rejects_invalid_argument` | 同上 | 调一个不属于 MethodMap 的未知方法 | `RpcError.code === "INVALID_ARGUMENT"`；已知方法缺场景映射仍按第 6 节回退 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `apps/desktop/src/mocks/scenarios.ts` | 由 [03] §6 和 `design/prototype/js/states.js` 映射 | 逐项抄录状态名，不手改示例正文 |
| `apps/desktop/src/rpc/test-fixtures.ts` | `FakeTransport`、`fakeInvoke`、`waitFor` | 测试作者编写 |
| 无网络 fixture | 全部返回值来自 `generated/mock-data.ts` | `python3 scripts/gen_ts_types.py` 生成 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop
pnpm typecheck
pnpm lint
pnpm test -- --run src/rpc src/mocks
# 期望：8 passed，0 failed
cd ../..
python3 scripts/gen_ts_types.py --check
# 期望：generated TypeScript is up to date
```

### 9.2 完成清单
- [ ] 第 4 节每个文件已创建或生成
- [ ] 第 8.1 节 8 个测试全部存在且通过
- [ ] `generated/` 下没有任何手写业务逻辑
- [ ] `VITE_RPC` 未设置时选择真实客户端，设置为 `mock` 时选择 mock
- [ ] 没有新增 npm 依赖，没有轮询
- [ ] 已写 `docs/wp/status/C-05.md`

## 10. 给下游的交接
| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| U-00 | `RpcClient`、`MethodName`、`ParamsOf`、`ResultOf` | 页面只导入 `rpc/index.ts`，不直接 `invoke` |
| U-01–U-08 | `createMockRpcClient`、`scenarios.ts` | 组件测试用 mock，不请求核心进程 |
| I-01 | 真实 `rpc_send` 与 `core://status` | 切换环境变量即可，不改页面 |
| E2E | mock 通知注入 | 场景缺失要补 `scenarios.ts`，不能改示例数据 |

---
id: U-08
title: 全局反馈：Toast、错误边界、核心状态与离线横幅
phase: mvp0
platform: shared
lane: ui
deps: [U-02]
size: S
owns: [apps/desktop/src/components/feedback/, apps/desktop/src/lib/]
appends: []
stubs: []
---

# U-08 全局反馈：Toast、错误边界、核心状态与离线横幅

## 0. 一眼看懂

- **目标**：把“操作成功/失败、界面崩溃、核心进程重启、离线”统一成一套可预测的反馈，不让页面各自弹窗、各自吞错。
- **完成后解锁**：I-01 可以挂载 `FeedbackHost`，获得全局 Toast、错误边界与离线横幅。
- **预计规模**：约 9 个文件、代码加测试 430 行以内。

## 1. 背景与边界

### 1.1 为什么需要它
页面只应处理业务状态，不应重复实现“第 4 秒消失”“错误不自动消失”“崩溃后还能复制错误编号”。统一反馈层也能保证密钥和堆栈不进入用户界面。

### 1.2 范围内
1. `ToastHost`：右下最多 3 条，成功 4 秒、错误不自动消失。
2. `ErrorBoundary`：捕获渲染错误，显示错误编号、重试、复制详情。
3. `OfflineBanner`：监听 `navigator.onLine` 与 `Bootstrap.offline`。
4. `CoreStatusBanner`：监听 `core://status`，显示核心重启中/已恢复。
5. `lib/toast-store.ts`：队列、去重、上限。
6. `lib/errors.ts`：RPC 错误到用户文案的映射；不显示 `data.detail`。
7. `lib/online.ts`：在线状态的订阅与清理。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 页面级字段错误与提示条 | U-02～U-07 |
| 后端错误码定义 | C-00 / C-01 |
| 核心进程监督 | C-02 |
| 系统通知、托盘 | v1 |
| 遥测、崩溃上报 | 不做；隐私优先 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [03-界面设计规范.md](../../03-界面设计规范.md) | §4.1 外壳横幅、§5.8 Toast/Banner、§8 aria-live | 反馈位置与语义 |
| [05-接口契约.md](../../05-接口契约.md) | §3 错误对象、§3.2 错误码 | 错误映射 |
| [02-技术架构.md](../../02-技术架构.md) | §1 离线约束、§6.2 核心状态事件 | 离线与核心重启 |
| [09-测试与评测.md](../../09-测试与评测.md) | §5 密钥不泄露 | 反馈不得泄露敏感信息 |

## 3. 前置条件

- U-02 已交付 `PageFrame`、`app/events.ts`（`sentinel:toast` 事件）和 `#feedback-root` 挂载点。
- U-01 已交付 `Toast`、`Banner`、`Button` 组件。
- C-02 已定义 `core://status` 的事件负载；本包只消费，不修改 Rust。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `components/feedback/FeedbackHost.tsx` | 新建 | 挂载 Toast、离线、核心状态与错误边界 |
| `components/feedback/ToastViewport.tsx` | 新建 | 右下堆叠、最多 3 条、关闭按钮 |
| `components/feedback/ErrorBoundary.tsx` | 新建 | 类组件捕获渲染错误 |
| `components/feedback/OfflineBanner.tsx` | 新建 | 离线/恢复提示 |
| `components/feedback/CoreStatusBanner.tsx` | 新建 | 核心重启中/恢复 |
| `lib/toast-store.ts` | 新建 | `pushToast`、`dismissToast`、`subscribe` |
| `lib/errors.ts` | 新建 | `toUserMessage(error)`、`requestIdOf(error)` |
| `lib/online.ts` | 新建 | `useOnline()` 与事件清理 |
| `lib/report.ts` | 新建 | 生成可复制的诊断文本，脱敏 |
| `components/feedback/*.test.tsx` / `lib/*.test.ts` | 新建 | §8.1 的 8 个测试 |

## 5. 接口规格

### 5.1 公开接口
```ts
type ToastTone = "success" | "error";
interface ToastItem { id: string; tone: ToastTone; text: string; createdAt: number; }
function pushToast(input: {tone:ToastTone; text:string}): string;
function dismissToast(id: string): void;
function subscribeToasts(fn: (items: ToastItem[]) => void): () => void;
function toUserMessage(error: unknown): string;
function requestIdOf(error: unknown): string | null;
function buildDiagnostic(input: {error: unknown; appVersion: string; protocolVersion: string}): string;
function useOnline(): boolean;
function FeedbackHost(props: { children: React.ReactNode }): JSX.Element;
function ErrorBoundary(props: { children: React.ReactNode; fallback?: React.ReactNode }): JSX.Element;
```
- `pushToast` 的 `id` 用 `crypto.randomUUID()`；相同 `tone+text` 在 1 秒内重复出现时只保留一条并刷新计时。
- 成功 Toast 在 4000ms 后自动 `dismissToast`；错误 Toast 不设自动关闭。
- `toUserMessage` 优先使用 `error.data.message`（后端已本地化）；未知错误返回“发生了意外错误，请重试。”
- `buildDiagnostic` 只含错误码、requestId、应用/协议版本、时间；不得含密钥、请求体、持仓或逻辑正文。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `ToastItem.id` | string | 是 | UUID | 关闭与去重键 |
| `ToastItem.tone` | enum | 是 | success/error | `role=status/alert` |
| `ToastItem.createdAt` | number | 是 | epoch ms | 排序与去重窗口 |
| `ErrorBoundary.state.errorId` | string | 是 | 12 位大写十六进制 | 用户可复制的错误编号 |
| `CoreStatus` | enum | 是 | `starting`/`restarting`/`ready`/`failed` | 横幅文案 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MAX_TOASTS` | `3` | `toast-store.ts` | 同时显示上限 |
| `TOAST_SUCCESS_MS` | `4000` | `toast-store.ts` | 成功自动关闭 |
| `DEDUPE_WINDOW_MS` | `1000` | 同上 | 相同文案去重窗口 |
| `TOAST_Z` / `BANNER_Z` | `50` / `20` | 组件样式 | 层级 |
| `DIAGNOSTIC_MAX` | `4000` | `report.ts` | 复制文本上限 |

## 6. 实现步骤

1. `FeedbackHost` 在 `#feedback-root` 内渲染 `ToastViewport`、`OfflineBanner`、`CoreStatusBanner`，并用 `ErrorBoundary` 包裹 `children`；挂载点不存在时在 `document.body` 创建。
2. 监听 `window` 的 `sentinel:toast` 事件（`CustomEvent<{tone,text}>`），调用 `pushToast`；页面不需要直接 import 本包。
3. `toast-store` 用数组保存；超过 3 条时移除最早一条；相同 `tone+text` 在 1 秒内只更新 `createdAt`，不新增；监听者只收到副本。
4. `ToastViewport` 固定在右下 `24px`，列间距 `12px`；成功 `role="status"`，错误 `role="alert"`；每条有关闭按钮 `aria-label="关闭提示"`；`Esc` 关闭最上面一条。
5. `ErrorBoundary` 捕获 `componentDidCatch`，生成 12 位错误编号；界面显示“界面出现了一个错误。”+“错误编号：{id}”+`重试`+`复制错误详情`；不显示堆栈。
6. `复制错误详情` 调 `buildDiagnostic` 并 `navigator.clipboard.writeText`；失败时显示“复制失败，请手动记录错误编号。”；诊断文本不写 `console`。
7. `OfflineBanner` 同时参考 `navigator.onLine` 与 `Bootstrap.offline`；离线时 warn 横幅“当前离线，显示的是上次的结果。”，恢复时显示一次成功 Toast“已恢复联网”并自动消失。
8. `CoreStatusBanner` 监听 Tauri `core://status`：`restarting` 显示 warn“核心进程正在重启…”，`failed` 显示 danger“核心进程未能启动，请重试。”，`ready` 后 3 秒自动隐藏；不得阻塞页面滚动。
9. `useOnline` 在挂载时读 `navigator.onLine`，订阅 `online`/`offline`，卸载时移除监听；SSR 测试环境默认 `true`。
10. `lib/errors` 只映射 15 个错误码到一句中文；`data.detail` 永不展示，只有“复制错误详情”包含 requestId，不含 detail。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（i18n 键） |
|---|---|---|---|
| 渲染抛错 | 显示 fallback，不白屏 | `INTERNAL` | `feedback.renderError`：“界面出现了一个错误。” |
| 错误无 requestId | 生成客户端错误编号 | `INTERNAL` | `feedback.errorId` |
| 剪贴板权限拒绝 | 不发异常，显示手动提示 | — | `feedback.copyFailed` |
| 离线时点击扫描 | 页面自行处理 | `SOURCE_UNAVAILABLE` | `feedback.offline` |
| 核心重启中 | warn 横幅，页面保持 | — | `feedback.coreRestarting` |
| 核心启动失败 | danger 横幅 + 重试 | — | `feedback.coreFailed` |
| Toast 文案过长 | 最多 3 行，超出省略 | — | 不适用 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `toast_store_keeps_only_three` | `lib/toast-store.test.ts` | push 4 条不同文案 | 长度 3，最早一条被移除 |
| `toast_store_dedupes_same_text_within_one_second` | 同上 | 1 秒内 push 两次相同 | 长度 1 |
| `success_toast_dismisses_after_4000ms` | `ToastViewport.test.tsx` | 假计时器推进 4000ms | 节点消失 |
| `error_toast_does_not_auto_dismiss` | 同上 | 推进 10000ms | 节点仍在，`role=alert` |
| `error_boundary_shows_id_and_hides_stack` | `ErrorBoundary.test.tsx` | 子组件抛错 | 文本含“错误编号”，不含 `at ` 堆栈 |
| `offline_banner_reacts_to_window_event` | `OfflineBanner.test.tsx` | 触发 `offline` 事件 | 文本“当前离线” |
| `online_recovery_shows_one_toast` | `FeedbackHost.test.tsx` | offline→online | 只出现 1 条“已恢复联网” |
| `diagnostic_contains_no_secret_or_thesis` | `lib/report.test.ts` | 错误对象含 `apiKey` 与长正文 | 输出不含两者，只含 code/requestId/版本 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增 fixture | 错误对象在测试内构造 | 使用 `code:"INTERNAL"` 与假 requestId |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop && pnpm vitest run src/components/feedback src/lib
# 期望：8 passed，0 failed
cd apps/desktop && pnpm tsc --noEmit
# 期望：exit=0
```
### 9.2 完成清单
- [ ] 1280×820 与 1024×700 截图覆盖 Toast 成功/错误、离线横幅、错误边界
- [ ] Toast 最多 3 条；错误不自动消失
- [ ] 诊断文本不含密钥、逻辑、持仓、成本
- [ ] `Esc` 关闭 Toast；焦点可见；`aria-live` 正确
- [ ] 未修改 `owns` 之外文件；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| I-01 | `FeedbackHost` 挂载在 `#feedback-root` | 只挂载一次；不重复创建 portal |
| U-02～U-07 | `sentinel:toast` 事件 | 页面不直接 import Toast 组件 |
| C-02 | `core://status` 负载 | `state` 取 `starting/restarting/ready/failed` |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 多个页面重复挂载 FeedbackHost | Toast 出现两次 | 模块级单例标记；第二次挂载只返回 children |
| 错误边界吞掉开发错误 | 测试难定位 | 开发模式仍 `console.error`，但界面不显示堆栈 |
| 离线事件在 Tauri 不触发 | 横幅不出现 | 同时依赖 `Bootstrap.offline` 与服务端 `source.degraded` |

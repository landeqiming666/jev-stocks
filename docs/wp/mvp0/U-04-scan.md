---
id: U-04
title: 扫描页
phase: mvp0
platform: shared
lane: ui
deps: [U-02]
size: M
owns: [apps/desktop/src/pages/scan/]
appends: []
stubs: []
---

# U-04 扫描页

## 0. 一眼看懂

- **目标**：让用户相信系统真的在工作且成本可控：运行历史、预算条、进度、失败批次与重试全部可见。
- **完成后解锁**：I-01 可以演示“扫描 → 部分成功 → 重试失败批次”的完整路径。
- **预计规模**：约 10 个文件、代码加测试 620 行以内。

## 1. 背景与边界

### 1.1 为什么需要它
语义判定是付费且可能失败的操作。用户需要看到“扫了多少、花了多少、哪一批失败、为什么失败”，否则不会信任它每天运行。

### 1.2 范围内
1. `scan.history` 运行列表、预算条、空状态。
2. 运行状态标签：成功、部分成功、失败、已取消、已中断、进行中。
3. `scan.detail` 明细抽屉与批次列表。
4. `scan.retryBatch` 单批重试。
5. `scan.start`、`scan.cancel` 与 `scan.progress`/`scan.finished` 通知。
6. 键盘：行打开明细、抽屉关闭、重试按钮。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 扫描调度、批次拆分、水位线 | P-02 |
| Jev 调用与判定 | S-03～S-05 |
| 今日清单的卡片展示 | U-02 |
| 自动重试策略 | P-02；本页只提供手动重试 |
| 定时扫描设置 | v1 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [03-界面设计规范.md](../../03-界面设计规范.md) | §4.7 扫描、§5.7 表格、§5.8 抽屉、§6 状态表 | 布局与状态 |
| [05-接口契约.md](../../05-接口契约.md) | §5.6 扫描、§6 通知、§7.1–§7.2 状态机 | 字段与状态 |
| [09-测试与评测.md](../../09-测试与评测.md) | §6 E2E-06、§7 像素比对 | 交互验收 |

## 3. 前置条件

- U-02 已交付 `useScanControl` 的事件名、`PageFrame` 用法和错误 Toast 事件。
- U-01 已交付 `Table`、`Progress`、`Drawer`、`Banner`、`StatusTag`、`EmptyState`、`Button`。
- C-05 的 mock 支持 `scan.*` 示例；`scan.progress` 可注入。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `pages/scan/index.tsx` | 新建 | 页面入口、初始加载、通知订阅 |
| `pages/scan/ScanHeader.tsx` | 新建 | 标题、立即扫描/取消、上次扫描时间 |
| `pages/scan/BudgetBar.tsx` | 新建 | token 用量、估算费用、重置时间、80%/100% 状态 |
| `pages/scan/RunTable.tsx` | 新建 | 运行历史表与行展开 |
| `pages/scan/RunRow.tsx` | 新建 | 单次运行的统计与状态 |
| `pages/scan/RunDetailDrawer.tsx` | 新建 | 窗口、统计、批次列表、重试 |
| `pages/scan/BatchRow.tsx` | 新建 | 批次状态、尝试次数、错误与重试 |
| `pages/scan/useScanRuns.ts` | 新建 | 历史、明细、刷新、开始/取消 |
| `pages/scan/format.ts` | 新建 | 运行时长、token、费用、状态文案 |
| `pages/scan/*.test.tsx` | 新建 | §8.1 的 10 个测试 |

## 5. 接口规格

### 5.1 公开接口
```ts
function ScanPage(): JSX.Element;
function BudgetBar(props: { usedTokens:number; limitTokens:number; estCostUsd:string; resetAt:string }): JSX.Element;
function RunTable(props: {
  items: ScanRun[]; loading: boolean;
  onOpen: (runId:string) => void;
}): JSX.Element;
function RunDetailDrawer(props: {
  runId: string | null; overlay: boolean; onClose: () => void;
  onRetryBatch: (batchId:string) => Promise<void>;
}): JSX.Element | null;
function useScanRuns(client: RpcClient): {
  runs: ScanRun[]; budget: Budget | null; loading: boolean; error: RpcError | null;
  refresh: () => Promise<void>; start: () => Promise<void>; cancel: (runId:string) => Promise<void>;
  detail: (runId:string) => Promise<{run:ScanRun;batches:ScanBatch[]}>;
};
```
- `start` 成功后不等待运行结束，立即刷新历史；重复点击在 `running` 时禁用。
- `cancel` 只对 `running` 运行可用；成功后按钮恢复“立即扫描”，列表保留该运行。
- `onRetryBatch` 同步返回后刷新明细与运行统计；失败时批次保持 `failed` 并显示服务端文案。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `ScanRun.status` | enum | 是 | 7 个取值 | 运行状态与标签映射 |
| `ScanRun.stats` | object | 是 | 所有计数 ≥0 | 表格统计列 |
| `ScanBatch.status` | enum | 是 | `pending`/`succeeded`/`failed`/`cancelled` | 批次标签 |
| `ScanRun.batchSummary` | object | 是 | 四个整数 | 明细摘要 |
| `ScanRun.error` | object \| null | 是 | code + message | 失败原因 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `BUDGET_WARN` / `BUDGET_DANGER` | `80` / `100` | `BudgetBar.tsx` | 进度条阈值 |
| `HISTORY_LIMIT` | `50` | `useScanRuns.ts` | 首次请求条数 |
| `DETAIL_WIDTH` | `400` | `RunDetailDrawer.tsx` | 明细抽屉宽度 |
| `RETRY_TIMEOUT_MS` | `60000` | `useScanRuns.ts` | 单批重试前端超时 |
| `PROGRESS_THROTTLE_MS` | `500` | `useScanRuns.ts` | 进度通知最小间隔 |

## 6. 实现步骤

1. 挂载时并行调用 `scan.history({limit:50})`；加载中显示 4 行骨架。没有记录时显示“还没有扫描记录”+“立即扫描”，不显示空表头。
2. 页头显示“扫描”；右侧按钮在无运行时为“立即扫描”，运行时为“取消”。无配置时按钮禁用，`title` 写“请先完成设置”。
3. 预算条文本固定格式：`今日已用 18,420 / 2,000,000 tokens · 估算 $0.0008 · 重置于 明天 08:00`；进度用 `--ink-2`，≥80% `--warn`，100% `--danger` 并显示“预算已用完”。
4. 历史表列：开始时间、状态、标的数、披露数、段落数、判定数、请求数、tokens、估算费用、耗时、引擎。数值列右对齐等宽；状态用 `StatusTag`；行支持点击、`Enter` 或 `Space` 打开明细，并同步 `aria-expanded`。
5. 状态映射：`succeeded`→成功/ok，`partial`→部分成功/warn，`failed`→失败/danger，`cancelled`→已取消/none，`interrupted`→已中断/none，`running`→进行中/info，`queued`→排队中/info。
6. 运行中行显示进度条，进度来自 `scan.progress` 的 `done/total` 与 `message`；通知间隔小于 500ms 时只保留最后一条。收到 `scan.finished` 后刷新历史并把运行状态改为终态。
7. 明细抽屉宽 400px；显示窗口范围、统计、引擎、失败原因；批次列表每行显示“标的 + 披露标题”、状态、尝试次数、tokens。失败批次显示错误码与文案，并提供“重试”。
8. 重试点击后按钮进入 `is-loading`（文字不变），成功刷新明细与列表并发出成功 Toast“已重试成功”；失败保留批次并显示错误，不得把 `failed` 改成 `succeeded`。
9. 空预算状态：`budget` 示例显示进度 100%、`Banner` “今日预算已用完，明天 08:00 重置。”、扫描按钮禁用；历史仍可查看。
10. 抽屉打开后焦点进入标题；`Esc` 关闭并还焦点到行。行的 `aria-expanded` 与实际抽屉同步；1024 宽时抽屉覆盖内容并启用焦点陷阱。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（i18n 键） |
|---|---|---|---|
| 历史加载失败 | 全页错误 + 重试 | `SOURCE_UNAVAILABLE`/`INTERNAL` | `scan.loadFailed`：“扫描记录加载失败。” |
| 已有运行 | 按钮禁用 + 提示 | `CONFLICT` | `scan.runningConflict`：“扫描正在进行。” |
| 预算耗尽 | 禁用开始，保留历史 | `BUDGET_EXCEEDED` | `scan.budgetExhausted` |
| 重试时密钥失效 | 保留失败批次 | `UNAUTHENTICATED` | `scan.authFailed`：“Jev 密钥无效，请去设置。” |
| 重试超过 60 秒 | 停止等待，刷新明细 | `TIMEOUT` | `scan.retryTimeout` |
| 明细运行不存在 | 抽屉显示错误与关闭 | `NOT_FOUND` | `scan.runNotFound` |
| 批次列表为空 | 显示“没有批次记录” | — | `scan.noBatches` |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `scan_history_renders_four_runs` | `ScanPage.test.tsx` | `scan.history/default` | 4 行；状态含“成功”“部分成功”“已取消” |
| `scan_empty_shows_start_action` | 同上 | `scan.history/empty` | 文本“还没有扫描记录”，一个主按钮 |
| `budget_bar_turns_warn_at_80_percent` | `BudgetBar.test.tsx` | 1,600,000 / 2,000,000 | 进度元素含 `is-warn` |
| `budget_bar_turns_danger_at_limit` | 同上 | 2,000,000 / 2,000,000 | 文本“预算已用完”，`is-danger` |
| `running_row_shows_done_total` | `ScanPage.test.tsx` | `scan.history/running` + `scan.progress` 9/17 | 文本含“9 / 17” |
| `start_disabled_when_running` | 同上 | 一个 running | 按钮 disabled，`title` 含“扫描正在进行” |
| `detail_renders_failed_batch_reason` | `RunDetailDrawer.test.tsx` | `scan.detail/with_failures` | 文本含“529”与“已重试 3 次” |
| `retry_batch_calls_rpc_once` | 同上 | 点击“重试” | `scan.retryBatch` 调用 1 次，参数为 `batchId` |
| `retry_failure_keeps_failed_status` | 同上 | 重试抛 `MODEL_ERROR` | 批次仍为“失败”，出现错误 |
| `cancel_sends_run_id` | `ScanPage.test.tsx` | running 点取消 | `scan.cancel` 参数为当前 `runId` |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `pages/scan/__fixtures__/history.json` | `scan.history/default` | 从契约复制 |
| `pages/scan/__fixtures__/detail.json` | `scan.detail/with_failures` | 从契约复制 |
| `pages/scan/__fixtures__/budget.json` | `scan.history/budget_exhausted` | 从契约复制 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop && pnpm vitest run src/pages/scan
# 期望：10 passed，0 failed
cd apps/desktop && pnpm tsc --noEmit
# 期望：exit=0
```
### 9.2 完成清单
- [ ] 1280×820 与 1024×700 截图覆盖 `default`、`detail`、`budget`
- [ ] 表格窄窗口内部滚动；数值列不换行
- [ ] 预算 80%/100% 同时有颜色和文字，不只用颜色
- [ ] 抽屉焦点与 `Esc` 行为通过键盘测试
- [ ] 未修改 `owns` 之外文件；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| U-02 | `scan.progress`/`scan.finished` 的刷新约定 | 两页可同时订阅，通知不是唯一数据源 |
| I-01 | 运行状态标签与错误文案 | 不新增枚举；只映射契约值 |
| E-02 | token 与费用展示 | 费用使用接口的 `estCostUsd`，前端不重算 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 通知过密导致重渲染 | 扫描中页面卡顿 | 500ms 合并；只保留最后一条 |
| 重试后统计不一致 | 列表与明细数字不同 | 重试成功后重新拉取 `scan.detail`，不用本地加减 |
| 费用显示精度差异 | 与后端不一致 | 直接显示 `Decimal` 字符串的前 4 位，不转浮点 |

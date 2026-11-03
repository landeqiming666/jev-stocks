---
id: U-02
title: 今日页与证据抽屉
phase: mvp0
platform: shared
lane: ui
deps: [U-01]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [apps/desktop/src/pages/today/, apps/desktop/src/components/evidence/, apps/desktop/src/i18n/zh-CN/today.ts]
appends: []
stubs: []
---

# U-02 今日页与证据抽屉

## 0. 一眼看懂

- **目标**：实现“30 秒内知道今天有没有需要处理的事”：待处理清单、三种折叠组、九种页面状态、六种证据抽屉状态。
- **完成后解锁**：U-03～U-08 可以复用今日页的刷新、处理和抽屉模式。
- **预计规模**：约 14 个文件、代码加测试 760 行以内。

## 1. 背景与边界

### 1.1 为什么需要它
今日页是产品的核心界面。它必须同时做到：结论先于证据、空状态明确、失败不被伪装成成功、用户处理完条目后立即移出清单。

### 1.2 范围内
1. `inbox.list` 的加载、刷新、排序、分组与空/错/离线/未配置状态。
2. 判定卡片、折叠的“系统拿不准的 K 条”和“已处理（N）”。
3. `decision.get` 驱动的证据抽屉，及 `decision.act`、`decision.reopen`。
4. `scan.start` 与 `scan.cancel` 的页头按钮，接收 `scan.progress`/`scan.finished`/`inbox.updated`。
5. 键盘：卡片操作、抽屉焦点、`Esc` 关闭、处理后的焦点落点。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 扫描运行历史与批次明细 | U-04 |
| 编辑投资逻辑 | U-03 |
| 全局 Toast 队列、离线横幅 | U-08；本页只发 `sentinel:toast` 事件 |
| 定时扫描、系统通知 | v1 |
| 新的卡片或抽屉样式 | U-01；本页只用组件库 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [03-界面设计规范.md](../../03-界面设计规范.md) | §4.2 今日、§4.3 证据抽屉、§5.6 卡片、§6 状态总表、§7 文案 | 布局、状态与文案 |
| [05-接口契约.md](../../05-接口契约.md) | §4 `Inbox`/`DecisionSummary`/`Evidence`；§5.5 清单与判定；§6 通知 | 数据字段与动作 |
| [01-产品需求.md](../../01-产品需求.md) | §7 US-05～US-07 | 验收行为 |
| [09-测试与评测.md](../../09-测试与评测.md) | §6 E2E-05～E2E-09、§7 像素比对 | 端到端与截图 |

## 3. 前置条件

- U-01 已交付 `Card`、`VerdictChip`、`Probability`、`Drawer`、`Banner`、`EmptyState`、`Skeleton`、`Button`。
- U-00 已交付 `PageFrame`、`navigate`、`useEscape`、`app/format.ts`、`app/events.ts`。
- C-05 的 mock 可按 `contracts/methods/inbox.list.json` 的示例名返回；不得自行造示例。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `pages/today/index.tsx` | 新建 | 页面入口；状态选择与 `PageFrame` |
| `pages/today/TodayHeader.tsx` | 新建 | 日期、市场状态、上次扫描、扫描/取消按钮 |
| `pages/today/DecisionCard.tsx` | 新建 | 单条判定卡片与四个操作 |
| `pages/today/DecisionGroups.tsx` | 新建 | 待处理、待确认、已处理三个折叠组 |
| `pages/today/useInbox.ts` | 新建 | 拉取、通知刷新、乐观处理与回滚 |
| `pages/today/useScanControl.ts` / `state.ts` | 新建 | 扫描开始/取消、进度、冲突处理与页面状态纯函数 |
| `components/evidence/EvidenceDrawer.tsx` | 新建 | 六种抽屉状态与底部操作区 |
| `components/evidence/ProbabilityBars.tsx` | 新建 | 五个概率条与“未设置失效条件” |
| `components/evidence/EvidenceText.tsx` | 新建 | 段落、证据句高亮、标题/整段说明 |
| `pages/today/*.test.tsx` / `components/evidence/*.test.tsx` | 新建 | §8.1 的 12 个测试 |

## 5. 接口规格

### 5.1 公开接口
```ts
function TodayPage(): JSX.Element;
function DecisionCard(props: {
  item: DecisionSummary;
  onOpen: (decisionId: string) => void;
  onAct: (decisionId: string, action: ActionType, note?: string) => void;
}): JSX.Element;
function EvidenceDrawer(props: {
  decisionId: string | null;
  overlay: boolean;
  onClose: () => void;
  onAct: (action: ActionType, note: string | null) => Promise<void>;
  onReopen: () => Promise<void>;
}): JSX.Element | null;
function useInbox(client: RpcClient): {
  state: "loading"|"ready"|"error"; inbox: Inbox | null;
  error: RpcError | null; refresh: () => Promise<void>;
  act: (id: string, action: ActionType, note?: string) => Promise<void>;
  reopen: (id: string) => Promise<void>;
};
function useScanControl(client: RpcClient): { start(): Promise<void>; cancel(): Promise<void>; progress: {done:number;total:number;message:string} | null };
function deriveTodayState(inbox: Inbox | null, boot: Bootstrap): TodayState;
```
- `act` 成功时把条目从 `items`/`uncertain` 移到 `processed` 首位；失败时恢复原对象并发出错误 Toast。
- `onAct` 的备注去首尾空白后 ≤200 个 Unicode 码点；空串存 `null`。
- `deriveTodayState` 的优先级：`no_holdings` > `unconfigured` > `scan_failed` > `offline` > `scanning` > `empty` > `pending`。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `Inbox.items` | `DecisionSummary[]` | 是 | 只含推翻、削弱 | 主清单 |
| `Inbox.uncertain` | `DecisionSummary[]` | 是 | 不含已处理 | 折叠组，不计入 N |
| `DecisionSummary.headline` | number | 是 | 0..1 | 卡片概率，两位小数 |
| `DecisionSummary.contentStatus` | enum | 是 | `full_text`/`title_only` | 仅标题标注 |
| `Evidence.kind` | enum | 是 | `sentence`/`passage`/`title` | 高亮方式 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `VISIBLE_CARDS` | `5` | `state.ts` | 前 5 条展开，其余折叠 |
| `PROCESSED_DAYS` | `30` | `state.ts` | 已处理组回看天数 |
| `NOTE_MAX` | `200` | `EvidenceDrawer.tsx` | 备注上限 |
| `DRAWER_PUSH_BP` | `1200` | `index.tsx` | 推/覆盖切换宽度 |
| `PROGRESS_MIN_MS` | `500` | `useScanControl.ts` | 进度刷新节流 |
| `TOAST_ERROR` | `sentinel:toast` | `app/events.ts` | 错误事件名 |

## 6. 实现步骤

1. 挂载时调用 `inbox.list`；加载中显示 3 张无动画骨架卡。页面获得焦点或用户点“刷新”时重新调用，禁止定时轮询。
2. 订阅 `inbox.updated`：收到后调用 `inbox.list`，不直接拼接通知里的计数；订阅 `scan.progress` 更新页头进度，`scan.finished` 后刷新清单与“上次扫描”。
3. 标题规则：`items.length` 为 N 时显示“今天有 N 件事需要你看一眼”；N=0 且无待确认时显示“今天没有需要处理的变化”，并写“已检查 X 只标的、Y 份披露、Z 个段落，上次扫描 …”。
4. 排序：先按关系 `overturn` 在 `weaken` 前，再按 `headline` 降序，再按 `createdAt` 降序。前 5 条渲染完整卡片，其余用“其余 M 条”按钮展开。
5. 卡片必须包含：市场徽标、代码/名称、判定标签、两位小数概率、“你写过：”单行摘要、“证据：”两行摘要、`8-K · 时间 · 标题`、四个操作。`thesisCurrentVersion > thesisVersion` 时在标题行加“逻辑已更新”。
6. 操作：`查看原文` 打开抽屉并记录触发元素；`仍然成立` 直接 `act("still_valid")`；`修正逻辑` 先 `navigate("holdings",{thesis:item.thesisId})`；`⋯` 菜单含 `准备卖出`、`忽略`。处理成功后焦点移到下一条卡片标题。
7. `scan_failed`：清单保留上次成功结果；顶部 danger 提示条显示 `lastScan.error.message`，按钮“重试”调用 `scan.start`；页头写“上次扫描失败 {时间}”，状态栏的“最近扫描”仍取最近成功。
8. `scanning`：页头按钮变“取消”，下方进度条与“正在判定 {标的} · {done} / {total}”；清单保持可操作，收到 `inbox.updated` 时增量刷新。
9. 证据抽屉宽 400px；打开后聚焦 `<h2 id>`，`Esc` 关闭并还焦点。内容顺序固定：标题/概率/关闭、披露信息与外链、原文段落、判定时逻辑与失效条件、五个概率、来源信息、底部操作。外链只允许 `https://www.sec.gov`，点击前显示域名。
10. `EvidenceText`：`kind=sentence` 用 `sentenceStart/sentenceEnd` 切分并 `<mark class="c-evidence-mark">` 高亮；`passage` 显示整段并说明“未能定位到单句”；`title` 只显示标题并说明“仅依据标题判定”。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（i18n 键） |
|---|---|---|---|
| `inbox.list` 失败且无缓存 | 全页错误状态 + 重试 | `SOURCE_UNAVAILABLE`/`INTERNAL` | `today.loadFailed`：“清单加载失败，请重试。” |
| 核心进程未配置 | 禁用扫描并引导设置 | `CONFIG_REQUIRED` | `today.configRequired`：“请先填写 Jev 密钥和 SEC 联系邮箱。” |
| 扫描已在进行 | 按钮禁用，提示“扫描正在进行” | `CONFLICT` | `today.scanConflict` |
| 处理请求失败 | 条目保持原状，恢复焦点 | `NOT_FOUND`/`INTERNAL` | `today.actionFailed` |
| 抽屉判定已被删除 | 显示“没有找到这条判定”，只有关闭按钮 | `NOT_FOUND` | `today.decisionNotFound` |
| 外链不是 https 或不是 sec.gov | 不打开，显示错误 Toast | `INVALID_ARGUMENT` | `today.linkBlocked` |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `today_pending_renders_three_cards_in_required_order` | `pages/today/TodayPage.test.tsx` | `inbox.list/pending` | 3 张卡；前两张“推翻”，第三张“削弱” |
| `today_empty_states_checked_counts` | 同上 | `inbox.list/empty` | 大字“今天没有需要处理的变化”，含“4 只标的” |
| `today_uncertain_not_counted_in_n` | 同上 | pending + 2 uncertain | 标题 N=3；折叠标签“系统拿不准的 2 条” |
| `today_scan_failed_keeps_last_items` | 同上 | `scan_failed` | 3 张卡仍在，danger 提示条含失败原因 |
| `today_title_only_marks_evidence` | 同上 | `contentStatus=title_only` | 证据行前缀“仅依据标题” |
| `today_act_moves_item_to_processed` | 同上 | 点击“仍然成立” | 卡片移入“已处理（1）”，调用一次 `decision.act` |
| `today_act_failure_restores_item` | 同上 | mock 返回 `INTERNAL` | 卡片仍在待处理，出现错误 Toast 事件 |
| `drawer_esc_closes_and_restores_focus` | `components/evidence/EvidenceDrawer.test.tsx` | 打开后按 Esc | `onClose` 调用；触发按钮聚焦 |
| `drawer_renders_five_probability_bars` | 同上 | `decision.get/overturn` | 5 行；`killMet=null` 行写“未设置失效条件” |
| `drawer_sentence_highlights_offsets` | 同上 | `kind=sentence`, start=4,end=12 | 一个 `mark.c-evidence-mark`，文本长度为 8 |
| `drawer_processed_shows_reopen_only` | 同上 | `decision.get/processed` | 无“仍然成立”，有“重新打开” |
| `scan_control_sends_cancel_when_running` | `pages/today/useScanControl.test.ts` | `scanning` 状态点取消 | 调用 `scan.cancel`，参数为当前 `runId` |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `pages/today/__fixtures__/inbox.json` | `inbox.list` 的 `pending` 示例 | 从 `contracts/methods/inbox.list.json` 复制 |
| `pages/today/__fixtures__/decision-overturn.json` | `decision.get/overturn` | 从契约复制；证据句子偏移不得改 |
| `pages/today/__fixtures__/decision-title-only.json` | `decision.get/title_only` | 从契约复制 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop && pnpm vitest run src/pages/today src/components/evidence
# 期望：12 passed，0 failed
cd apps/desktop && pnpm tsc --noEmit
# 期望：exit=0
```
### 9.2 完成清单
- [ ] 九种页面状态与六种抽屉状态都能通过 hash 参数复现
- [ ] 1280×820 与 1024×700 截图覆盖 `pending`、`empty`、`scan_failed`、`drawer=overturn`
- [ ] 像素比对 `maxDiffPixelRatio=0.01` 通过；动态状态不纳入
- [ ] 键盘：Tab 顺序、`Esc`、处理后焦点、抽屉焦点归还全部通过
- [ ] 未修改 `owns` 之外文件；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| U-03 | `navigate("holdings",{thesis})`、处理后的焦点规则 | 修正逻辑只跳转，不自动保存 |
| U-04 / U-08 | `useScanControl` 的进度事件与 `sentinel:toast` | 扫描页不得重复订阅；页面不直接渲染 Toast |
| I-01 | 页面状态 hash 参数 | `state` 与抽屉参数不得改名 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 通知丢失导致清单过期 | 新条目未出现 | 页面获得焦点时强制 `inbox.list`；不依赖通知正确性 |
| 证据偏移与服务端文本不一致 | 高亮错位 | 校验 `sentenceEnd <= passageText.length`；否则退回整段显示并标注 |

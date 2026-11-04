---
id: U-03
title: 持仓页与逻辑编辑器
phase: mvp0
platform: shared
lane: ui
deps: [U-02]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [apps/desktop/src/pages/holdings/, apps/desktop/src/i18n/zh-CN/holdings.ts]
appends: []
stubs: []
---

# U-03 持仓页与逻辑编辑器

## 0. 一眼看懂

- **目标**：在一屏内完成“添加标的、登记持仓、写/改/归档投资逻辑、刷新行情”，并让没有逻辑的持仓显眼地处于“未守护”状态。
- **完成后解锁**：U-02 的“修正逻辑”跳转可以落地；I-01 可以演示完整主流程。
- **预计规模**：约 12 个文件、代码加测试 780 行以内。

## 1. 背景与边界

### 1.1 为什么需要它
投资逻辑是产品的输入。用户如果不能在 2 分钟内写完第一条逻辑，后面的扫描、清单和证据都没有意义。持仓页还必须把“持仓”和“只关注”区分清楚。

### 1.2 范围内
1. 持仓表：标的、持仓、成本、最近收盘、日涨跌、市值、逻辑数、状态。
2. 添加标的：300ms 防抖搜索、已添加标记、无结果提示、内联数量/成本/备注表单。
3. 行内逻辑区：逻辑卡、版本、最近判定、编辑、版本历史、归档。
4. 逻辑编辑器：500/300 计数、空值/超长/上限/冲突错误。
5. 行情刷新与离线 Toast。
6. 键盘与焦点：行展开、编辑器保存/取消、删除确认。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 标的表下载、搜索索引 | D-02 |
| 持仓与逻辑的数据库写入 | P-01 |
| 行情抓取 | D-04 |
| CSV 导入、真实券商同步 | v1 / 永远不做 |
| 判定清单与证据抽屉 | U-02 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [03-界面设计规范.md](../../03-界面设计规范.md) | §4.4 持仓、§5.1–§5.4、§7 文案 | 表格、编辑器、计数规则 |
| [05-接口契约.md](../../05-接口契约.md) | §5.3 标的与持仓、§5.4 投资逻辑 | 参数、错误与乐观锁 |
| [01-产品需求.md](../../01-产品需求.md) | §7 US-01～US-04 | 用户故事验收 |
| [04-数据模型.md](../../04-数据模型.md) | §3 持仓与逻辑、§8.1 清单规则 | 版本与状态含义 |

## 3. 前置条件

- U-02 已交付 `PageFrame` 用法、处理后的跳转参数 `?thesis=<id>` 和全局错误事件。
- U-01 已交付 `Table`、`SearchInput`、`Field`、`Menu`、`Modal`、`Banner`、`EmptyState`。
- C-05 的 mock 支持 `holdings.*`、`instruments.search`、`prices.refresh`、`thesis.*` 的契约示例。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `pages/holdings/index.tsx` | 新建 | 页面入口、加载、跳转参数、刷新 |
| `pages/holdings/HoldingsToolbar.tsx` | 新建 | 搜索添加、刷新行情、行情截至时间 |
| `pages/holdings/HoldingsTable.tsx` | 新建 | 表头、行、展开区、空状态 |
| `pages/holdings/HoldingRow.tsx` | 新建 | 单行展示、行内编辑数量/成本/备注 |
| `pages/holdings/AddInstrument.tsx` | 新建 | 防抖搜索、结果下拉、添加表单 |
| `pages/holdings/ThesisList.tsx` | 新建 | 逻辑卡、模板、添加入口、上限提示 |
| `pages/holdings/ThesisEditor.tsx` | 新建 | 500/300 编辑器、保存/取消、冲突条 |
| `pages/holdings/VersionHistory.tsx` | 新建 | 只读版本列表 |
| `pages/holdings/useHoldings.ts` | 新建 | `holdings.list/upsert/archive` 与刷新 |
| `pages/holdings/useTheses.ts` | 新建 | `thesis.list/create/update/archive/versions` |
| `pages/holdings/validation.ts` | 新建 | 数量、成本、备注、逻辑长度的纯函数 |
| `pages/holdings/*.test.tsx` | 新建 | §8.1 的 13 个测试 |

## 5. 接口规格

### 5.1 公开接口
```ts
function HoldingsPage(): JSX.Element;
type HoldingInput = {instrumentId:string;quantity:string;avgCost?:string|null;note?:string|null}; type ThesisInput = {instrumentId:string;statement:string;killCondition?:string|null}; type ThesisUpdate = {thesisId:string;statement:string;killCondition?:string|null;expectedVersion:number};
function HoldingsTable(props: {
  items: Holding[]; expandedId: string | null;
  onToggle: (instrumentId: string) => void;
  onEditHolding: (h: Holding) => void;
  onArchive: (instrumentId: string) => Promise<void>;
}): JSX.Element;
function ThesisEditor(props: {
  instrumentId: string; initial?: Thesis | null;
  onSaved: (t: Thesis) => void; onCancel: () => void;
}): JSX.Element;
function validateThesis(statement: string, killCondition: string): {
  ok: boolean; statement?: string; killCondition?: string;
  field?: "statement"|"killCondition"; code?: "EMPTY"|"TOO_LONG";
};
function useHoldings(client: RpcClient): {
  items: Holding[]; loading: boolean; error: RpcError | null;
  refresh: () => Promise<void>; upsert: (input: HoldingInput) => Promise<void>;
  archive: (instrumentId: string) => Promise<void>;
};
```
- `validateThesis` 去首尾空白后按 Unicode 码点计数；`statement` 为空或 >500 返回 `code`，`killCondition` >300 同理；`killCondition` 空串规范化为 `null`。
- `onSaved` 只在 `thesis.create/update` 成功后调用；冲突时不关闭编辑器。
function useTheses(client: RpcClient): { items: Thesis[]; create(input: ThesisInput): Promise<Thesis>; update(input: ThesisUpdate): Promise<Thesis>; archive(id: string): Promise<void>; versions(id: string): Promise<ThesisVersionItem[]> };

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `Holding.quantity` | Decimal string | 是 | ≥0，4 位小数 | 0 表示只关注 |
| `Holding.avgCost` | Decimal string \| null | 是 | ≥0，4 位小数 | 未填为 null |
| `Holding.status` | enum | 是 | `guarded`/`attention`/`unguarded` | 表尾状态标签 |
| `Thesis.statement` | string | 是 | 1..500 码点 | 逻辑正文 |
| `Thesis.killCondition` | string \| null | 是 | ≤300 码点 | 失效条件 |
| `Thesis.expectedVersion` | number | 是 | ≥1 | 乐观锁 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `SEARCH_DEBOUNCE_MS` | `300` | `AddInstrument.tsx` | 输入到请求的等待 |
| `SEARCH_LIMIT` | `10` | 同上 | 下拉最多结果数 |
| `STATEMENT_MAX` / `KILL_MAX` | `500` / `300` | `validation.ts` | 字数上限 |
| `MAX_THESES` | `5` | `ThesisList.tsx` | 每标的有效逻辑上限 |
| `NOTE_MAX` | `200` | `validation.ts` | 持仓备注上限 |

## 6. 实现步骤

1. 挂载 `holdings.list`；加载中显示 6 行骨架（固定高度 44）；空列表显示“先添加第一只标的”+“去添加”按钮，不显示空表头。
2. `HoldingsToolbar` 的搜索框输入变化后 300ms 调 `instruments.search`，请求参数 `{query,limit:10}`；只保留最后一次请求结果（用递增序号丢弃过期响应）。结果项显示代码、英文名、交易所、中文名；已添加项标“已添加”且不可再次选择。
3. 选中标的后展开内联表单：数量（默认 `0`）、成本（可空）、备注（可空）。提交前校验：数量是十进制且 ≥0；成本为空或 ≥0；备注 ≤200。成功后关闭表单、刷新表格并把新行滚动到可见处。
4. 表格数值列右对齐、等宽；日涨跌带 `+/-` 与 `%`；颜色只用 `--up`/`--down`（A/HK 红涨绿跌，美股绿涨红跌由 `data-market` 切换）；数量 0 在持仓列显示“关注”。状态标签：`guarded`→“守护中”，`attention`→“有待处理”，`unguarded`→“没有逻辑”。
5. 行点击或 `Enter`/`Space` 展开；展开后 `aria-expanded=true`。展开区先显示逻辑卡，末尾显示 `+ 添加逻辑`；达到 5 条时按钮禁用并写“最多 5 条有效逻辑”。没有逻辑时显示“没有逻辑的持仓不会被守护”+ 3 个模板按钮，点击只填入编辑器，不自动保存。
6. 逻辑卡显示正文、失效条件、`第 N 版 · 创建于 …`、最近判定标签；操作 `编辑`、`版本历史`、`归档`。归档弹 `Modal`，确认文案“归档后不再扫描，历史判定会保留”。
7. `ThesisEditor` 用 3 行 textarea 与单行 input；计数用去首尾空白后的码点数。超限时计数 `--danger`、输入 `aria-invalid`、字段下写具体错误；保存中禁用按钮并 `aria-busy`。
8. `Cmd/Ctrl+Enter` 保存，`Esc` 取消；有未保存内容时先弹确认。保存 `thesis.update` 传 `expectedVersion`；收到 `CONFLICT` 时在编辑器上方显示 warn 条“这条逻辑已被修改，请刷新后再试”+“刷新”，不覆盖用户输入。
10. `刷新行情` 调 `prices.refresh`；部分失败保留已更新时间并逐项标出；全部失败发 `sentinel:toast` 错误“行情源暂时无法访问，已使用 {日期} 的收盘价。”

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（i18n 键） |
|---|---|---|---|
| 标的表未加载 | 下拉提示先填邮箱 | `CONFIG_REQUIRED` | `holdings.needEmail`：“填写联系邮箱后才能下载标的表” |
| 数量为负/非数字 | 字段红边 + 说明 | `INVALID_ARGUMENT` | `holdings.invalidQuantity`：“数量必须是非负数字” |
| 逻辑为空/超长 | 字段错误，不提交 | `INVALID_ARGUMENT` | `holdings.thesisEmpty` / `holdings.thesisTooLong` |
| 已有 5 条 | 禁用添加入口 | `INVALID_ARGUMENT` | `holdings.thesisLimit`：“每只标的最多 5 条有效逻辑” |
| 编辑冲突 | 保留输入，显示刷新条 | `CONFLICT` | `holdings.thesisConflict` |
| 归档失败 | 行保持可见，Toast 报错 | `INTERNAL` | `holdings.archiveFailed` |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `holdings_renders_six_rows_and_status_labels` | `HoldingsPage.test.tsx` | `holdings.list/default` | 6 行；状态文本含“守护中”“有待处理”“没有逻辑” |
| `holdings_zero_quantity_shows_watch_only` | 同上 | 数量 `0.0000` | 持仓列文本“关注” |
| `search_debounces_and_drops_stale_response` | `AddInstrument.test.tsx` | 连续输入 `z`、`ze` | 只发 1 次请求（300ms 后），结果 3 条 |
| `add_form_rejects_negative_quantity` | 同上 | `-5` | 错误“数量必须是非负数字”，不发 `holdings.upsert` |
| `thesis_count_trims_whitespace` | `ThesisEditor.test.tsx` | `"   "` | `0 / 500`；保存显示“逻辑内容不能为空” |
| `thesis_501_chars_marks_overflow` | 同上 | 501 个中文字符 | 计数 `501 / 500`，输入 `aria-invalid=true` |
| `thesis_save_sends_expected_version` | 同上 | 当前版本 2 | `thesis.update` 参数含 `expectedVersion:2` |
| `thesis_conflict_keeps_editor_open` | 同上 | `thesis.update/conflict` | 编辑器仍存在，出现“请刷新后再试” |
| `thesis_limit_disables_add_button` | `ThesisList.test.tsx` | 5 条有效逻辑 | 按钮 disabled，说明含“最多 5 条” |
| `archive_requires_confirmation` | `HoldingsPage.test.tsx` | 点击归档 | 未确认前不调用 `holdings.archive` |
| `row_toggles_with_keyboard` | `HoldingsTable.test.tsx` | 行聚焦按 Enter | `aria-expanded=true`，逻辑区出现 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `pages/holdings/__fixtures__/holdings.json` | `holdings.list/default` | 从契约复制 |
| `pages/holdings/__fixtures__/theses.json` | `thesis.list/zzar` | 从契约复制；两条逻辑 |
| `pages/holdings/__fixtures__/search-ze.json` | `instruments.search/ze` | 从契约复制 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop && pnpm vitest run src/pages/holdings
# 期望：13 passed，0 failed
cd apps/desktop && pnpm tsc --noEmit
# 期望：exit=0
```
### 9.2 完成清单
- [ ] 1280×820 与 1024×700 截图覆盖 `default`、`expanded`、`editor-error`、`search`
- [ ] 像素比对通过；表格在窄窗口内部滚动，页面无横向溢出
- [ ] 所有数字等宽、右对齐；数量 0 显示“关注”
- [ ] 键盘可完成搜索、展开、编辑、保存、取消、归档确认
- [ ] 未修改 `owns` 之外文件；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| U-02 | `navigate("holdings",{thesis})` | 页面只展开对应标的，不自动打开编辑器 |
| U-05 / U-06 | 持仓标的、数量与代码 | 两页都重新查询，不读取本页缓存 |
| I-01 | `thesis.*` 乐观锁行为 | 冲突必须可复现并保留输入 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 编辑器宽度在 1024 下过窄 | 文本域换行严重 | 展开区占满行宽，操作区换行到下一行 |

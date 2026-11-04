---
id: U-05
title: 交易页
phase: mvp0
platform: shared
lane: ui
deps: [U-02]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [apps/desktop/src/pages/trading/, apps/desktop/src/i18n/zh-CN/trading.ts]
appends: []
stubs: []
---

# U-05 交易页

## 0. 一眼看懂

- **目标**：用回放时钟练习“下一交易日开盘价成交”的模拟交易：账户、下单、挂单、成交、持仓、历史订单和拒单原因。
- **完成后解锁**：I-01 可以演示下单被拒、推进成交、账户权益变化的完整路径。
- **预计规模**：约 9 个文件、代码加测试 560 行以内。

## 1. 背景与边界

### 1.1 为什么需要它
模拟账户让用户在不冒真实资金风险的情况下验证自己的判断。交易页必须把“冻结资金、T+1、开盘价成交、费用、拒单”讲清楚，不能用绿色按钮暗示收益。

### 1.2 范围内
1. 账户条、回放日期、下一交易日、重置账户。
2. 四个指标卡：现金、冻结资金、持仓市值、权益。
3. 下单面板：标的、方向、数量、固定“开盘市价单”、预估金额与费用。
4. 四个标签页：挂单、成交、持仓、历史订单。
5. 七种页面状态：默认、新账户、无账户、资金不足、可卖不足、无行情、推进后。
6. 键盘：分段控件、数量输入、提交、确认重置。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 撮合、费用、冻结、T+1 规则 | P-05 |
| 限价单、盘中止损、真实券商 | v1 / 永远不做 |
| K 线图 | v1 |
| 风险指标 | U-06 |
| 账户级导出 | v1 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [03-界面设计规范.md](../../03-界面设计规范.md) | §4.5 交易、§5.1–§5.5、§5.11 | 布局、表单、标签页 |
| [05-接口契约.md](../../05-接口契约.md) | §5.7 模拟交易、§7.3 订单状态 | RPC 与订单状态 |
| [08-模拟交易与风险.md](../../08-模拟交易与风险.md) | §3 账户、§4 下单、§5 撮合、§6 费用 | 文案与拒单原因 |

## 3. 前置条件

- U-02 已交付 `PageFrame`、`navigate`、错误 Toast 事件和 `app/format.ts`。
- U-01 已交付 `SegmentedControl`、`Field`、`Table`、`Modal`、`EmptyState`、`StatusTag`。
- C-05 的 mock 支持 `paper.*` 示例；时钟由 `account.clockDate` 提供，不得读本机日期。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `pages/trading/index.tsx` | 新建 | 页面入口、账户加载、标签页状态 |
| `pages/trading/AccountBar.tsx` | 新建 | 账户选择、回放日期、下一交易日、重置 |
| `pages/trading/PortfolioCards.tsx` | 新建 | 四个指标卡与格式化 |
| `pages/trading/OrderPanel.tsx` | 新建 | 标的搜索、方向、数量、预估、提交 |
| `pages/trading/OrdersTable.tsx` | 新建 | 四个标签页的表格 |
| `pages/trading/CreateAccountForm.tsx` | 新建 | 名称、初始现金、回放起始日 |
| `pages/trading/usePaper.ts` | 新建 | 账户、组合、订单、推进、重置 |
| `pages/trading/validation.ts` | 新建 | 数量、金额、账户名、确认文本 |
| `pages/trading/*.test.tsx` | 新建 | §8.1 的 9 个测试 |

## 5. 接口规格

### 5.1 公开接口
```ts
function TradingPage(): JSX.Element;
type PlaceOrderInput = {instrumentId:string;side:"buy"|"sell";quantity:number;orderType:"market_open";idempotencyKey:string}; type AdvanceResult = {clockDate:string;filled:PaperOrder[];rejected:PaperOrder[];pendingRemaining:number;portfolio:Portfolio};
function OrderPanel(props: {
  accountId: string; cash: string; availableCash: string;
  onSubmit: (input: PlaceOrderInput) => Promise<void>;
}): JSX.Element;
function PortfolioCards(props: { portfolio: Portfolio }): JSX.Element;
function OrdersTable(props: {
  tab: "pending"|"fills"|"positions"|"history";
  orders: PaperOrder[]; positions: Position[];
  onCancel: (orderId:string) => Promise<void>;
}): JSX.Element;
function validateOrder(input: {quantity:string; side:"buy"|"sell"; availableCash:string; sellable:number}): {
  ok: boolean; code?: "INVALID_QUANTITY"|"INSUFFICIENT_CASH"|"INSUFFICIENT_POSITION";
};
function usePaper(client: RpcClient): {
  accounts: PaperAccount[]; account: PaperAccount | null; portfolio: Portfolio | null;
  orders: PaperOrder[]; loading: boolean; refresh: () => Promise<void>;
  place: (input: PlaceOrderInput) => Promise<void>; advance: () => Promise<AdvanceResult>;
  reset: (confirmText:string) => Promise<void>;
};
```
- `place` 在一次“下单意图”开始时生成 `crypto.randomUUID()` 作为 `idempotencyKey`，并把键保存在 `pendingIntent` 中；超时、网络错误或用户重试都复用同一个键，直到确认成功或明确失败。用户修改数量/方向后开始新意图才生成新键。
- 超时后先调用 `paper.orders({accountId, idempotencyKey})` 查询是否已提交；查到订单则按已成功处理，不再重发。禁止在重试时生成新 UUID。
- `advance` 成功后更新 `clockDate`、组合与订单；失败时保留原时钟并显示原因。
- `validateOrder` 只做前端可判断的校验；最终以 `ORDER_REJECTED` 与 `data.orderId` 为准。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `PaperOrder.status` | enum | 是 | 4 个取值 | 标签文字与颜色 |
| `PaperOrder.estimate` | object \| null | 是 | 金额 Decimal | 预估区只读 |
| `Position.sellableQuantity` | number | 是 | ≥0 | 可卖数量，T+1 后变化 |
| `PaperAccount.clockDate` | IsoDate | 是 | 交易日 | 回放日期 |
| `Portfolio.equity` | Decimal string | 是 | = cash + marketValue | 指标卡 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `DEFAULT_CASH` | `"100000.00"` | `CreateAccountForm.tsx` | 新账户初始现金 |
| `QTY_STEP` | `1` | `OrderPanel.tsx` | 数量步长 |
| `ESTIMATE_DECIMALS` | `2` | `OrderPanel.tsx` | 预估金额显示位数 |
| `TABS` | `pending,fills,positions,history` | `OrdersTable.tsx` | 标签页顺序 |
| `CONFIRM_FIELD` | 账户名 | `ResetAccountModal.tsx` | 重置确认文本 |

## 6. 实现步骤

1. 挂载 `paper.accounts`；无账户时显示创建表单；有账户时默认选第一个并调用 `paper.portfolio` 与 `paper.orders`。加载中显示四个指标卡骨架和表头骨架。
2. 顶部账户条：账户下拉、`回放日期 {date}（{星期}）`、“下一交易日”主按钮、“重置账户”文字危险按钮。回放日期只显示日期，不显示本机时间。
3. 指标卡：现金、冻结资金、持仓市值、权益；金额 `$1,234.56`，权益用 `--text-num-l`。数值右对齐、等宽、不跳动。
4. 下单面板：标的搜索复用 `SearchInput`；方向用 `SegmentedControl`（买入/卖出）；数量为整数输入；类型只读“开盘市价单”。预估区显示“预估价 $28.4142 · 预估金额 $2,841.42 · 预估费用 $0.00”，并固定提示“按下一个交易日开盘价成交，价格可能与预估不同。”
5. 提交前校验：数量为正整数；买入预计金额 + 费用 ≤ 可用现金；卖出数量 ≤ 可卖数量。失败时不发 `paper.order.place`，直接在面板上方显示 danger 提示；但如果是服务端拒单，刷新历史并高亮新拒单。
6. 标签页：挂单按创建时间倒序；成交按 `filledOn` 倒序；持仓按市值倒序；历史订单含已拒绝、已取消。状态标签：待成交/info、已成交/ok、已拒绝/danger、已取消/none。
7. 点击“下一交易日”调用 `paper.advance`；成功后 Toast `10月15日：1 笔成交`，指标卡、持仓、订单同时刷新；无行情时显示“没有 {date} 的行情。请先刷新行情，或选择更早的回放日期。”
8. 重置账户打开 `Modal`，必须输入账户名才启用“确认重置”；确认后调用 `paper.reset`，成功后清空当前组合并回到新账户空状态。
9. 键盘：标签页 `ArrowLeft/ArrowRight` 切换；分段控件左右切换；数量输入只接受数字；`Enter` 提交；`Esc` 关闭重置模态框。
10. 所有金额计算使用接口返回的 Decimal 字符串；前端只做显示与格式化，不用 `Number` 累加现金。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（i18n 键） |
|---|---|---|---|
| 数量为 0/负数/小数 | 字段错误，不提交 | `INVALID_ARGUMENT` | `trading.invalidQuantity`：“数量必须是正整数” |
| 资金不足 | danger 提示，订单以 rejected 保存 | `ORDER_REJECTED` | `trading.insufficientCash`：“资金不足：预计需要 …，可用现金 …。” |
| 可卖不足 | danger 提示，订单 rejected | `ORDER_REJECTED` | `trading.insufficientPosition`：“可卖数量不足：持仓 0 股，要卖出 500 股。” |
| 重复提交 | 按钮禁用，返回原订单 | `CONFLICT` | 不提示（同一订单） |
| 无行情 | 保留时钟，提示刷新 | `DATA_INSUFFICIENT` | `trading.noPrice` |
| 重置确认文本错误 | 按钮禁用 | `INVALID_ARGUMENT` | `trading.confirmMismatch`：“请输入账户名以确认” |
| 账户不存在 | 回到无账户状态 | `NOT_FOUND` | `trading.accountMissing` |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `trading_default_renders_four_metric_cards` | `TradingPage.test.tsx` | `paper.portfolio/default` | 现金、冻结资金、持仓市值、权益四个标题 |
| `trading_zero_quantity_blocks_submit` | `OrderPanel.test.tsx` | 数量 `0` | 不发 `paper.order.place`，错误“数量必须是正整数” |
| `trading_insufficient_cash_shows_amounts` | 同上 | 预计 `92025.99`，可用 `90185.09` | 文本含两个金额 |
| `trading_place_reuses_idempotency_key_on_timeout` | 同上 | 提交后超时，再点重试 | 两次请求的 `idempotencyKey` 相同；先查询 `paper.orders`，不重复下单 |
| `trading_rejected_order_appears_in_history` | `OrdersTable.test.tsx` | 历史含 rejected | 状态“已拒绝”并显示拒单原因 |
| `trading_advance_updates_clock_and_toast` | `TradingPage.test.tsx` | `paper.advance/filled` | 回放日期更新，Toast 含“1 笔成交” |
| `trading_no_price_keeps_clock` | 同上 | `paper.advance` 抛 `DATA_INSUFFICIENT` | 日期不变，出现 warn 提示 |
| `trading_reset_requires_account_name` | `ResetAccountModal.test.tsx` | 空文本 | 确认按钮 disabled；输入账户名后 enabled |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `pages/trading/__fixtures__/portfolio.json` | `paper.portfolio/default` | 从契约复制 |
| `pages/trading/__fixtures__/orders.json` | `paper.orders/default` | 从契约复制 |
| `pages/trading/__fixtures__/rejected.json` | `paper.order.place/insufficient_cash` | 从契约复制 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop && pnpm vitest run src/pages/trading
# 期望：9 passed，0 failed
cd apps/desktop && pnpm tsc --noEmit
# 期望：exit=0
```
### 9.2 完成清单
- [ ] 1280×820 与 1024×700 截图覆盖 `default`、`error-cash`、`no_account`
- [ ] 四个指标卡金额稳定、等宽、右对齐
- [ ] 拒单显示具体数字原因，不只是“失败”
- [ ] 键盘可切换标签页、方向、提交、关闭模态框
- [ ] 未修改 `owns` 之外文件；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| I-01 | 下单与推进的完整链路 | 前端不重算费用；只显示接口值 |
| U-06 | 模拟持仓数量 | 风险页只读组合，不写回交易页 |
| E-01 | 演示账户与订单 | 演示数据必须使用虚构标的 `ZZ*` |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 前端预估与成交价差异引发误解 | 用户以为按预估价成交 | 固定提示“按下一交易日开盘价成交”；成交后显示实际价 |
| 双击导致重复冻结 | 挂单两条 | 提交期间禁用按钮 + 幂等键；服务端仍以幂等键为准 |
| 金额用浮点累计 | 末位差 0.01 | 所有金额显示直接格式化 Decimal 字符串 |

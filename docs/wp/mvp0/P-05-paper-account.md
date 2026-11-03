---
id: P-05
title: 模拟账户与订单：账本、回放时钟
phase: mvp0
platform: shared
lane: data
deps: [P-04, C-03, D-04, C-01]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [core/sentinel/trading/account.py, core/sentinel/trading/matching.py, core/sentinel/trading/ledger.py, core/sentinel/storage/migrations/010_paper.sql, core/tests/unit/trading/test_account.py, core/tests/unit/trading/test_matching.py, core/tests/unit/trading/test_ledger.py, core/sentinel/trading/__init__.py, core/sentinel/trading/models.py, core/sentinel/trading/rpc.py]
appends: []
stubs: []
---
# P-05 模拟账户与订单：账本、回放时钟

## 0. 一眼看懂
- **目标**：把 P-04 的纯规则接到持久化账户、订单、冻结、成交、持仓和权益快照，交付 8 个模拟交易 RPC。
- **完成后解锁**：U-05 可以下单与推进日期，E-01 可以载入演示账户。
- **预计规模**：实现约 620 行，测试约 360 行；3 个实现文件、3 个测试文件。

## 1. 背景与边界
### 1.1 为什么需要它
模拟交易的可信度来自账本而不是界面。现金必须由流水推导，冻结必须与挂单一致，成交只能使用回放时钟之后的下一个开盘价，重复点击与重试不能造成第二次成交。
### 1.2 范围内
1. 模拟账户创建、列表、组合读取和重置。
2. 下单校验、幂等键、拒单保存、买入冻结、取消释放。
3. 下一交易日开盘撮合、滑点、费用、持仓与平均成本。
4. 现金流水、冻结、权益快照和只读一致性检查。
5. 8 个 RPC 方法：`paper.accounts`、`paper.createAccount`、`paper.portfolio`、`paper.order.place`、`paper.order.cancel`、`paper.orders`、`paper.advance`、`paper.reset`。
### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 费用公式、滑点公式和纯撮合判断 | P-04 |
| 行情抓取与交易日历生成 | D-04 |
| 限价单、做空、融资、部分成交、分红拆股 | 不在 MVP-0 |
| 后台自动推进 | v1 调度工作包 |
| 真实券商接入 | 不做 |
| 其他迁移文件 | 各自工作包；本包只新增 `010_paper.sql`，不改 001–009、011–012 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | §2 回放时钟与持仓、§4 金额 | `Decimal`、交易日、UTC |
| [04-数据模型.md](../../04-数据模型.md) | §3.10 `010_paper.sql`、§4 请求哈希、§6 重置例外、§7 完整性、§8.5 | 表与不变量 |
| [08-模拟交易与风险.md](../../08-模拟交易与风险.md) | §2 回放、§4 下单、§5 撮合、§6 余额、§7 账本一致性 | 权威算法 |
| [05-接口契约.md](../../05-接口契约.md) | §4 `PaperAccount`/`PaperOrder`/`Portfolio`、§5.7、§7.3、§8 | RPC 与状态机 |

## 3. 前置条件
- P-04 提供 `precheck`、`estimate_buy`、`calculate_fees`、`match_at_open`、`request_hash`、`load_market_rules`。
- C-03 提供 `Database.read()`、`Database.write()` 和 `Database.backup(label: str) -> Path`；重置账户前必须调用 `backup("paper.reset")`。
- D-04 提供 `next_trading_day(date) -> date`、`latest_price_date(instrument_ids) -> date | None`、`close_on_or_before(instrument_id, date) -> PriceRow | None`、`open_on(instrument_id, date) -> Decimal | None`。
- C-01 提供 RPC 注册、`Decimal` 与 `date` 参数模型；所有时间为 UTC，日期按 `America/New_York` 交易日。
- `010_paper.sql` 由本包创建，内容逐字取自 [04](../../04-数据模型.md) §3.10；不得修改其他编号的迁移。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/trading/ledger.py` | 新建 | 现金、冻结、可用现金、持仓、权益查询与 7 项一致性检查 |
| `core/sentinel/trading/matching.py` | 新建 | 单笔订单事务：释放冻结、成交、费用、持仓、成交记录 |
| `core/sentinel/trading/account.py` | 新建 | `PaperService`、8 个用例、分页、重置和 handler 注册 |
| `core/sentinel/storage/migrations/010_paper.sql` | 新建 | 逐字复制 [04](../../04-数据模型.md) §3.10 的 6 张表 |
| `core/tests/unit/trading/test_ledger.py` | 新建 | 汇总、冻结、权益和损坏数据测试 |
| `core/tests/unit/trading/test_matching.py` | 新建 | 买单、卖单、拒单、回滚和平均成本测试 |
| `core/tests/unit/trading/test_account.py` | 新建 | RPC 用例、幂等、取消、推进、重置和随机序列测试 |

## 5. 接口规格
### 5.1 公开接口
```python
class PaperService:
    def __init__(self, db: Database, rules: MarketRules,
                 clock: Callable[[], datetime] = clock.now) -> None: ...
    def list_accounts(self) -> list[PaperAccountView]: ...
    def create_account(self, name: str, initial_cash: Decimal,
                       start_date: date) -> PaperAccountView: ...
    def portfolio(self, account_id: str) -> PortfolioView: ...
    def place_order(self, intent: OrderIntent) -> PaperOrderView: ...
    def cancel_order(self, order_id: str) -> PaperOrderView: ...
    def list_orders(self, account_id: str, status: str | None,
                    limit: int, cursor: str | None,
                    idempotency_key: str | None = None) -> PaperOrderPage: ...
    def advance(self, account_id: str) -> AdvanceResult: ...
    def reset(self, account_id: str, confirm_text: str) -> None: ...
def register_handlers(registrar: HandlerRegistrar, service: PaperService) -> None: ...
class Ledger:
    def totals(self, tx: SqlExecutor, account_id: str) -> LedgerTotals: ...
    def position_quantity(self, tx: SqlExecutor, account_id: str, instrument_id: str) -> int: ...
    def pending_sell_quantity(self, tx: SqlExecutor, account_id: str, instrument_id: str) -> int: ...
    def assert_invariants(self, tx: SqlExecutor, account_id: str) -> None: ...
def execute_order(tx: WriteTx, order: OrderRow, next_day: date,
                  open_price: Decimal | None, rules: MarketRules) -> MatchOutcome: ...
```
- `PaperService` 的 8 个 handler 全部以 `cancellable=False` 注册（C-01 §5.1）：账本写入不接受 `$/cancel`，避免“已成交但客户端收到 CANCELLED”。
- `place_order` 对参数错误不保存订单；对 `NO_PRICE`、`INSUFFICIENT_CASH`、`INSUFFICIENT_POSITION` 保存 `rejected` 订单并抛 `ORDER_REJECTED`，`data.orderId` 指向该行。
- `advance` 整次推进一个事务：成交、拒单、资金、持仓、时钟与快照一起提交；程序错误全部回滚。
- `reset` 删除前必须先成功备份；确认文字必须与账户名完全一致。用 `db.exclusive()` 包围确认、备份及删除事务，不直接引用存储私有锁。
- 所有 SQL 参数绑定；所有现金运算用 `Decimal`；数量用 `int`。
- 列表分页按 `created_at DESC, order_id DESC`，limit 默认 50、最大 200。
### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `LedgerTotals` | `cash` | Decimal | 是 | 4 位 | 全部实际现金流水 |
| | `reserved` | Decimal | 是 | ≥ 0 | 冻结资金 |
| | `available` | Decimal | 是 | cash − reserved | 可下单现金 |
| `PositionRow` | `quantity` | int | 是 | ≥ 0 | 持仓数量 |
| | `avgCost` | Decimal | 是 | 6 位 | 含买入费用 |
| `OrderRow` | `status` | enum | 是 | pending/filled/rejected/cancelled | 订单状态 |
| | `reservedCash` | Decimal | 否 | pending 买单必填 | 冻结额 |
| | `requestHash` | str | 是 | 64 位十六进制 | 幂等参数摘要 |
| `AdvanceResult` | `clockDate` | date | 是 | 新交易日 | 回放日期 |
| | `tradingDay` | bool | 是 | 成功时固定 `true` | 与 05 §5.7 对齐 |
| | `filled` / `rejected` | list | 是 | 订单视图 | 本批结果 |
| | `pendingRemaining` | int | 是 | ≥ 0 | 剩余挂单 |
| | `portfolio` | PortfolioView | 是 | 推进后的组合 | 与 05 §5.7 对齐 |
| `PortfolioView` | `cash` / `reservedCash` / `availableCash` | Decimal | 是 | 4 位 | 资金 |
| | `equity` | Decimal | 是 | 现金加市值 | 权益 |
| | `asOf` | date | 是 | 账户时钟 | 估值日 |
`PaperAccountView`、`PaperOrderView`、`PaperOrderPage` 的字段直接复用 [05-接口契约.md](../../05-接口契约.md) §4，本包不得改变金额字符串精度。
这三个视图以及 `PortfolioView`、`AdvanceResult` 必须是 `pydantic.BaseModel`（C-01 的 `Handler` 只接受 `BaseModel` 或 `dict`）；金额序列化为 4 位小数字符串，成交价 6 位。
### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MAX_ACCOUNT_NAME_CODEPOINTS` | `30` | `account.py` | 名称上限 |
| `INITIAL_CASH_QUANTUM` | `Decimal("0.0001")` | `account.py` | 初始现金精度 |
| `DEFAULT_ORDER_LIMIT` / `MAX_ORDER_LIMIT` | `50` / `200` | `account.py` | 订单分页 |
| `RANDOM_SEQUENCE_STEPS` | `200` | `test_account.py` | G3 随机序列步数 |
| `RANDOM_SEED` | `20261102` | `test_account.py` | 可重复随机测试 |

## 6. 实现步骤
1. **创建账户**：名称去空白后 1–30 码点；初始现金 `> 0` 且最多 4 位小数；名称唯一冲突返回 `CONFLICT`。`start_date` 必须满足 `next_trading_day(start_date - 1 day) == start_date`。事务内插入账户与一笔 `deposit(+initial_cash, entry_date=start_date)`。
2. **下单身份**：事务内读账户并拒绝已归档账户；按 `idempotency_key` 查订单。已有且 `request_hash` 相同返回原订单；哈希不同抛 `CONFLICT`。
3. **下单预检**：读取标的、当日收盘价、现金、持仓与其他挂卖单；调用 P-04。参数错误在写前置阶段抛 `INVALID_ARGUMENT`。**业务拒绝走独立事务**：在单独 `Database.write()` 中插入 `rejected` 订单并提交，提交成功后**在事务外**抛 `ORDER_REJECTED`；禁止在插入的同一事务内抛错（会导致该行回滚，`data.orderId` 失效）。
4. **冻结**：买单通过后插入 `pending` 订单，`reserved_cash = required`，写一条 `reserve(-required)`；卖单 `reserved_cash = NULL`，不写资金流水。订单、冻结与返回对象在一个事务提交。
5. **取消**：只接受 `pending`；状态改 `cancelled`，写 `release(+reserved_cash)`，清空 `reserved_cash`。重复取消或非 pending 抛 `CONFLICT`。
6. **推进前置**：`next_day = next_trading_day(clock_date)`；若 `latest_price_date(involved) is None` 或 `next_day > latest`，抛 `DATA_INSUFFICIENT` 且时钟不变。
7. **一次推进一个事务**：按卖单优先、再 `created_at`、`order_id` 排序；在**同一个 `Database.write()` 事务**内逐笔处理，调用 `open_on` 与 P-04 `match_at_open`。业务拒单（资金/持仓/无价）写入 rejected 结果并继续下一笔；程序异常直接抛出，整个事务回滚。
8. **成交记账**：买单先写 `release(+reserved_cash)`，再检查可用现金；足够时写 `buy(-amount)`、`fee(-fee)`，更新持仓数量与平均成本。卖单写 `sell(+amount)`、`fee(-fee)`，减少数量，`avg_cost` 不变；清仓保留 `quantity=0` 行。
9. **写成交与状态**：成交行字段为 price、quantity、amount、fee、slippage_bps；订单改 `filled`、清空 `reserved_cash`。拒单时释放冻结、写拒单码与中文消息、订单改 `rejected`；这些都在同一事务内。
10. **推进与快照**：在同一事务内把 `clock_date = next_day`，按当日收盘估值；缺当日收盘的持仓使用最近一个 `close <= next_day` 并记录 `warn`。写唯一 `equity_snapshot`，提交事务后返回 `AdvanceResult(...)`。
11. **失败语义**：任一笔程序错误或数据库错误都会回滚**整次推进**（成交、拒单、资金、持仓、时钟、快照全部不生效），`advance` 抛 `INTERNAL`；不会出现“D+1 已成交、时钟仍为 D”。业务拒单不是异常，不影响其他订单。
12. **组合读取**：现金、冻结和持仓从流水与 `position` 读取；市值只使用 `trade_date <= clock_date` 的行情。`sellableQuantity = quantity`，美股无 T+1。
13. **重置**：校验账户、确认名；先调用 `db.backup("paper.reset")` 并确认返回路径存在；事务内删除该账户的 `fill`、`paper_order`、`position`、`cash_ledger`、`equity_snapshot`，恢复 `clock_date=start_date`，写新 deposit。其他账户数据不得受影响；备份失败则不删除任何行。
14. **一致性**：每次 `advance` 后调用 `assert_invariants`：现金非负、持仓非负、冻结等于 pending 买单之和、权益等于现金加市值、成交金额等于价格乘数量、持仓等于买入减卖出。任一违规抛 `INTERNAL` 并保留现场。

## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 账户名重复或为空 | 不创建 | `CONFLICT` / `INVALID_ARGUMENT` | `error.CONFLICT` / `error.INVALID_ARGUMENT` |
| 初始现金不是正数 | 不写账户与流水 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 同幂等键同参数 | 返回原订单，不再冻结 | — | — |
| 同幂等键不同参数 | 不修改原订单 | `CONFLICT` | `error.CONFLICT` |
| 参数错误 | 不保存订单 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 资金或持仓业务拒绝 | 独立事务保存 rejected 后抛错，不冻结 | `ORDER_REJECTED` | `trading.*` |
| 取消非 pending | 状态不变 | `CONFLICT` | `error.CONFLICT` |
| 下一交易日无任何行情 | 不更新时钟、不撮合 | `DATA_INSUFFICIENT` | `error.DATA_INSUFFICIENT` |
| 任一笔订单 SQL/程序失败 | 整次推进回滚 | `INTERNAL` | `error.INTERNAL` |
| 重置确认文字错误 | 不备份、不删除 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 账本不变量失败 | 停止推进并记录错误编号 | `INTERNAL` | `error.INTERNAL` |

## 8. 测试（先写）
### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_cash_is_sum_of_real_entries` | `test_ledger.py` | deposit 10000、reserve 500、buy 4000、fee 1 | cash 5999.0000，reserved 500，available 5499.0000 |
| `test_reserved_equals_pending_buy_sum` | 同上 | 两个 pending 买单 1000/500 | 冻结 1500；构造差异后 integrity 报错 |
| `test_negative_cash_is_detected` | 同上 | 只有 buy −1 | integrity 返回 `negative_cash` |
| `test_buy_fill_updates_avg_cost_with_fee` | `test_matching.py` | 买 100、价 49.9、费 1；再买 50、价 52、费 1 | avgCost `50.613333` |
| `test_sell_fill_keeps_avg_cost` | 同上 | 60 股、avg 51.135550，卖 40 | quantity 20，avgCost 不变 |
| `test_fill_failure_rolls_back_reserve_and_position` | 同上 | 在写 fill 前注入异常 | 订单仍 pending，冻结与持仓不变 |
| `test_place_same_key_same_params_returns_original` | `test_account.py` | 同请求执行两次 | 同 orderId；只有一条 reserve |
| `test_place_same_key_different_params_conflicts` | 同上 | 数量 100 后改 101 | `CONFLICT`；原订单不变 |
| `test_business_rejection_is_saved_without_reserve` | 同上 | 预计需要超过可用现金 | rejected 行存在；reserve 0 条 |
| `test_parameter_error_is_not_saved` | 同上 | quantity 0 | `INVALID_ARGUMENT`；订单 0 行 |
| `test_cancel_releases_exact_reserved_amount` | 同上 | pending 买单冻结 2841.4200 | 取消后冻结 0，现金恢复 |
| `test_advance_uses_next_day_open_not_clock_day_close` | 同上 | D 日 close 100，D+1 open 110 | 成交价含 5 bps 为 110.055000 |
| `test_advance_does_not_read_future_prices` | 同上 | 只有 D+2 价格，无 D+1 | `DATA_INSUFFICIENT`，时钟仍 D |
| `test_advance_second_order_failure_rolls_back_all` | 同上 | 3 笔订单，第 2 笔注入异常 | 3 笔均不生效；时钟仍 D；无新增 fill/流水 |
| `test_gap_up_shortfall_rejects_and_releases` | 同上 | 释放冻结后差 0.0001 | `INSUFFICIENT_CASH_AT_FILL`，冻结 0 |
| `test_reset_removes_only_target_account` | 同上 | 两个账户 | 目标账户只剩 deposit；另一个数据不变 |
| `test_random_200_step_ledger_invariants` | `test_account.py` | seed 20261102，买/卖/取消/推进各 50 次 | 每步后 7 项不变量全通过 |
### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增文件 | 临时 DuckDB、固定时钟、虚构 `us:ZZAR`、5 个连续交易日行情（`2026-10-26` 至 `2026-10-30`） | 测试内插入；重置测试前用真实备份函数写临时目录 |

## 9. 验收
### 9.1 命令与期望输出
```bash
(cd core && uv run pytest tests/unit/trading/test_ledger.py tests/unit/trading/test_matching.py tests/unit/trading/test_account.py -q)
# 期望：17 passed，0 failed
scripts/check.sh
# 期望：exit=0；ruff、mypy 对 sentinel/trading 全绿
```
### 9.2 完成清单
- [ ] 第 4 节全部文件存在，`owns` 外无改动
- [ ] `010_paper.sql` 与 04 §3.10 的 6 张表逐字一致
- [ ] 8 个 RPC 方法严格匹配 §5.7
- [ ] 每次 advance 后账本 7 项不变量通过
- [ ] 200 步随机序列可重复通过
- [ ] 已写 `docs/wp/status/P-05.md`

## 10. 交接、风险与回退
| 对象 | 使用或风险 | 约定与回退 |
|---|---|---|
| U-06 | 使用 8 个 RPC 方法 | 金额为 4 位字符串；成交价为 6 位字符串；界面显示拒单原因；收到 `INTERNAL` 后刷新组合与订单列表（整次推进已回滚） |
| E-01 | 创建演示账户与订单 | 只调用公开 RPC 或用同一服务方法，不直接写账本 |
| I-01 | 端到端验证下单与推进 | 先刷新行情；缺少目标日行情时不出成交 |
| 推进中途程序错误 | 整次推进回滚，时钟与成交均不变 | 用户重试；不会出现混合状态 |
| 重置误删风险 | 用户确认文字错误 | 全等校验；删除前备份；只有目标账户数据被删 |
| 行情缺失 | 权益使用最近收盘 | 日志与界面标注数据截至；禁止使用未来行情 |

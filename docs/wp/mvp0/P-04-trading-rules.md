---
id: P-04
title: 模拟交易规则：校验、费用、撮合
phase: mvp0
platform: shared
lane: data
deps: [C-00]
size: S
owns: [core/sentinel/trading/rules.py, core/sentinel/trading/fees.py, core/sentinel/messages/trading.py, core/tests/unit/trading/test_rules.py, core/tests/unit/trading/test_fees.py]
appends: []
stubs: []
---
# P-04 模拟交易规则：校验、费用、撮合

## 0. 一眼看懂
- **目标**：用纯函数实现美股只做多、整数股、开盘市价单的参数校验、资金持仓校验、滑点、费用、拒单和下一交易日开盘撮合。
- **完成后解锁**：P-05 可以在此基础上实现持久化账户、订单事务与账本。
- **预计规模**：实现约 330 行，测试约 260 行；2 个实现文件、2 个测试文件。

## 1. 背景与边界
### 1.1 为什么需要它
费用和撮合如果混进数据库代码，测试会同时依赖网络数据、当前时间和持久化状态。本包把规则做成不读数据库、不发网络请求、只使用显式输入的纯函数，P-05 负责事务。
### 1.2 范围内
1. 可配置的美股规则对象与 TOML 加载、校验。
2. 下单参数与业务前置校验的第 4–8 步。
3. 买入预估、冻结金额和请求哈希。
4. 佣金、SEC Section 31 费、FINRA TAF 与滑点。
5. 下一交易日开盘撮合的纯函数结果：成交、拒单或继续挂起。
6. 上述规则的全部边界测试与文档数值样例。
### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 账户、持仓、订单、流水落库 | P-05 |
| 交易日历推进与行情读取 | P-05、D-04 |
| 限价单、卖空、融资、碎股、盘中止损 | 不在 MVP-0 |
| 真实券商下单 | 不做 |
| 修改运行时配置文件 | 部署包提供配置；本包只读取调用方传入的路径 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | §4 时间与金额、§5 环境变量 | `Decimal`、舍入和时间边界 |
| [08-模拟交易与风险.md](../../08-模拟交易与风险.md) | §1 原则、§3 配置、§4 下单、§5 撮合与费用、§6 余额、§7 账本一致性 | 权威算法与样例 |
| [05-接口契约.md](../../05-接口契约.md) | §3 错误、§4 `PaperOrder`、§5.7、§7.3、§8 | RPC 参数、订单状态和幂等 |
| [04-数据模型.md](../../04-数据模型.md) | §3.10 `010_paper.sql` | 金额精度与订单字段 |

## 3. 前置条件
- C-00 已提供 `UserError`、`InternalError`、`new_id()`、`clock.now()`、金额字符串转换。
- 调用方传入的账户、标的、行情快照与挂单数量都是已校验对象，本包不查数据库。
- 运行配置 `resources/market_rules/us.toml` 由部署资源提供。P-04 只实现加载器和校验，不创建该路径，因为本包 `owns` 不包含 `resources/`。
- SEC 与 FINRA 的当前费率属于外部事实，必须标 `TODO-VERIFY(P-04)`；未核实就把费率写为 0 且 `verified=false`，界面显示占位提示。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/trading/rules.py` | 新建 | `MarketRules`、`load_market_rules`、参数与业务前置校验、买入预估、请求哈希 |
| `core/sentinel/trading/fees.py` | 新建 | `FeeConfig`、`FeeBreakdown`、`calculate_fees`、`match_at_open` |
| `core/sentinel/messages/trading.py` | 新建 | 拒单与不支持订单类型文案；由协调者加入公共文案目录 |
| `core/tests/unit/trading/test_rules.py` | 新建 | 配置、预检、预估、哈希测试 |
| `core/tests/unit/trading/test_fees.py` | 新建 | 费用数值、舍入、撮合和拒单测试 |

## 5. 接口规格
### 5.1 公开接口
```python
@dataclass(frozen=True)
class MarketRules:
    market: str
    currency: str
    slippage_bps: Decimal
    commission_per_share: Decimal
    commission_min: Decimal
    commission_max_pct: Decimal
    sec_fee_per_million: Decimal
    sec_effective_from: str
    sec_source: str
    sec_verified: bool
    taf_per_share: Decimal
    taf_max_per_trade: Decimal
    taf_effective_from: str
    taf_source: str
    taf_verified: bool
    max_order_quantity: int
    max_pending_orders: int
    max_wait_trading_days: int
def load_market_rules(path: Path) -> MarketRules: ...
def validate_parameters(intent: OrderIntent, pending_count: int,
                        rules: MarketRules) -> None: ...
def precheck(intent: OrderIntent, snapshot: MarketSnapshot,
             available_cash: Decimal, held: int, pending_sell: int,
             rules: MarketRules) -> PrecheckResult: ...
def estimate_buy(close: Decimal, quantity: int,
                 rules: MarketRules) -> BuyEstimate: ...
def request_hash(account_id: str, intent: OrderIntent) -> str: ...
def calculate_fees(side: Side, quantity: int, amount: Decimal,
                   cfg: FeeConfig) -> FeeBreakdown: ...
def match_at_open(intent: OrderIntent, open_price: Decimal | None,
                  waited_days: int, reserved_cash: Decimal,
                  available_cash_after_release: Decimal, held: int,
                  rules: MarketRules) -> MatchResult: ...
```
- `validate_parameters` 覆盖 [08-模拟交易与风险.md](../../08-模拟交易与风险.md) §4.1 第 4、5 步；失败抛 `INVALID_ARGUMENT`。
- `precheck` 覆盖第 6–8 步；业务拒绝返回 `PrecheckResult.reject`，不抛异常，便于 P-05 保存拒单。
- `match_at_open` 不读时钟、不读数据库、不写数据库；所有数值由参数提供。
- 金额计算只用 `Decimal`；`float` 在入口即被拒绝，防止静默精度损失。
- 所有函数线程安全、幂等、无全局可变状态。
### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `OrderIntent` | `accountId` | str | 是 | 非空 | 账户 |
| | `instrumentId` | str | 是 | `us:` 前缀 | 标的 |
| | `side` | enum | 是 | `buy/sell` | 方向 |
| | `quantity` | int | 是 | 正整数 | 整数股 |
| | `orderType` | str | 是 | 固定 `market_open` | 订单类型 |
| | `idempotencyKey` | str | 是 | 1–64 字符 | 幂等键 |
| `MarketSnapshot` | `clockDate` | date | 是 | 交易日 | 下单模拟日 |
| | `close` | Decimal/null | 是 | > 0 或 null | 当日收盘价 |
| | `maxOrderQuantity` | int | 是 | > 0 | 来自规则 |
| `PrecheckResult` | `estimate` | BuyEstimate/null | 否 | 买单非空；含 price/amount/fee/required | 预估 |
| | `reject` | Reject/null | 否 | 与 estimate 互斥；含 code/messageKey/data | 业务拒绝 |
| `FeeBreakdown` | `commission` | Decimal | 是 | 2 位小数 | 佣金 |
| | `sec` / `taf` | Decimal | 是 | 2 位小数 | 卖出监管费 |
| | `total` | Decimal | 是 | 三项之和 | 总费用 |
| `MatchResult` | `kind` | enum | 是 | `filled/rejected/pending` | 撮合结果 |
| | `price` / `amount` / `fee` | Decimal | 成交必填 | 6/4/4 位 | 成交数据 |
| | `rejectCode` | str | 否 | 六种拒单码 | 拒单原因 |
### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MONEY_QUANTUM` | `Decimal("0.0001")` | `rules.py` | 金额 4 位 |
| `PRICE_QUANTUM` | `Decimal("0.000001")` | `rules.py` | 价格 6 位 |
| `CENT_QUANTUM` | `Decimal("0.01")` | `fees.py` | 费用 2 位 |
| `BPS_DENOMINATOR` | `Decimal("10000")` | `fees.py` | 基点换算 |
| `SEC_MILLION` | `Decimal("1000000")` | `fees.py` | Section 31 分母 |
| `DEFAULT_SLIPPAGE_BPS` | `Decimal("5")` | `rules.py` | 买加上浮、卖下压 |

## 6. 实现步骤
1. **加载配置**：用 `tomllib.loads(path.read_text("utf-8"))`；所有数值字段先按字符串读取再 `Decimal`，拒绝二进制浮点。市场固定 `us`、币种固定 `USD`；`taf_per_share > 0` 且 `taf_max_per_trade <= 0` 抛 `InternalError`。
2. **参数校验**：`side` 非法、`orderType != "market_open"`、数量非正整数或超过 `max_order_quantity`、幂等键空或超过 64 字符、`pending_count >= max_pending_orders` 时抛 `INVALID_ARGUMENT`，`field` 指向对应字段。
3. **前置校验顺序**：先检查 `close is None or close <= 0` → `NO_PRICE`；再检查买单 `available_cash < required` → `INSUFFICIENT_CASH`；再检查卖单 `held - pending_sell < quantity` → `INSUFFICIENT_POSITION`。第一个失败原因就是唯一拒单原因。
4. **买入预估**：`estimate_price = round6(close × (1 + slippage_bps/10000))`；`amount = round4(price × quantity)`；`fee = calculate_fees("buy", quantity, amount, cfg)`；`required = amount + fee`；不加安全余量。
5. **请求哈希**：`sha256(f"{account_id}|{instrument_id}|{side}|{quantity}|{order_type}")`，输出 64 位小写十六进制；不包含幂等键和时间。
6. **费用**：`commission = max(min, round2(quantity × per_share))`；若 `max_pct > 0`，再取 `min(commission, round2(amount × max_pct / 100))`。买入 SEC 与 TAF 为 0。
7. **卖出监管费**：`sec = ceil2(amount / 1_000_000 × sec_per_million)`；`taf = min(taf_max, ceil2(quantity × taf_per_share))`；`total = commission + sec + taf`，每项先量化到 0.01。
8. **撮合**：无开盘价时，`waited_days + 1 >= max_wait_trading_days` 返回 `NO_PRICE_AT_FILL` 拒单，否则返回 pending。成交价按方向应用滑点，金额与费用按第 4–7 步计算。
9. **买单资金**：先假定冻结已释放，若 `available_cash_after_release < amount + fee` 返回 `INSUFFICIENT_CASH_AT_FILL`；足够才返回 filled。
10. **卖单持仓**：`held < quantity` 返回 `INSUFFICIENT_POSITION_AT_FILL`；足够才返回 filled。卖出不改变平均成本，由 P-05 处理。

## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 限价单或其他订单类型 | 不进入业务校验 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT`，原因“暂不支持限价单” |
| 浮点金额传入 | 立即拒绝，`field` 指向金额字段 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 无当日收盘价 | 保存 rejected 订单 | `ORDER_REJECTED` / `NO_PRICE` | `trading.no_price` |
| 买单资金不足 | 保存 rejected，包含 required 与 available | `ORDER_REJECTED` / `INSUFFICIENT_CASH` | `trading.insufficient_cash` |
| 卖单持仓不足 | 保存 rejected，包含 held 与 requested | `ORDER_REJECTED` / `INSUFFICIENT_POSITION` | `trading.insufficient_position` |
| 连续 5 个交易日无开盘价 | 撮合返回拒单并释放冻结 | `ORDER_REJECTED` / `NO_PRICE_AT_FILL` | `trading.no_price_at_fill` |
| 开盘跳空后资金不足 | 释放冻结后拒绝，不产生负现金 | `ORDER_REJECTED` / `INSUFFICIENT_CASH_AT_FILL` | `trading.insufficient_cash_at_fill` |
| 卖出时持仓不足 | 防御性拒单 | `ORDER_REJECTED` / `INSUFFICIENT_POSITION_AT_FILL` | `trading.insufficient_position_at_fill` |
| TAF 单价非零但上限为 0 | 启动即视为配置错误 | `INTERNAL` | `error.INTERNAL` |

## 8. 测试（先写）
### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_config_and_parameter_guards` | `test_rules.py` | 无 `meta.market`；quantity 0；pending 50/上限 50 | 依次为 `InternalError`、`field="quantity"`、`INVALID_ARGUMENT` |
| `test_precheck_returns_no_price_before_cash` | 同上 | close null 且资金不足 | 只返回 `NO_PRICE` |
| `test_buy_estimate_matches_document_sample_a` | 同上 | close 28.40、100 股、5 bps、无费用；另以 open 51.10 买 100 | 预估 `28.414200/2841.4200`；样例 A 成交价 `51.125550`，金额 `5112.5550` |
| `test_request_hash_is_stable_64_hex` | 同上 | `acct-1, us:ZZAR, buy, 100, market_open` | `sha256` 固定测试向量一致 |
| `test_buy_fees_use_commission_minimum` | `test_fees.py` | 数量 100、金额 5112.5550 | commission `1.00`，total `1.00` |
| `test_sell_fee_samples_b_and_e` | 同上 | 100 股/5107.4450；60000 股/599700.0000 | 前者 SEC `0.15`、TAF `0.02`、total `1.17`；后者 TAF `8.30`、total `324.98` |
| `test_no_open_price_fifth_day_boundary` | 同上 | waited 3；waited 4；上限 5 | 前者 `pending`；后者 `NO_PRICE_AT_FILL` |
| `test_buy_fill_rejects_on_gap_up_cash_shortfall` | 同上 | 释放冻结后可用 2857.4274，需要 2857.4275 | `INSUFFICIENT_CASH_AT_FILL` |
| `test_sell_fill_preserves_positive_amount` | 同上 | open 20.00、5000 股 | amount `99950.0000`，kind filled |
### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增文件 | 每个测试用 `tmp_path` 写最小 `us.toml`；费用样例使用 §5.2 的测试专用费率 | 测试内构造，不依赖真实费率 |

## 9. 验收
### 9.1 命令与期望输出
```bash
(cd core && uv run pytest tests/unit/trading/test_rules.py tests/unit/trading/test_fees.py -q)
# 期望：9 passed，0 failed
scripts/check.sh
# 期望：exit=0；ruff、mypy 对 sentinel/trading/rules.py、fees.py 全绿
```
### 9.2 完成清单
- [ ] 第 4 节全部文件存在，`owns` 外无改动
- [ ] 所有金额输入和输出均为 `Decimal`，序列化为十进制字符串
- [ ] 第 5.3 节测试费率没有写入生产配置
- [ ] 外部费率都有 `TODO-VERIFY(P-04)` 或真实来源与 `verified=true`
- [ ] 已写 `docs/wp/status/P-04.md`

## 10. 交接、风险与回退
| 对象 | 使用或风险 | 约定与回退 |
|---|---|---|
| P-05 | 使用 `precheck`、`estimate_buy`、`calculate_fees`、`match_at_open`、`request_hash` | P-05 负责保存拒单、释放冻结和更新状态；纯函数只返回结果 |
| 费率变化 | SEC 或 FINRA 调整费率 | 修改部署配置的 `effective_from/source/verified`，不改代码 |
| 配置不可读 | 应用无法安全交易 | 启动时 `INTERNAL`；交易页禁用下单，其他页面可用 |
| 占位费率为 0 | 回测收益略高 | 交易页显示“监管费率为占位值”，报告不得声称已核实 |
| 开盘无价长期挂起 | 订单占用挂单上限 | 第 5 个交易日自动拒单并释放冻结 |

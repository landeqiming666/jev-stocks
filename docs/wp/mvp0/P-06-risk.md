---
id: P-06
title: 风险计算
phase: mvp0
platform: shared
lane: data
deps: [C-03, D-04, C-01]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [core/sentinel/quant/, core/sentinel/storage/migrations/011_risk.sql, core/tests/unit/quant/, core/sentinel/messages/risk.py]
appends: []
stubs: []
---
# P-06 风险计算

## 0. 一眼看懂
- **目标**：实现持仓组合的年化波动率、最大回撤、有效持仓数、前三大权重、相关矩阵、收缩条件数、SVD 风险因子和审计记录。
- **完成后解锁**：U-06 可以展示风险页，I-02 可以完成风险验收。
- **预计规模**：实现约 520 行，测试约 320 行；5 个实现文件、4 个测试文件。

## 1. 背景与边界
### 1.1 为什么需要它
风险页必须能从相同行情与持仓复现同一组数。计算层做成纯函数，服务层只负责取数与审计，可以把数值错误与数据库错误分开定位。
### 1.2 范围内
1. 从持仓、行情和日历窗口构造共同交易日与收益率矩阵。
2. 收益、协方差、相关矩阵、年化波动率、最大回撤、有效持仓数。
3. 0.1 收缩估计、原始与收缩后的条件数。
4. 标准化收益的 SVD、解释方差占比和第一主成分载荷。
5. 样本不足、零方差、单持仓、价格未复权和数据年限不足的警告。
6. `risk.compute` RPC 与 `risk_run` 审计记录。
### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 行情刷新 | D-04 |
| 持仓编辑与市值展示 | P-01、U-03 |
| 人民币汇率与多币种口径 | v1 |
| 组合优化、下单建议、目标价 | 不做 |
| 其他迁移文件 | 各自工作包；本包创建 `011_risk.sql`，不改其他编号 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | §2 共同交易日、§4 数值 | 数值类型与展示规则 |
| [04-数据模型.md](../../04-数据模型.md) | §3.5 `price_daily`、§3.11 `011_risk.sql`、§8.2 | 行情与审计字段 |
| [08-模拟交易与风险.md](../../08-模拟交易与风险.md) | §8.1 输入、§8.2 步骤、§8.3 输出、§8.4 数值样例、§8.5 边界 | 权威公式和期望值 |
| [05-接口契约.md](../../05-接口契约.md) | §4 `RiskResult`、§5.8、§3.2 `DATA_INSUFFICIENT` | RPC 返回与错误 |

## 3. 前置条件
- C-03 提供 `Database.read()`、`Database.write()` 和 `new_id()`。
- D-04 提供前复权行情 `adj_close`、原始 `close` 和交易日历读取能力。
- C-01 提供 `risk.compute` 参数模型与 `register`。
- 本包创建 `011_risk.sql`，迁移前须核对 04 §3.11 权威 DDL。
- 依赖 `numpy` 已由 WP-00 锁定；本包不新增第三方库。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/quant/__init__.py` | 新建 | 导出 `RiskService`、`compute_risk`、`RiskInput` |
| `core/sentinel/quant/models.py` | 新建 | 输入、输出、持仓点和价格点数据结构 |
| `core/sentinel/quant/prices.py` | 新建 | 日历窗口、共同交易日、价格基线和收益率矩阵 |
| `core/sentinel/quant/risk.py` | 新建 | 协方差、相关、波动率、回撤、收缩、特征值、SVD 纯函数 |
| `core/sentinel/quant/service.py` | 新建 | 取数、权重、审计记录和 RPC handler |
| `core/sentinel/storage/migrations/011_risk.sql` | 新建 | 逐字复制 [04](../../04-数据模型.md) §3.11 的 `risk_run` 表 |
| `core/tests/unit/quant/test_prices.py` | 新建 | 窗口、共同日、缺价和价格基线测试 |
| `core/tests/unit/quant/test_risk.py` | 新建 | 数值样例与边界测试 |
| `core/tests/unit/quant/test_service.py` | 新建 | 数据库取数、审计和 RPC 测试 |

## 5. 接口规格
### 5.1 公开接口
```python
@dataclass(frozen=True)
class PricePoint:
    trade_date: date
    close: float
    adj_close: float | None
@dataclass(frozen=True)
class HoldingPoint:
    instrument_id: str
    symbol: str
    quantity: Decimal | int
@dataclass(frozen=True)
class RiskInput:
    symbols: list[str]
    instrument_ids: list[str]
    returns: np.ndarray             # shape (T, n)
    weights: np.ndarray             # shape (n,)
    endpoint_closes: np.ndarray     # shape (n,)
    window_observations: int
    periods_per_year: float
    price_basis: Literal["adj_close", "close"]
def build_risk_input(holdings: Sequence[HoldingPoint],
                     prices: Mapping[str, Sequence[PricePoint]],
                     window: Literal["6M", "1Y", "3Y"],
                     min_observations: int = 60) -> RiskInput: ...
def compute_risk(data: RiskInput, *, shrinkage_alpha: float = 0.1,
                 singularity_ratio: float = 1e-12) -> RiskResult: ...
class RiskService:
    def compute(self, scope: str, window: str, currency: str) -> RiskResult: ...
def register_handlers(registrar: HandlerRegistrar, service: RiskService) -> None: ...
```
- `min_observations` 的生产调用固定为 60；单元测试可传 4 复现文档小样本。
- `compute_risk` 是纯函数，不读数据库、不读时钟、不写文件；输入数组必须是有限 `float64`。
- `build_risk_input` 负责剔除无持仓和无有效基线标的；零方差资产保留，日内缺价按有效一日收益交集处理，并保持 `symbols` 与矩阵列一一对应。
- `RiskService.compute` 只接受 `scope="holdings"`、`window` 三选一、`currency="USD"`；其他值 `INVALID_ARGUMENT`。
### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `RiskResult` | `asOf` | date | 是 | 窗口终点 | 数据截止 |
| | `window.from` | date | 是 | 第一个共同日 | 起点 |
| | `window.observations` | int | 是 | ≥ 60 | 收益率数 |
| | `annualizedVol` | float | 是 | ≥ 0 | 年化波动率 |
| | `maxDrawdown` | float | 是 | ≥ 0 | 最大回撤 |
| | `effectiveHoldings` | float | 是 | > 0 | `1/Σw²` |
| | `topWeights` | list[object] | 是 | 降序前 3 | `instrumentId/symbol/weight` |
| | `correlation.matrix` | list[list] | 是 | n×n，对角 1 | 相关矩阵 |
| | `svd.explained` | list[float] | 是 | 和 ≤ 1，前 5 | 解释方差占比 |
| | `conditionNumberRaw/Shrunk` | float/null | 是 | > 0 或 null | 条件数 |
| | `warnings` | list[str] | 是 | 可空 | 用户可见警告 |
| | `excluded` | list[object] | 是 | `instrumentId/symbol/reason` | 剔除项 |
| `risk_run` | `instrument_ids` | JSON 文本 | 是 | 数组 | 参与标的 |
| | `params_json` | JSON 文本 | 是 | 参数与代码版本 | 可复现参数 |
| | `result_json` | JSON 文本 | 是 | 与 RPC 结果一致 | 审计结果 |
### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `WINDOW_MONTHS` | `{"6M": 6, "1Y": 12, "3Y": 36}` | `prices.py` | 日历窗口 |
| `PERIODS_PER_YEAR` | `252` | `risk.py` | 固定日频年化参数；窗口标签不参与 |
| `MIN_OBSERVATIONS` | `60` | `risk.py` | 生产样本门槛 |
| `SHRINKAGE_ALPHA` | `0.1` | `risk.py` | 收缩强度 |
| `SINGULARITY_RATIO` | `1e-12` | `risk.py` | 条件数空值阈值 |
| `MAX_EXPLAINED_COMPONENTS` | `5` | `risk.py` | 解释方差与载荷上限 |

## 6. 实现步骤
1. **窗口终点**：行情不超过已收盘市场日；终点为所有参与标的共同具有有效原 close 的最近交易日。通常等于 min(latest)，该上界存在内洞则退到共同日但保留资产权重。起点用日历月回退：6/12/36 个月，目标月无该日时取月末。
2. **价格基线**：窗口内所有参与标的的 `adj_close` 均非空时使用 `adj_close`；任一缺失时全部使用 `close`，并加“价格未复权”警告。
3. **逐只收益**：按市场交易日历对每只标的计算相邻交易日的简单收益 `P_t/P_{t-1}-1`；任一端点缺失或非有限值，该日收益无效。禁止先删除缺价日再计算，避免把多日收益压成日收益。
4. **有效交集与门槛**：取所有标的都拥有有效一日收益的日期交集，升序排列，`T = len(intersection)`；`T < 60` 抛 `DATA_INSUFFICIENT(data.observations=T, required=60)`。
5. **权重**：`w_i = quantity_i × endpoint_close_i / Σ`，`endpoint_close` 使用窗口终点原始 `close`，不是复权价。矩阵列顺序按持仓 symbol 升序。
6. **协方差与相关**：`X = R - R.mean(axis=0)`；`Σ = X.T @ X / (T - 1)`。**零方差资产保留在 `R`、`w` 和 `Σ` 中**，对应零行零列；`ρ_ij` 对零方差列返回 `null`，不重算权重。`n=1` 时相关矩阵固定 `[[1.0]]` 并加警告。
7. **年化波动率**：组合历史收益 `p_t = R[t] @ w`；`annualizedVol = sqrt(PERIODS_PER_YEAR × w.T @ Σ @ w)`，`PERIODS_PER_YEAR = 252`。窗口标签只决定取数区间；3Y 只有 1Y 数据时年化仍用 252。
8. **最大回撤**：`V_0=1`，`V_t=V_{t-1}(1+p_t)`；`peak_t=max(V_0..V_t)`；结果为 `max((peak_t-V_t)/peak_t)`，非负。
9. **收缩与条件数**：`target = trace(Σ)/n`；`Σ_α=(1-α)Σ+α×target×I`；`eigvalsh` 求特征值。若 `λmin <= 1e-12×λmax`，条件数为 null 并加“协方差矩阵接近奇异”；否则为 `λmax/λmin`。
10. **SVD**：仅对样本标准差 `s_i > 0` 的列做 `Z=X_col/s_i`；`U,S,Vt=np.linalg.svd(Z, full_matrices=False)`；`explained=S²/ΣS²`，取前 `min(5,n)`。零方差列不参与分解，但输出中保留标的映射并标注为 `null`/排除。
11. **载荷方向**：第一主成分取 `Vt[0]`；找绝对值最大的索引，若其值为负则整体乘 −1；按 `abs(value) DESC, symbol ASC` 取前 5。
12. **输出转换**：NumPy 标量转为 Python `float`，非有限值转 null；相关矩阵对角线强制 `1.0`；`topWeights` 按权重降序、symbol 升序取前 3。
13. **服务层**：查询 `quantity > 0` 且未归档持仓；调用 `build_risk_input` 与 `compute_risk`；在写事务中插入 `risk_run`，`result_json` 使用 `json.dumps(allow_nan=False)`。
14. **警告合并**：固定顺序为未复权、接近奇异、单持仓、最新行情落后窗口终点超过 3 个交易日、3Y 实际不足三年。相同文本只出现一次。

## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| `scope/window/currency` 非法 | 不计算 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 没有 `quantity > 0` 持仓 | 不写 `risk_run` | `DATA_INSUFFICIENT` | “没有可计算的持仓” |
| 共同交易日少于 60 | `data.observations/required` | `DATA_INSUFFICIENT` | “样本不足：共同交易日 {n} 天，至少需要 60 天。” |
| 全部标的零方差 | 返回零波动率；相关/SVD 为 null | — | “资产无波动，相关性与主成分无法计算。” |
| 只有 1 只持仓 | 返回波动率、回撤、权重和 `[[1]]` | — | 警告“至少需要 2 只持仓” |
| 协方差接近奇异 | 条件数为 null | — | 警告“协方差矩阵接近奇异” |
| 任一复权价缺失 | 使用原始收盘价 | — | 警告“价格未复权” |
| 3Y 实际不足三年 | 用可得共同日计算 | — | 警告“数据不足三年，实际 {起点} 起” |
| 输入含 NaN 或 inf | 视为该日缺价 | — | 不产生非有限输出 |

## 8. 测试（先写）
### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_window_and_calendar_start` | `test_prices.py` | 两只最新日 10-30/10-28；终点 2026-08-31 | 终点 10-28；6M 起点 2026-02-28 |
| `test_price_basis_and_common_days` | 同上 | 一只 `adj_close=None`；10-28 只一只标的有价 | basis `close` 并警告；10-28 被丢弃 |
| `test_insufficient_and_zero_variance_is_kept` | `test_risk.py` | T=59；第 2 列全为 0 | 前者 `DATA_INSUFFICIENT`；后者保留第 2 列，相关格为 null |
| `test_annualization_is_252_regardless_of_window_label` | 同上 | 同一组 252 天收益，标签 1Y 与 3Y | 年化波动率完全相等 |
| `test_missing_endpoint_does_not_create_multi_day_return` | `test_prices.py` | A `100→110→100→110`，B 缺第 2 日 | 只保留有效一日收益，不出现跨两日收益 |
| `test_zero_variance_asset_keeps_weight_and_portfolio_vol` | `test_risk.py` | 50% 恒价 + 50% 日波动 1% | 有效持仓 2；组合波动 0.5% |
| `test_document_covariance_and_correlation` | 同上 | §8.4 的 3×4 收益率矩阵 | 协方差逐项 `1e-9` 一致；ρ12 `0.6`，其余非对角 `0` |
| `test_document_condition_numbers` | 同上 | alpha 0.1 | raw `11.050128313`；shrunk `6.937910721` |
| `test_document_vol_drawdown_and_effective_holdings` | 同上 | w `(0.5,0.3,0.2)`、periods 252 | vol `0.2186229631`；回撤 `0.0194042931`；有效持仓 `2.6315789474` |
| `test_document_svd_and_sign` | 同上 | 同一样例；Vt 第一列为负 | explained `(0.5333333333, 0.3333333333, 0.1333333333)`；最大载荷为正 |
| `test_single_holding_and_service_audit` | 同上、`test_service.py` | n=1、T=60；合法持仓与价格 | `[[1.0]]` 且警告；`risk_run` 的 JSON 等于 RPC 结果 |
### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增文件 | `§8.4` 小样本在测试内写成 `np.array`；服务测试在临时 DuckDB 插入三只虚构标的、65 个共同交易日 | 测试内构造；不联网 |

## 9. 验收
### 9.1 命令与期望输出
```bash
(cd core && uv run pytest tests/unit/quant -q)
# 期望：11 passed，0 failed
scripts/check.sh
# 期望：exit=0；ruff、mypy 对 sentinel/quant 全绿
```
### 9.2 完成清单
- [ ] 第 4 节全部文件存在，`owns` 外无改动
- [ ] `011_risk.sql` 与 04 §3.11 逐字一致
- [ ] 数值样例误差不超过 `1e-9`
- [ ] 年化固定使用 `252`，不随窗口标签或历史年数变化
- [ ] `T < 60` 不返回任何指标数字
- [ ] 已写 `docs/wp/status/P-06.md`

## 10. 交接、风险与回退
| 对象 | 使用或风险 | 约定与回退 |
|---|---|---|
| U-07 | 使用 `risk.compute` | 单持仓和奇异矩阵显示警告，不伪造数值 |
| I-02 | 端到端验收风险页 | 演示数据至少 60 个共同交易日；否则使用不足状态 |
| D-04 | 依赖 `close/adj_close` 质量 | 任一复权价缺失就整体退回 `close`，不混用两种基线 |
| 样本门槛 | 新持仓导致样本不足 | 返回 `DATA_INSUFFICIENT`，页面不显示部分指标 |
| 条件数接近无限 | 奇异矩阵 | 输出 null 和警告；不使用巨大的伪条件数 |
| 审计结果增长 | `risk_run` 只增 | 保留用于复现；不在 MVP-0 自动清理 |

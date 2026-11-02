---
id: D-04
title: 日线行情与交易日历
phase: mvp0
platform: shared
lane: data
deps: [C-03, D-01, G1-US]
size: M
owns: [core/sentinel/markets/prices/, core/sentinel/storage/migrations/005_prices.sql, resources/calendars/, core/tests/unit/markets/prices/, core/tests/fixtures/prices/]
appends: []
stubs: []
---

# D-04 日线行情与交易日历

## 0. 一眼看懂

- **目标**：腾讯主源、纳斯达克备源拉取美股日线，校验后写入 `price_daily`；提供 2025 到 2027 年日历。完成后解锁 P-01、P-06、E-02。
- **预计规模**：6 个实现模块约 420 行，4 个测试文件约 340 行，日历 JSON 约 80 行。

## 1. 背景与边界

### 1.1 为什么需要它
持仓页要显示最新收盘，风险页要 250 个交易日，扫描页要判断“最近一个已收盘交易日”。行情源是非官方接口，字段顺序与复权语义都不直观；交易日历必须独立于网络，否则节假日会把“最新数据”算错。

### 1.2 范围内
1. `PriceSource` 与 `Bar`，签名与 [07](../../07-美股数据源.md#61-行情源适配器接口) §6.1 一致；腾讯三市场与纳斯达克解析。
2. 主备切换、OHLC 校验、非法行丢弃与计数。
3. `resources/calendars/us.json` 与 5 个日历函数。
4. `prices.refresh` 的服务方法、参数/结果模型；由 C-07 的 markets 适配器注册；返回每个标的的成功/失败明细。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 创建 `price_daily` 表 | 本包创建 `005_prices.sql`；C-03 只负责执行迁移 |
| 汇率、港股、A 股行情 | v1 / v2；本包只预留协议 |
| K 线、盘中行情、分红因子 | U-04 / 不做 / 不做 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [07-美股数据源.md](../../07-美股数据源.md#61-行情源适配器接口) | §6.1 接口 | `Bar` 与 `PriceSource` |
| [07-美股数据源.md](../../07-美股数据源.md#62-候选源2026-11-02-预探针实测) | §6.2 实测 | 行序、耗时、`$` 前缀 |
| [07-美股数据源.md](../../07-美股数据源.md#7-交易日历d-04) | §7 日历 | 休市日与函数 |
| [04-数据模型.md](../../04-数据模型.md#35-005_pricessql--d-04) | §3.5 表结构 | `price_daily` |

## 3. 前置条件

- C-03 已合并；`005_prices.sql` 由本包创建并建表。
- D-01 已合并；本包注册 `tencent` 策略：读取 30 秒、总计 30 秒。
- G1-US 已交付 `quotes_tencent_{us,hk,cn}.probe.json`、`quotes_nasdaq_us.probe.json`、`prices_250d_summary.json`。
- `tzdata` 已安装；不得引入 pandas、exchange_calendars。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/markets/prices/__init__.py` | 新建 | 导出 `Bar`、`PriceSource`、`PriceService` |
| `core/sentinel/markets/prices/models.py` | 新建 | `Bar`、`RefreshFailure`、`RefreshResult` |
| `core/sentinel/markets/prices/source.py` | 新建 | `PriceSource` 协议与 `to_tencent_symbol` |
| `core/sentinel/markets/prices/tencent.py` | 新建 | 腾讯请求与行解析 |
| `core/sentinel/markets/prices/nasdaq.py` | 新建 | 纳斯达克请求与行解析 |
| `core/sentinel/markets/prices/service.py` | 新建 | 主备切换、增量范围、校验、落库 |
| `core/sentinel/markets/prices/calendar.py` | 新建 | 5 个日历函数与 `MarketState` |
| `resources/calendars/us.json` | 新建 | 2025 到 2027 年休市与提前收盘 |
| `resources/calendars/SOURCES.md` | 新建 | 每个日期的 NYSE 来源 URL 与访问日期 |
| `core/sentinel/storage/migrations/005_prices.sql` | 新建 | 逐字复制 [04](../../04-数据模型.md) §3.5 的 `price_daily` 表与索引 |
| `core/tests/unit/markets/prices/test_{tencent,nasdaq,service,calendar}.py` | 新建 | §8.1 的测试 |

## 5. 接口规格

### 5.1 公开接口
```python
@dataclass(frozen=True)
class Bar:
    trade_date: date; open: float | None; high: float | None; low: float | None
    close: float | None; adj_close: float | None; volume: int | None

class PriceSource(Protocol):
    name: str
    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]: ...
@dataclass(frozen=True)
class RefreshFailure:
    instrument_id: str; code: str; reason: str
@dataclass(frozen=True)
class RefreshResult:
    updated: int; failed: list[RefreshFailure]; as_of: date
class MarketState: status: str; next_open_at: datetime
class TencentPriceSource:
    def __init__(self, http: HttpClient) -> None: ...
    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]: ...
class NasdaqPriceSource:
    def __init__(self, http: HttpClient) -> None: ...
    def fetch_daily(self, symbol: str, start: date, end: date) -> list[Bar]: ...
class PriceService:
    def __init__(self, db: Database, primary: PriceSource, backup: PriceSource, calendar_path: Path, clock: Callable[[], datetime]) -> None: ...
    def refresh(self, instrument_ids: Sequence[str] | None = None) -> RefreshResult: ...

def is_trading_day(d: date) -> bool: ...
def next_trading_day(d: date) -> date: ...
def prev_trading_day(d: date) -> date: ...
def session_close(d: date) -> datetime: ...
def market_state(now: datetime) -> MarketState: ...
```
`fetch_daily` 在来源失败时抛 `SourceError`；空结果返回 `[]`，由 `PriceService` 触发备源。`refresh` 对每个标的独立失败，全部失败时返回 `RefreshResult` 且 `failed` 长度等于标的数，由 RPC 层映射 `SOURCE_UNAVAILABLE`。所有公开函数线程安全。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `Bar.trade_date` | date | 是 | 美东交易日 | 日期 |
| `Bar.open/high/low/close/adj_close` | float | 否 | > 0 或 `None` | 价格；复权未确认时 `adj_close=None` |
| `RefreshFailure.instrument_id` / `code` / `reason` | str | 是 | 标的 ID；错误码；细分原因 | 单标的失败明细 |
| `MarketState.status` | str | 是 | `open`/`pre`/`after`/`closed`/`holiday` | 市场状态 |
| `MarketState.next_open_at` / `us.json.years` | datetime / list[int] | 是 | UTC；`[2025,2026,2027]` | 下一次开盘与覆盖年份 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `TENCENT_URL` | `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get` | `tencent.py` | 主源 |
| `NASDAQ_URL` | `https://api.nasdaq.com/api/quote/{symbol}/historical` | `nasdaq.py` | 备源 |
| `DEFAULT_LOOKBACK_DAYS` / `MAX_ROWS` | `1095` / `250` | `service.py` | 空库取 3 年；单次最多 250 行 |
| `CALENDAR_PATH` | `resources/calendars/us.json` | `calendar.py` | 只读资源 |
| `EASTERN` | `ZoneInfo("America/New_York")` | `calendar.py` | 交易所时区 |

## 6. 实现步骤

1. 注册 tencent 策略（读取 30 秒、总计 30 秒）；请求 `param={symbol},day,,,{limit},qfq`，`limit=min(250, 交易日数+10)`，头 `Referer: https://gu.qq.com/`。
2. 解析 `data[symbol]`：先 `qfqday` 后 `day`；每行 6 个元素，按 `[日期, 开, 收, 高, 低, 量]` 映射；`qfqday` 设 `adj_close=close`，`day` 设 `None`。
3. 腾讯代码 `us:` 换 `us`；`BRK.B` 以 G1-US `REPORT.md` 的 `symbolMapping` 为准。纳斯达克用 `assetclass=stocks`、`fromdate`、`limit=250`，日期 `%m/%d/%Y`，价格去 `$` 与逗号。
4. 主备：先腾讯；抛错或空结果时调纳斯达克；都失败记 `SOURCE_UNAVAILABLE`；成功时写实际来源名。
5. 增量范围：有库值时 `start = 最新日期 + 1 天`，否则 `as_of - 1095 天`；`end` 是最近已收盘交易日。
6. 校验与落库：非法 OHLC、价格 ≤ 0、`NaN`、`inf` 丢行；其余 upsert，单标的一个事务，`fetched_at=clock.now()`。
7. 日历：校验 `market`、时区、`years`；`04:00–09:30` 为 `pre`，`09:30–close` 为 `open`，`close–20:00` 为 `after`，周末节假日为 `holiday`。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 两源都失败 | 该标的失败 | `SOURCE_UNAVAILABLE` | `error.SOURCE_UNAVAILABLE` |
| 腾讯超时或 429 | 切纳斯达克并记录原因 | `RATE_LIMITED`（仅全失败时） | `error.RATE_LIMITED` |
| 空数组或字段缺失 | 空数组切备源；字段全丢则失败 | `SOURCE_UNAVAILABLE` | `error.SOURCE_UNAVAILABLE` |
| OHLC 非法 | 丢行并 `warn` | — | 无 |
| 日期超范围或日历超年份 | 丢弃；日历按周一至周五并 `warn` | — | 数据状态提示“交易日历只到 2027 年” |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_tencent_maps_close_before_high` | `.../test_tencent.py` | `["2026-10-30","346.72","344.63","349.19","334.35","67841555"]` | `open=346.72`、`close=344.63`、`high=349.19`、`low=334.35` |
| `test_tencent_adjustment_keys` | 同上 | `quotes_tencent_cn.probe.json`；美股 fixture | `qfqday` 时 `adj_close=close`；`day` 时全为 `None` |
| `test_tencent_empty_returns_empty` | 同上 | `data: {usAAPL: {day: []}}` | `[]` |
| `test_tencent_missing_field_and_errors` | 同上 | 5 元素行；`RATE_LIMITED`；`DECODE_FAILED` | `PRICE_SCHEMA`；原样抛出；`SOURCE_UNAVAILABLE` |
| `test_nasdaq_strips_dollar_and_parses_date` | `.../test_nasdaq.py` | `{"date":"10/30/2026","close":"$344.63"}` | `trade_date == date(2026,10,30)`、`close == 344.63` |
| `test_service_fallback_and_incremental` | `.../test_service.py` | 腾讯 `TIMEOUT`；库内最新 `2026-10-29` | `source == "nasdaq"`；`start == 2026-10-30` |
| `test_service_failure_and_invalid_ohlc` | 同上 | 两源都抛错；`high < low` | `SOURCE_UNAVAILABLE`；非法行不入库 |
| `test_calendar_holiday_is_not_trading_day` | `.../test_calendar.py` | `2026-11-26` | `False`；`market_state.status == "holiday"` |
| `test_calendar_early_close_and_dst` | 同上 | `2026-11-27`；`2026-03-09`；`2026-11-02` | `18:00Z`；`20:00Z`；`21:00Z` |
| `test_calendar_out_of_range_uses_weekday` | 同上 | `2030-01-01` 周二 | `is_trading_day` 为 `True` 并 `warn` |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `core/tests/fixtures/prices/prices_tencent_{us,hk,cn}.sample.json` | 各 30 个交易日；A 股含 `qfqday` | G1-US 录制后复制 |
| `core/tests/fixtures/prices/prices_nasdaq_us.sample.json` | 30 个交易日，含 `$` | G1-US 录制后复制 |
| `core/tests/fixtures/prices/prices_tencent_bad.json` | 5 元素行、429、非 UTF-8 三种变体 | 手写；编码变体测试内生成 |
| `core/tests/fixtures/prices/prices_invalid_ohlc.json` / `prices_synthetic.py` | 4 行含 2 行非法；确定性行情生成器 | 手写 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd "/Users/lijiaxuan/Documents/ChatGPT/JEV Stocks/core"
uv run pytest tests/unit/markets/prices -q
# 期望：10 passed，0 failed
cd .. && python3 - <<'PY'
import json
c = json.load(open("resources/calendars/us.json", encoding="utf-8"))
assert c["years"] == [2025, 2026, 2027]
assert {"2026-11-26", "2026-12-25"} <= {h["date"] for h in c["holidays"]}
assert {"2026-11-27", "2026-12-24"} <= {h["date"] for h in c["early_closes"]}
print("calendar ok")
PY
# 期望：calendar ok
```

### 9.2 完成清单
- [ ] 第 4 节 11 个文件全部创建；`005_prices.sql` 与 04 §3.5 逐字一致；10 个测试通过；`SOURCES.md` 完整；`day` 未被当作 `adj_close`；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| P-01 / P-06 | 最新两行；`close` 或 `adj_close` | P-01 只读库；缺复权时降级并警告 |
| U-04 / v2 | `Bar` 列表；`PriceSource` 协议 | 按日期升序；新市场只加适配器 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 慢请求、接口下线或复权不明 | 超时；连续失败；数值差异无法解释 | 读取上限 30 秒；用纳斯达克；`adj_close=None` |

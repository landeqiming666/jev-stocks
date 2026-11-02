---
id: D-02
title: 美股标的表与搜索
phase: mvp0
platform: shared
lane: data
deps: [C-03, D-01]
size: M
owns: [core/sentinel/markets/instruments/, core/sentinel/storage/migrations/002_instrument.sql, core/tests/unit/markets/instruments/, core/tests/fixtures/instruments/, resources/aliases/]
appends: []
stubs: []
---

# D-02 美股标的表与搜索

## 0. 一眼看懂

- **目标**：下载 SEC 标的表，按固定规则导入 `instrument` 与 `instrument_alias`，并提供 `instruments.search`；完成后解锁 P-01、P-04、D-03、D-04。
- **预计规模**：5 个实现模块约 330 行，4 个测试文件约 260 行，别名表 100 条；全部使用已批准依赖。

## 1. 背景与边界

### 1.1 为什么需要它
用户输入的是“苹果”“BRK.B”或 `AAPL`，系统内部只认 `us:AAPL`。标的表必须可离线使用、可重复导入、能把类股与中文别名正确归一，否则持仓、扫描、行情都会对错标的。

### 1.2 范围内
1. 拉取、解析、白名单过滤、代码规范化、CIK 补零、重复去重。
2. 单事务全量替换与 `is_active` 软下线。
3. 中文别名表与 `norm_query` 得分搜索，返回最多 50 条。
4. 启动刷新判定：表为空或距上次刷新超过 7 天。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 创建 `instrument` 与 `instrument_alias` 表 | C-03 执行 `002_instrument.sql` |
| 把 `instruments.search` 注册到 JSON-RPC 路由 | C-07 的 markets 适配器接线；本包只提供 `InstrumentService.search` 与参数/结果模型 |
| 港股、A 股、公司简介、模型生成别名 | v2 / 不做 / 禁止 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [07-美股数据源.md](../../07-美股数据源.md#41-来源) | §4.1 来源 | 字段顺序与 10,423 行 |
| [07-美股数据源.md](../../07-美股数据源.md#43-中文别名表) | §4.3 中文别名 | 文件格式与数量 |
| [07-美股数据源.md](../../07-美股数据源.md#44-规范化与搜索instrumentssearch) | §4.4 搜索 | 得分与排序 |
| [05-接口契约.md](../../05-接口契约.md#53-标的与持仓5) | §5.3 | 入参与返回 |

## 3. 前置条件

- C-03 已合并：`Database.read()` 返回 `SqlExecutor`，`Database.write()` 返回 `WriteTx`；迁移 `002_instrument.sql` 由本包创建。
- D-01 已合并：`HttpClient.get_json(url, source="sec")`。
- 调用方在未配置 SEC 邮箱时先抛 `CONFIG_REQUIRED`，本包不重复校验。
- `resources/aliases/us_zh.json` 已由本包创建，评审抽查 10 条。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/markets/instruments/__init__.py` | 新建 | 导出服务与模型 |
| `core/sentinel/markets/instruments/models.py` | 新建 | `TickerRow`、`Instrument`、`SearchHit`、`ImportStats` |
| `core/sentinel/markets/instruments/normalize.py` | 新建 | `normalize_symbol`、`norm_query` |
| `core/sentinel/markets/instruments/source.py` | 新建 | `SecTickerSource.fetch()` 与字段校验 |
| `core/sentinel/markets/instruments/repository.py` | 新建 | 事务导入、软下线、别名重建、查询 |
| `core/sentinel/markets/instruments/service.py` | 新建 | `InstrumentService.search()`、`ensure_fresh()` |
| `core/sentinel/storage/migrations/002_instrument.sql` | 新建 | 逐字复制 [04](../../04-数据模型.md) §3.2 的 `instrument`、`instrument_alias` 两张表与索引 |
| `resources/aliases/us_zh.json` | 新建 | 至少 100 条中文名与别名 |
| `core/tests/unit/markets/instruments/test_{normalize,source,repository,service}.py` | 新建 | §8.1 的测试 |

## 5. 接口规格

### 5.1 公开接口
```python
@dataclass(frozen=True)
class TickerRow:
    cik: str; name: str; ticker: str; exchange: str

@dataclass(frozen=True)
class Instrument:
    instrument_id: str; market: str; symbol: str; exchange: str
    name: str; name_zh: str | None; currency: str; cik: str | None; is_active: bool

@dataclass(frozen=True)
class SearchHit:
    instrument: Instrument; score: int

class ImportStats: total: int; kept: int; skipped_exchange: int; skipped_symbol: int; duplicates: int; deactivated: int

def normalize_symbol(raw: str) -> str | None: ...
def norm_query(value: str) -> str: ...

class SecTickerSource:
    def __init__(self, http: HttpClient, *, email_provider: Callable[[], str | None] | None = None) -> None: ...
    def fetch(self) -> list[TickerRow]: ...

class InstrumentRepository:
    def __init__(self, db: Database) -> None: ...
    def replace_from_sec(self, rows: Sequence[TickerRow], *, fetched_at: datetime) -> ImportStats: ...
    def search(self, query: str, *, limit: int = 20) -> list[SearchHit]: ...
    def get(self, instrument_id: str) -> Instrument | None: ...
    def last_refresh_at(self) -> datetime | None: ...

class InstrumentService:
    def __init__(self, repo: InstrumentRepository, source: SecTickerSource, clock: Callable[[], datetime]) -> None: ...
    def search(self, query: str, limit: int = 20) -> list[SearchHit]: ...
    def ensure_fresh(self, *, offline: bool, has_sec_email: bool) -> ImportStats | None: ...
```
`search` 在 `query` 规范化后为空、原串长度不在 1 到 64、`limit` 不在 1 到 50 时抛 `UserError("INVALID_ARGUMENT", field="query"|"limit")`。`SecTickerSource.fetch` 每次通过注入的 `email_provider` 获取当前联系邮箱；未配置或非法时在网络调用前抛 `CONFIG_REQUIRED`（`missing=["secEmail"]`），配置后发送 `User-Agent: Sentinel/<版本> <邮箱>`。网络失败抛 `SourceError`，字段缺失抛 `SourceError("SOURCE_UNAVAILABLE", reason="TICKER_SCHEMA")`。所有仓储方法线程安全，写操作只通过 `Database.write()`。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `Instrument.instrument_id` | str | 是 | `us:<symbol>` | 主键 |
| `Instrument.exchange` | str | 是 | `NASDAQ`/`NYSE`/`NYSE American`/`CBOE` | 规范化交易所 |
| `TickerRow.cik` / `ticker` / `exchange` | str | 是 | 10 位数字；原始代码；SEC 交易所名 | 导入前原始行 |
| `SearchHit.score` | int | 是 | 30/60/80/100/120 | 匹配得分 |
| `ImportStats` 键 | int | 是 | `total`、`kept`、`skipped_exchange`、`skipped_symbol`、`duplicates`、`deactivated` | 导入计数 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `TICKERS_URL` | `https://www.sec.gov/files/company_tickers_exchange.json` | `source.py` | 唯一来源 |
| `EXCHANGE_MAP` | `{"Nasdaq":"NASDAQ","NYSE":"NYSE","NYSE American":"NYSE American","CBOE":"CBOE"}` | `source.py` | 白名单 |
| `MAX_AGE_DAYS` / `DEFAULT_LIMIT` / `MAX_LIMIT` | `7` / `20` / `50` | `service.py` | 刷新与搜索上限 |
| `ALIAS_MIN_ENTRIES` | `100` | `resources/aliases/us_zh.json` | 评审门槛 |

## 6. 实现步骤

1. 读取 JSON，断言顶层 `fields == ["cik","name","ticker","exchange"]`；`data` 每行必须 4 个元素，否则整批失败并 `reason=TICKER_SCHEMA`。
2. source 完整保留形状合法的原始行，repository 统一过滤并计数：只保留 `EXCHANGE_MAP` 的键；其余计入 `skipped_exchange`。避免在 source 提前丢行导致 `ImportStats.total` 和跳过计数错误。
3. 代码规范化：`strip().upper()`；`-` 换 `.`；只允许 `A-Z0-9.`。重复 `symbol` 保留 `int(cik)` 最小行；CIK 用 `str(int(cik)).zfill(10)`，非数字行计入 `skipped_symbol`。
4. 中文名：读 `us_zh.json`，以 `symbol` 建映射；文件缺失或 JSON 非法时启动失败 `INTERNAL`，不静默空表。
5. 单事务：`DELETE FROM instrument_alias` 中本批 `instrument_id` 的行；`INSERT ... ON CONFLICT (market, symbol) DO UPDATE` 更新 `exchange/name/name_zh/currency/cik/is_active/source/updated_at`；把本批未出现的旧 `market='us'` 行 `is_active=FALSE`，计入 `deactivated`。
6. 别名重建：每行写入 `symbol`（kind `symbol`）、`name` 规范化（`name_en`）、`name_zh`（`name_zh`）、每个 `aliases` 项（`alias`）；同一 `(instrument_id, alias)` 只保留先出现的 kind，顺序为 `symbol`、`name_zh`、`name_en`、`alias`。
7. 搜索 SQL：`SELECT ... FROM instrument_alias a JOIN instrument i USING(instrument_id) WHERE i.is_active AND a.alias LIKE '%' || ? || '%'`；计分：精确 symbol 120、精确别名 100、前缀 symbol 80、前缀 60、包含 30；排序 `(-score, symbol)` 后截断。
8. `ensure_fresh`：`last_refresh_at` 为空或 `now - last_refresh_at > 7 天`，且 `offline=False`、`has_sec_email=True` 时刷新；否则返回 `None`。刷新失败只 `warn`，保留旧表；网络返回空列表时不覆盖已有标的，也不更新刷新水位，避免临时空响应把全市场软下线。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 查询为空/超过 64 字/`limit` 越界 | 不查库 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 标的表为空且无缓存 | 返回空列表 | — | 界面提示“填写联系邮箱后才能下载标的表” |
| 网络失败；字段缺失；重复代码 | 保留旧表；字段缺失整批拒绝；重复保留 CIK 最小行 | `SOURCE_UNAVAILABLE` / — | `error.SOURCE_UNAVAILABLE` |
| 中文别名文件损坏 | 启动失败 | `INTERNAL` | `error.INTERNAL` |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_normalize_symbol_and_query` | `.../test_normalize.py` | `" BRK-B "`、`"A B"`、`" 苹果 公司! "` | `"BRK.B"`、`None`、`"苹果公司"` |
| `test_fetch_maps_exchange_whitelist` | `.../test_source.py` | `company_tickers_exchange.sample.json` | source 保留原始交易所；repository 映射 `Nasdaq` 为 `NASDAQ`，丢弃 OTC 并计数 |
| `test_fetch_schema_and_empty` | 同上 | 删掉 `exchange`；`data: []` | `TICKER_SCHEMA`；空列表 |
| `test_fetch_rate_limit_and_decode_map` | 同上 | D-01 抛 `RATE_LIMITED`；`DECODE_FAILED` | 前者原样抛出且 `retryable`；后者 `SOURCE_UNAVAILABLE` |
| `test_import_keeps_smallest_cik_on_duplicate` | `.../test_repository.py` | 两行 `BRK-B`，CIK 1067983 与 1 | 保留 1；`duplicates == 1` |
| `test_import_deactivates_and_rolls_back` | 同上 | 三行改两行；第二行触发约束错误 | 缺失行 `is_active is False`；失败后两表保持原状 |
| `test_search_scores_exact_symbol_highest` | `.../test_service.py` | 查询 `BRK.B` | 首条 `us:BRK.B`，`score == 120` |
| `test_search_chinese_alias_and_sort` | 同上 | 查询 `苹果`；`a` 加 `limit=2` | 首条 `us:AAPL` 得 100；返回 2 条降序 |
| `test_ensure_fresh_skips_without_email` | 同上 | 表为空、`has_sec_email=False` | 返回 `None`，不调用 `fetch` |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `core/tests/fixtures/instruments/company_tickers_exchange.sample.json` | 25 条，含 `BRK-B`、OTC、重复 ticker、带空格 ticker | 从 G1-US 的探针 fixture 裁剪并构造 |
| `core/tests/fixtures/instruments/company_tickers_exchange_bad.json` | 空数据、缺字段、429 三种变体 | 手写 |
| `core/tests/fixtures/instruments/us_zh.sample.json` | 5 条别名 | 手写；生产文件另建 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd "/Users/lijiaxuan/Documents/ChatGPT/JEV Stocks/core"
uv run pytest tests/unit/markets/instruments -q
# 期望：9 passed，0 failed
cd .. && python3 - <<'PY'
import json
d = json.load(open("resources/aliases/us_zh.json", encoding="utf-8"))
assert len(d) >= 100
assert all(set(x) == {"symbol", "name_zh", "aliases"} for x in d)
print("aliases", len(d))
PY
# 期望：aliases 100 或更多
```

### 9.2 完成清单
- [ ] 第 4 节 10 个文件全部创建；`us_zh.json` 至少 100 条，抽查 10 条正确
- [ ] 第 8.1 节 9 个测试全部通过；导入失败后旧表不变；搜索不超过 300 ms
- [ ] 已写 `docs/wp/status/D-02.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| P-01 / P-04 | `repo.get`、`Instrument`、`service.search` | 持仓前校验标的；RPC 层把 `SearchHit` 转成 `Instrument[]` |
| D-03 / D-04 | `cik`、`instrument_id`、`symbol` | CIK 必须 10 位；腾讯代码由 `us:` 前缀推导 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 别名质量差或搜索慢 | 抽查错误；超过 300 ms | 人工修正别名；给 `alias` 建索引并走 CR |

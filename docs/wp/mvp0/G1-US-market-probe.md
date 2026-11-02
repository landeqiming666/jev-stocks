---
id: G1-US
title: 闸门探针：SEC、行情源实测与录制
phase: mvp0
platform: shared
lane: data
deps: [WP-00]
size: S
owns: [scripts/probe_sources.py, core/tests/unit/markets/probe/, core/tests/fixtures/markets/probe/]
appends: []
stubs: []
---

# G1-US 闸门探针：SEC、行情源实测与录制

## 0. 一眼看懂

- **目标**：在写任何生产适配器之前，用一条可重复执行的探针确认 SEC 与两个行情源的真实行为，并把裁剪后的响应录成 fixture。
- **完成后解锁**：D-03、D-04。
- **预计规模**：探针脚本约 260 行，fixture 与报告约 120 行；新增约 11 个文件。
- **闸门结论**：SEC 三端点可用；腾讯为主源；纳斯达克为美股备源；Yahoo、Stooq、东方财富本轮不可用。

## 1. 背景与边界

### 1.1 为什么需要它
2026-11-02 只做了单次人工预探针，证实了端点可达，但没有证明字段稳定、250 个交易日连续、复权语义正确、限速可承受。D-03 与 D-04 的解析器必须以录制数据为准，不能凭记忆写字段。

### 1.2 范围内
1. SEC：`submissions`、`company_tickers_exchange.json`、`browse-edgar`、一份 `-index.htm` 的状态码、字段、耗时。
2. 腾讯：`usAAPL`、`hk00700`、`sh600519` 三个市场的日线，验证行序与复权键。
3. 纳斯达克：`AAPL` 历史日线，验证 `$` 前缀与日期格式。
4. 负向对照与 250 个交易日连续性、复权语义、条款、限速的结论表。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 生产用 HTTP 重试、熔断、缓存 | D-01 |
| 修改 `docs/07-美股数据源.md` 的待核实标记 | 协调者；本包只提交报告与 fixture |
| 下载并提交完整披露或完整行情 | 不做；只保留裁剪片段 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [07-美股数据源.md](../../07-美股数据源.md#2-sec-访问规则) | §2 SEC 访问规则 | `User-Agent` 与限速 |
| [07-美股数据源.md](../../07-美股数据源.md#41-来源) | §4.1 标的表来源 | 字段顺序 |
| [07-美股数据源.md](../../07-美股数据源.md#51-列出披露) | §5.1 列出披露 | `submissions` 字段 |
| [07-美股数据源.md](../../07-美股数据源.md#62-候选源2026-11-02-预探针实测) | §6.2 候选源实测 | 预探针数值 |

## 3. 前置条件

- WP-00 已合并，`httpx` 已安装在 `core/.venv`。
- 环境变量 `SENTINEL_SEC_CONTACT` 必须是真实可联系邮箱；未设置时脚本以退出码 2 结束，不发请求。
- `SENTINEL_OFFLINE` 未设置或为 `0`。
- 允许访问 `data.sec.gov`、`www.sec.gov`、`web.ifzq.gtimg.cn`、`api.nasdaq.com`。
- 探针不得读取任何 Jev 密钥。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `scripts/probe_sources.py` | 新建 | 命令行探针：发请求、校验、裁剪、写报告 |
| `core/tests/unit/markets/probe/test_probe_sources.py` | 新建 | 用录制数据测试解析与退出码，不联网 |
| `core/tests/fixtures/markets/probe/REPORT.md` | 生成 | 本轮结论表与仍待确认项 |
| `core/tests/fixtures/markets/probe/company_tickers_exchange.probe.json` | 生成 | 裁剪到 25 条，含 `BRK-B`、OTC、重复 ticker、带空格 ticker |
| `core/tests/fixtures/markets/probe/submissions_0000320193.probe.json` | 生成 | Apple 的 `filings.recent` 裁剪到 15 条 |
| `core/tests/fixtures/markets/probe/quotes_{tencent_us,tencent_hk,tencent_cn,nasdaq_us}.probe.json` | 生成 | 每个来源 30 个交易日 |
| `core/tests/fixtures/markets/probe/filing_index_8k_ex99.probe.html` | 生成 | 含 `EX-99.1` 的 8-K 索引页 |
| `core/tests/fixtures/markets/probe/prices_250d_summary.json` | 生成 | 5 个代码的连续性统计，不含完整行情 |
| `core/tests/fixtures/markets/probe/negative_sources.json` | 生成 | 三个不可用源的 URL、状态码、内容类型、前 200 字符摘要 |

## 5. 接口规格

### 5.1 公开接口
```python
@dataclass(frozen=True)
class ProbeCheck:
    name: str                 # 如 "sec.submissions"
    status: str               # "pass" | "warn" | "fail"
    required: bool
    http_status: int | None
    elapsed_ms: int | None
    detail: str               # 单行英文，不含响应正文
    values: dict[str, object] # 具体数值，写入 REPORT

def probe_sec(contact: str, client: httpx.Client) -> list[ProbeCheck]: ...
def probe_tencent(client: httpx.Client) -> list[ProbeCheck]: ...
def probe_nasdaq(client: httpx.Client) -> list[ProbeCheck]: ...
def probe_negative(client: httpx.Client) -> list[ProbeCheck]: ...
def probe_continuity(frames: dict[str, list[list[str]]]) -> list[ProbeCheck]: ...
def write_fixtures(out: Path, results: list[ProbeCheck], payloads: dict[str, object]) -> None: ...
def main(argv: list[str] | None = None) -> int: ...
```
`main` 参数：`--out PATH`（默认 `core/tests/fixtures/markets/probe`）、`--contact`、`--symbols`（默认 `AAPL,MSFT,BRK.B,NVDA,KO`）、`--days`（默认 250）、`--timeout`（默认 30）、`--offline-fixtures PATH`（只跑解析，不发请求）。

退出码：`0` 所有 `required=True` 的检查为 `pass` 或 `warn`；`1` 任一必需检查为 `fail`；`2` 参数错误或缺少联系邮箱。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `ProbeCheck.values` | dict | 是 | 可 JSON 序列化 | 供报告与测试断言的数字 |
| `prices_250d_summary.json` | dict | 是 | 键 `symbol`、`rows`、`firstDate`、`lastDate`、`gaps`、`hasAdjClose` | 每个代码的连续性统计 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `SEC_UA` | `f"SentinelProbe/0.1 (contact: {contact})"` | 脚本 | SEC 要求的请求头 |
| `SUBMISSIONS_URL` | `https://data.sec.gov/submissions/CIK0000320193.json` | 脚本 | Apple 样例 |
| `TICKERS_URL` | `https://www.sec.gov/files/company_tickers_exchange.json` | 脚本 | 标的表 |
| `BROWSE_URL` | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=8-K&dateb=&owner=include&count=10` | 脚本 | 列表页 |
| `TENCENT_URL` | `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{limit},qfq` | 脚本 | 日线 |
| `NASDAQ_URL` | `https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass=stocks&fromdate={fromdate}&limit={limit}` | 脚本 | 备源 |
| `EXPECTED_TICKER_ROWS` | `10423` | 脚本 | 2026-11-02 实测行数，偏离只 `warn` |

## 6. 实现步骤

1. 校验 `--contact` 含 `@` 且不含空白；否则打印用法到 stderr，返回 2。
2. 建 `httpx.Client(timeout=httpx.Timeout(connect=5.0, read=float(args.timeout), write=10.0, pool=5.0), follow_redirects=True)`。
3. SEC：元数据请求都带 `User-Agent: SEC_UA` 与 `Accept-Encoding: gzip, deflate`；`submissions` 断言四个键存在，`acceptanceDateTime` 必须匹配 `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$`。
4. 标的表：解析 `fields` 与 `data`，断言 `fields == ["cik","name","ticker","exchange"]`；行数不等于 10423 时 `warn`，不失败。
5. 腾讯：三个市场各请求 3 次，间隔 1 秒，记录中位数；预探针对照值为美股 1.4 秒、港股 11.0 秒、A 股 5.4 秒，超过 3 秒只 `warn`。解析 `qfqday` 优先、`day` 次之；每行 6 个字段，索引 1 是开、2 是收、3 是高、4 是低；`qfqday` 为前复权，`day` 的复权语义见 `TODO-VERIFY(G1-US)`。
6. 纳斯达克：请求 `limit=30`，断言 `data.tradesTable.rows` 非空；`close`、`open`、`high`、`low` 以 `$` 开头时去掉后再 `float()`；日期用 `%m/%d/%Y` 解析。
7. 连续性：5 个代码各请求 `--days` 行，统计行数、首尾日期、超过 4 个自然日的间隔；`rows < 250` 记 `fail`，`gaps > 0` 记 `warn`。250 日连续性、复权语义、条款、限速本轮未验证，必须由本包完成；未完成项写 `TODO-VERIFY(G1-US)`，不得声称已验证。
8. 负向对照：Yahoo `query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1mo&interval=1d`、Stooq CSV、东方财富 `push2his`；只记录状态码与内容类型，不判定通过。
9. 写 fixture：标的表保留前 25 条并强制包含 `BRK-B`、一个 `OTC`、一个重复 `ticker`、一个带空格 `ticker`；`submissions` 保留 15 条并包含 8-K、8-K/A、10-Q 各 1 条；行情各保留 30 行。
10. 写 `REPORT.md`：表格列为检查项、必需、状态、HTTP、耗时、关键数值、结论；末尾固定列出四个 `TODO-VERIFY(G1-US)` 的当前结论。

## 7. 错误与边界情况

| 情形 | 行为 | 退出码 | 报告写法 |
|---|---|---|---|
| 缺少联系邮箱 | 不发请求 | 2 | 不写文件 |
| SEC 403 | 必需检查 `fail` | 1 | `SEC_FORBIDDEN`，提示核对 `User-Agent` |
| SEC 429 | 必需检查 `warn`，记录 `Retry-After` | 0 | 不重试超过 2 次 |
| 字段缺失 | 必需检查 `fail` | 1 | 写明缺失键名 |
| 腾讯 `code != 0` | 必需检查 `fail` | 1 | 记录 `code` 与 `msg` |
| 负向源可用 | `warn` | 0 | 说明预探针结论需更新 |
| 超时 | 必需检查 `fail` | 1 | 记录超时秒数 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_sec_acceptance_datetime_regex` | `core/tests/unit/markets/probe/test_probe_sources.py` | `"2026-07-30T20:30:28.000Z"` | 匹配；`"2026-07-30 20:30:28"` 不匹配 |
| `test_tencent_maps_close_before_high` | 同上 | `["2026-10-30","346.72","344.63","349.19","334.35","67841555"]` | `open=346.72`、`close=344.63`、`high=349.19`、`low=334.35` |
| `test_tencent_prefers_qfqday_key` | 同上 | `{"qfqday":[...],"day":[...]}` | 读取 `qfqday`，`values.key == "qfqday"` |
| `test_nasdaq_strips_dollar_prefix` | 同上 | `{"close":"$344.63","open":"$345.10"}` | `344.63`、`345.10` |
| `test_missing_submissions_field_fails` | 同上 | 删除 `acceptanceDateTime`；另一份非 UTF-8 字节 | 状态 `fail`；`detail` 分别含字段名与 `Content-Type` |
| `test_rate_limit_is_warn_not_fail` | 同上 | 429 加 `Retry-After: 2` | 状态 `warn`，`values.retryAfter == "2"` |
| `test_empty_ticker_rows_is_fail` | 同上 | `{"fields":[...],"data":[]}` | 状态 `fail` |
| `test_offline_fixture_mode_does_not_use_network` | 同上 | `--offline-fixtures <dir>` 加禁止网络的 transport | 退出码 0，`REPORT.md` 生成 |
| `test_missing_contact_exits_2` | 同上 | `--contact ""` | 退出码 2 |
| `test_continuity_counts_four_day_gap` | 同上 | 日期 `2026-01-02` 与 `2026-01-07` | `gaps == 1` |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `.../company_tickers_exchange.probe.json` | SEC 真实响应裁剪 25 条 | 脚本从 `TICKERS_URL` 下载后裁剪 |
| `.../submissions_0000320193.probe.json` | Apple `filings.recent` 裁剪 15 条 | 脚本从 `SUBMISSIONS_URL` 下载后裁剪 |
| `.../quotes_*_us.probe.json` | 腾讯与纳斯达克各 30 个交易日 | 脚本下载后裁剪 |
| `.../filing_index_8k_ex99.probe.html` | 真实 8-K 索引页裁剪到 10 KB | 脚本下载后裁剪 |
| `.../negative_sources.json` | 三个不可用源摘要 | 脚本现场请求后写入 |
| `.../prices_250d_summary.json` | 5 个代码的统计 | 脚本现场请求后写入 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd "/Users/lijiaxuan/Documents/ChatGPT/JEV Stocks"
SENTINEL_SEC_CONTACT="name@example.com" uv run --project core python scripts/probe_sources.py --out core/tests/fixtures/markets/probe --days 250
# 期望：exit=0；末行 "required 6 passed, 0 failed"；REPORT.md 中 sec.submissions 的 http=200
cd core && uv run pytest tests/unit/markets/probe -q
# 期望：10 passed，0 failed
cd .. && python3 scripts/check_docs.py --strict
# 期望：错误 0
```

### 9.2 完成清单
- [ ] 第 4 节全部交付物存在
- [ ] `REPORT.md` 写明 10,423 行、三端点 200、三市场耗时、`qfqday/day` 差异
- [ ] 250 日连续性、复权语义、条款、限速四项都有结论或 `TODO-VERIFY(G1-US)`
- [ ] 第 8.1 节 10 个测试全部通过
- [ ] 未修改 `docs/01` 到 `docs/10`、`backlog.json`、`design/`
- [ ] 已写 `docs/wp/status/G1-US.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| D-03 | `submissions_...json`、`filing_index_8k_ex99.probe.html`、`REPORT.md` | 字段名与时间格式以录制数据为准 |
| D-04 | `quotes_tencent_*.probe.json`、`quotes_nasdaq_us.probe.json`、`prices_250d_summary.json` | 行序固定为日期、开、收、高、低、量 |
| 协调者 | `REPORT.md` | 合并后统一改写 `docs/07` 的 `TODO-VERIFY` 标记 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 行数随时间变化 | 不等于 10423 | 只 `warn`；断言字段形状，不断言绝对行数 |
| 250 日请求超时 | 单次超过 30 秒 | 降低 `--days` 到 120，报告标 `TODO-VERIFY(G1-US)` |

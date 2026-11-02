---
id: D-03
title: SEC 披露抓取与正文提取
phase: mvp0
platform: shared
lane: data
deps: [C-03, D-01, G1-US]
size: M
owns: [core/sentinel/markets/sec/, core/sentinel/storage/migrations/004_filings.sql, core/tests/unit/markets/sec/, core/tests/fixtures/sec/]
appends: []
stubs: []
---

# D-03 SEC 披露抓取与正文提取

## 0. 一眼看懂

- **目标**：按标的水位线列出 8-K、8-K/A、6-K，选择主文档与最多 3 个 `EX-99.*`，把 HTML 清洗成纯文本并写入 `event_doc` 与 `event_file`。
- **完成后解锁**：P-02 扫描编排、S-05 判定流水线。
- **预计规模**：6 个实现模块约 430 行，5 个测试文件约 360 行；不新增依赖。
- **边界**：本包不切段落也不写 `event_passage`；P-02 在扫描编排中调用 S-01 后写入。

## 1. 背景与边界

### 1.1 为什么需要它
SEC 的 `submissions` 只给元数据，新闻稿在 `EX-99.1` 里，主文档常常只有几行。如果只抓主文档，判定会漏掉真正的内容；如果抓全部附件，成本与噪声都不可控。本包把“抓哪些、怎么清洗、失败怎么标”固定下来。

### 1.2 范围内
1. `submissions` 解析、表单与时间窗口过滤、`event_id` 生成。
2. `-index.htm` 解析：主文档加最多 3 个 `EX-99.*`。
3. `html_to_text`：删脚本样式、块级换行、表格分隔、XBRL、200,000 字符上限。
4. 标题生成、写入两张表、已存在 `full_text` 时跳过。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 建表、切段落、判定 | C-03、S-01、S-05 |
| 扫描水位线与运行状态机 | P-02 |
| 10-Q、10-K、20-F、Form 4 | v1 |
| PDF 附件正文 | 不做；记为 `skipped` |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [07-美股数据源.md](../../07-美股数据源.md#51-列出披露) | §5.1 列出披露 | 字段与 URL 规则 |
| [07-美股数据源.md](../../07-美股数据源.md#52-找附件) | §5.2 附件选择 | `EX-99` 上限 |
| [07-美股数据源.md](../../07-美股数据源.md#54-标题) | §5.4 标题 | Item 名称表 |
| [04-数据模型.md](../../04-数据模型.md#34-004_filingssql--d-03) | §3.4 表结构 | 列与状态 |

## 3. 前置条件

- C-03 已合并；`004_filings.sql` 由本包创建并建表。
- D-01 已合并，`get_text` 对 SEC 403 会熔断，429 映射 `RATE_LIMITED`。
- G1-US 已交付 `submissions_0000320193.probe.json` 与 `filing_index_8k_ex99.sample.html`。
- selectolax 已安装；不得引入 BeautifulSoup。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/markets/sec/__init__.py` | 新建 | 导出服务与模型 |
| `core/sentinel/markets/sec/models.py` | 新建 | `FilingRef`、`IndexRow`、`EventFileDraft`、`FetchedEvent` |
| `core/sentinel/markets/sec/submissions.py` | 新建 | `parse_submissions` |
| `core/sentinel/markets/sec/index.py` | 新建 | `parse_index`、`select_files` |
| `core/sentinel/markets/sec/extract.py` | 新建 | `html_to_text` |
| `core/sentinel/markets/sec/title.py` | 新建 | `build_title` 与 16 个 Item 名称 |
| `core/sentinel/markets/sec/client.py` | 新建 | `SecFilingsClient`：列披露、抓文件、拼 URL |
| `core/sentinel/markets/sec/repository.py` | 新建 | 写 `event_doc`、`event_file` |
| `core/sentinel/markets/sec/service.py` | 新建 | `fetch_for_instrument` 编排 |
| `core/sentinel/storage/migrations/004_filings.sql` | 新建 | 逐字复制 [04](../../04-数据模型.md) §3.4 的 `event_doc`、`event_file`、`event_passage` 三张表 |
| `core/tests/unit/markets/sec/test_{submissions,index,extract,title,service}.py` | 新建 | §8.1 的测试 |

## 5. 接口规格

### 5.1 公开接口
```python
@dataclass(frozen=True)
class FilingRef:
    event_id: str; instrument_id: str; cik: str; accession: str; form_type: str
    published_at: datetime; filing_date: date; items: str | None
    primary_document: str; primary_doc_description: str | None
@dataclass(frozen=True)
class IndexRow:
    seq: int; description: str; file_name: str; doc_type: str; url: str
@dataclass(frozen=True)
class EventFileDraft:
    seq: int; file_name: str; doc_type: str; url: str
    text_status: str; text: str | None; char_count: int | None
class FetchedEvent: event: FilingRef; files: list[EventFileDraft]; content_status: str

def parse_submissions(payload: Mapping[str, object], *, instrument_id: str, cik: str, since: datetime, until: datetime, fetched_at: datetime) -> list[FilingRef]: ...
def parse_index(html: str, *, base_url: str) -> list[IndexRow]: ...
def select_files(rows: Sequence[IndexRow], *, cik: str, accession: str, primary_document: str) -> tuple[list[IndexRow], list[IndexRow]]: ...
def html_to_text(html: str) -> str: ...
def build_title(*, form_type: str, items: str | None, primary_doc_description: str | None, first_line: str | None) -> str: ...

class SecFilingsClient:
    def __init__(self, http: HttpClient) -> None: ...
    def list_filings(self, instrument: Instrument, since: datetime, until: datetime, fetched_at: datetime) -> list[FilingRef]: ...
    def fetch_file(self, url: str) -> str: ...
    def fetch_index(self, ref: FilingRef) -> list[IndexRow]: ...

class SecFilingsRepository:
    def __init__(self, db: Database) -> None: ...
    def upsert(self, event: FetchedEvent) -> None: ...
class SecFilingsService:
    def __init__(self, client: SecFilingsClient, repo: SecFilingsRepository, clock: Callable[[], datetime]) -> None: ...
    def fetch_for_instrument(self, instrument: Instrument, *, since: datetime, until: datetime) -> list[FetchedEvent]: ...
```
`parse_submissions` 对缺少 `filings.recent` 或数组长度不一致抛 `SourceError("SOURCE_UNAVAILABLE", reason="SEC_SCHEMA")`；`parse_index` 在找不到表格时返回 `[]`，由调用方退回主文档；`fetch_for_instrument` 对窗口内每个披露返回**按 `published_at` 升序的事件列表**：已入库且 `content_status` 为 `full_text`/`title_only` 的事件直接复用已存正文（不重复下载），其余抓取并抽取正文；每个事件在自己的事务中 upsert `event_doc`/`event_file`。这样 P-02 可以在重试时为已有事件补 `event_passage`。`submissions` 失败时原样抛错，调用方 P-02 把该标的记为失败且不推进水位线。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `FilingRef.event_id` | str | 是 | `us:<accession>` | 主键 |
| `FilingRef.published_at` / `form_type` | datetime / str | 是 | UTC 且不晚于 `fetched_at`；`8-K`/`8-K/A`/`6-K` | 发布时间与表单 |
| `IndexRow.seq` / `file_name` / `doc_type` | int / str / str | 是 | `0..999`；文件名非空；如 `EX-99.1` | 索引行 |
| `EventFileDraft.text_status` / `FetchedEvent.content_status` | str | 是 | `extracted/empty/failed/skipped`；`full_text/title_only/fetch_failed` | 文件与事件状态 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `FORMS` / `MAX_EX99` | `{"8-K","8-K/A","6-K"}` / `3` | `submissions.py` / `index.py` | 允许表单与附件上限 |
| `MAX_TEXT_CHARS` / `TITLE_MAX_CHARS` | `200000` / `120` | `extract.py` / `title.py` | 正文与标题上限 |
| `ARCHIVE_BASE` | `https://www.sec.gov/Archives/edgar/data` | `client.py` | 文件根地址 |
| `ITEM_NAMES` | 16 个键值对 | `title.py` | 见 07 §5.4 |

## 6. 实现步骤

1. `parse_submissions`：读取 `filings.recent` 的 16 个等长数组并取 7 个字段；长度不一致抛 `SEC_SCHEMA`。时间用 `datetime.fromisoformat` 转 UTC，晚于 `fetched_at` 则截断，只保留 `since < published_at <= until`。
2. 过滤：`form in FORMS`；`event_id = "us:" + accessionNumber`；`filing_date = date.fromisoformat(filingDate)`；`items` 为空串时存 `None`。
3. 索引 URL：`{ARCHIVE_BASE}/{int(cik)}/{accession.replace("-","")}/{accession}-index.htm`；主文档 URL：`{ARCHIVE_BASE}/{int(cik)}/{accession.replace("-","")}/{primaryDocument}`。
4. `parse_index`：用 selectolax 找第一个表头含 `Seq`、`Description`、`Document`、`Type` 的表格；跳过 `colspan` 行与表头；`seq` 转整数失败则跳过并 `warn`；链接地址用 `urljoin(base_url, href)`。
5. `select_files`：主文档合成 `seq=0` 的 `IndexRow`；索引中同文件名也强制为 `seq=0`；取 `EX-99` 前 3 个，其余作为 `skipped` 返回。
6. `html_to_text`：解析失败或空输入返回 `""`；删除 `script/style/head/noscript` 与注释；`p/div/br/li/tr/h1-h6/table/section` 前后加 `\n`；`td/th` 之间加 `" | "`；`ix:*` 只保留文本；`get_text` 后用 NFC 归一、删控制字符、`\xa0` 变空格、连续空白折叠；截到 200,000 字符并 `warn`。
7. 标题：8-K 拆分 `items` 查 `ITEM_NAMES`，未知写 `Item {编号}`，用 `"；"` 连接加 `"8-K: "`；6-K 取首个 `EX-99.1` 的首个非空行，截 120 字符。
8. 状态：全部为空 → `title_only`；至少一个非空 → `full_text`；网络异常且无可写文件 → `fetch_failed`；`skipped` 文件也写入。
9. 一个事务内 upsert `event_doc`，按 `event_id` 重写 `event_file`；已有 `full_text` 的事件直接跳过。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| `submissions` 403/429 或字段缺失 | 原样抛错；字段缺失该标的失败 | `SOURCE_UNAVAILABLE` / `RATE_LIMITED` | `error.SOURCE_UNAVAILABLE` / `error.RATE_LIMITED` |
| 索引页结构变化 | 只用主文档并 `warn` | — | 卡片标注“仅主文档” |
| 附件下载失败 | 该文件 `failed`；其他文件继续 | `SOURCE_UNAVAILABLE` | 批次显示原因与“重试” |
| 文本超 200,000 字符或已存在 `full_text` | 截断；已有全文则跳过抓取 | — | 无 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_parse_submissions_filters_forms_and_window` | `.../test_submissions.py` | 15 条样例；空 `recent` | 只保留三类表单；空数组返回 `[]` |
| `test_parse_submissions_parses_acceptance_utc` | 同上 | `"2026-07-30T20:30:28.000Z"` | `published_at == 2026-07-30T20:30:28Z` |
| `test_parse_submissions_clamps_and_rejects_schema` | 同上 | 未来时间；删除 `form` 数组 | 时间截到 `fetched_at`；`SEC_SCHEMA` |
| `test_parse_index_and_cap_ex99` | `.../test_index.py` | 真实索引；5 个 `EX-99.*` | 至少 1 行 `EX-99.1`；选中 3 个，其余 2 个 `skipped` |
| `test_select_files_skips_and_empty_index` | 同上 | `EX-101.INS`、PDF；无表格页面 | 两项 `skipped`；`parse_index` 返回 `[]` |
| `test_html_to_text_removes_scripts_and_keeps_table` | `.../test_extract.py` | 含脚本、样式、两行两列表格；空串 | 不含 `alert`/CSS；含 `A \| B`；空串返回 `""` |
| `test_html_to_text_xbrl_and_truncation` | 同上 | `ix:nonfraction>42`；250,000 个 `a` | 含 `42` 不含 `ix:`；长度 200000 |
| `test_build_title_8k_uses_item_names` | `.../test_title.py` | `items="2.02,9.01"` | `"8-K: Results of Operations and Financial Condition；Financial Statements and Exhibits"` |
| `test_build_title_unknown_and_6k_truncate` | 同上 | `items="99.99"`；200 字符首行 | 含 `"Item 99.99"`；长度 ≤ 125 且以 `"6-K: "` 开头 |
| `test_service_writes_title_only_when_all_empty` | `.../test_service.py` | 两份空 HTML | `content_status == "title_only"`；`event_file` 两行 `empty` |
| `test_service_skips_existing_full_text` | 同上 | 库里已有 `full_text` | 不调用 `fetch_file` |
| `test_service_maps_rate_limit_and_decode` | 同上 | D-01 抛 `RATE_LIMITED`；`DECODE_FAILED` | 前者原样抛；后者 `SOURCE_UNAVAILABLE` |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `core/tests/fixtures/sec/submissions_0000320193.sample.json` | G1-US 录制，裁剪 15 条 | 从 `markets/probe` 复制 |
| `core/tests/fixtures/sec/filing_index_8k_ex99.sample.html` | 一份含 `EX-99.1` 的 8-K 索引页 | G1-US 录制后裁剪到 10 KB |
| `core/tests/fixtures/sec/filing_{8k_main,ex99_press_release,6k_main,inline_xbrl}.sample.html` | 主文档、新闻稿、6-K 封面、含 `ix:` 标签 | G1-US 录制后裁剪或构造 |
| `core/tests/fixtures/sec/error_{403,429,503}.*` | 403、429 加 `Retry-After: 2`、503 | 手写 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd "/Users/lijiaxuan/Documents/ChatGPT/JEV Stocks/core"
uv run pytest tests/unit/markets/sec -q
# 期望：12 passed，0 failed
uv run mypy sentinel/markets/sec
# 期望：Success: no issues found
```

### 9.2 完成清单
- [ ] 第 4 节 11 个文件全部创建；`004_filings.sql` 与 04 §3.4 逐字一致；12 个测试通过；附件最多 3 个；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| S-01 | `event_file.text`、`event_doc.title` | 空文本事件只生成 `file_seq=-1` 的标题段落 |
| S-05 / P-02 / P-03 | `event_id`、时间、表单、URL、标题 | 只处理两类状态；失败不推进水位线；外链只允许 https |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| `EX-99` 过大或出现新表单 | 超过 200,000 字符；出现 `8-K12B` | 截断告警；本轮忽略新表单 |

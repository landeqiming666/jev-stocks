---
id: P-02
title: 扫描编排：水位线、批次、进度、取消
phase: mvp0
platform: shared
lane: semantic
deps: [P-01, D-03, S-01, S-05, C-04]
size: M
owns: [core/sentinel/scan/orchestrator.py, core/sentinel/scan/watermark.py, core/sentinel/scan/passages.py, core/sentinel/storage/migrations/008_scan.sql, core/tests/unit/scan/test_orchestrator.py, core/tests/unit/scan/test_watermark.py]
appends: []
stubs: []
---
# P-02 扫描编排：水位线、批次、进度、取消

## 0. 一眼看懂
- **目标**：把“可扫描标的与有效逻辑”变成一组可恢复、可取消、可重试的披露批次，并维护运行、水位线与统计。
- **完成后解锁**：P-03 可以读取判定形成清单，U-04 可以展示扫描进度与历史。
- **预计规模**：实现约 480 行，测试约 300 行；2 个实现文件、2 个测试文件。

## 1. 背景与边界
### 1.1 为什么需要它
抓取、模型调用和数据库写入的失败模式不同。编排层负责把网络工作与短事务隔开，保证重复扫描不重复计费、用户取消后不继续调度、进程崩溃后不会把半次运行伪装成成功。
### 1.2 范围内
1. 计算扫描窗口：首次回看、水位线、显式 `from`、30 天硬下限、启动后补跑 72 小时窗口。
2. `scan.start` 异步启动、同市场互斥、批次创建和进度通知。
3. 启动时把遗留 `running` 标记为 `interrupted`。
4. 逐批提交、失败隔离、预算耗尽挂起、终态计算。
5. 调用 S-01 分段，把 `event_passage` 幂等落库（D-03 不做分段）。
6. `scan.cancel`、`scan.status`、`scan.history`、`scan.detail`、`scan.retryBatch`。
7. 水位线只在披露列表完整获取后单调推进。
### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 抓取与解析 SEC 披露 | D-03 |
| 缓存判定、调用引擎、选择代表判定 | S-05 |
| 预算计数与通知节流 | C-04、S-02 |
| 待处理清单分页与处理动作 | P-03 |
| 其他迁移文件 | 各自工作包；本包创建 `008_scan.sql`，不改其他编号 |
| 定时器、托盘、唤醒补跑 | v1 调度工作包；本包只提供同一窗口函数 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | §2 术语、§3.1 ID、§4 时间 | UTC、ULID、运行与水位线定义 |
| [04-数据模型.md](../../04-数据模型.md) | §3.8 `008_scan.sql`、§7 完整性、§8.4 | 表结构、可扫描标的查询 |
| [05-接口契约.md](../../05-接口契约.md) | §3 错误、§4 `ScanRun`/`ScanBatch`、§5.6、§6 通知、§7.1、§7.2、§8 | RPC 与状态机 |
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | §7 分批、预算、费用 | 一批的定义与预算行为 |
| [02-技术架构.md](../../02-技术架构.md) | §7.2 取消、§7.3 数据库访问、§8 崩溃恢复 | 线程与事务边界 |
| [decisions.md](../../decisions.md) | ADR-007、ADR-012 | MVP-0 手动扫描；水位线语义 |

## 3. 前置条件
- P-01 提供 `list_scannable_instruments() -> list[str]`、`count_holdings()`、`list_active_theses(instrument_id) -> list[ThesisView]`。
- D-03 提供 `fetch_for_instrument(instrument, since, until) -> list[FetchedEvent]`；列表返回成功表示窗口内披露列表完整。
- S-01 提供 `split_passages(text, *, max_chars=1200) -> list[TextSpan]`；P-02 负责把结果写入 `event_passage`，S-01 不碰数据库。
- S-05 提供 `DecisionPipeline.process_batch(ctx, theses, passages, cancel) -> BatchOutcome`；`BatchOutcome` 含新判定数、缓存命中数、token 与证据失败数。
- C-04 提供设置读取、`emit("scan.progress", payload)`、`emit("scan.finished", run)`、`emit("inbox.updated", payload)`。
- C-01 提供独立 worker 线程和 `CancelToken`；`scan.start` 在创建运行后立即返回。
- 若 `008_scan.sql` 不存在，实现者停止并提 CR，不得在 Python 中内联建表。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/scan/watermark.py` | 新建 | `compute_window`、`read_watermark`、`advance_watermark` |
| `core/sentinel/scan/orchestrator.py` | 新建 | `ScanService`、批次调度、状态机、5 个 RPC handler、启动恢复 |
| `core/sentinel/scan/passages.py` | 新建 | `persist_passages()`：调用 S-01、幂等写 `event_passage`、返回 `PassageRecord` |
| `core/sentinel/storage/migrations/008_scan.sql` | 新建 | 逐字复制 [04](../../04-数据模型.md) §3.8 的 `scan_run`、`scan_batch`、`watermark` |
| `core/tests/unit/scan/test_watermark.py` | 新建 | 窗口计算与单调推进测试 |
| `core/tests/unit/scan/test_orchestrator.py` | 新建 | 异步运行、终态、取消、恢复、重试测试 |

## 5. 接口规格
### 5.1 公开接口
```python
@dataclass(frozen=True)
class ScanWindow:
    start: datetime
    end: datetime
    used_startup_catch_up: bool
def compute_window(*, now: datetime, watermark: datetime | None,
                   first_lookback_days: int, explicit_from: datetime | None) -> ScanWindow: ...
def read_watermark(db: Database, market: str) -> datetime | None: ...
def advance_watermark(db: Database, market: str, covered_until: datetime) -> datetime: ...
def persist_passages(db: Database, event: FetchedEvent) -> list[PassageRecord]: ...
class ScanService:
    def recover_on_startup(self) -> int: ...
    def start(self, market: str, requested_from: datetime | None) -> str: ...
    def cancel(self, run_id: str) -> None: ...
    def status(self, run_id: str) -> ScanRunView: ...
    def history(self, limit: int, cursor: str | None) -> ScanHistoryPage: ...
    def detail(self, run_id: str) -> ScanDetailView: ...
    def retry_batch(self, batch_id: str) -> ScanBatchView: ...
def register_handlers(registrar: HandlerRegistrar, service: ScanService) -> None: ...
```
- `start` 在事务内插入 `queued` 运行并返回 ULID；worker 随后把状态改为 `running`。
- `cancel` 对非终态运行置取消标记并立即返回；对终态运行是空操作。
- `history` 按 `created_at DESC, run_id DESC`，`limit` 默认 50、最大 200；cursor 为 `base64url(created_at|run_id)`。
- `retry_batch` 同步执行，单次上限 60 秒；只接受 `failed` 批次，其他状态抛 `CONFLICT`。
- 所有 `datetime` 入参必须带时区并归一化为 UTC；数据库读出后立即补 `tzinfo=UTC`。
### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `FilingRef` | `eventId` | str | 是 | `us:<accession>` | 披露 |
| | `instrumentId` | str | 是 | 已扫描标的 | 关联标的 |
| | `publishedAt` | datetime | 是 | UTC | 事件时间 |
| `BatchOutcome`（来自 S-05） | `new_decisions` | int | 是 | ≥ 0 | 新写判定数 |
| | `cached_decisions` | int | 是 | ≥ 0 | 缓存命中数 |
| | `input_tokens` / `estimated_tokens` | int | 是 | ≥ 0 | 判定与证据请求的 token |
| | `evidence_failures` / `truncated_passages` | int / bool | 是 | ≥ 0 | 证据失败与截断标记 |
| `RunCounters` | `instruments` | int | 是 | ≥ 0 | 实际扫描标的 |
| | `skippedNoThesis` | int | 是 | ≥ 0 | 无有效逻辑 |
| | `filings` / `passages` / `decisions` | int | 是 | ≥ 0 | 累计统计 |
`ScanRunView`、`ScanBatchView`、`ScanHistoryPage` 的字段直接复用 [05-接口契约.md](../../05-接口契约.md) §4 与 `contracts/`，本包不得另造同名字段。
### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `STARTUP_CATCH_UP_HOURS` | `72` | `watermark.py` | 启动后首次补跑最多覆盖最近 72 小时 |
| `MAX_EXPLICIT_LOOKBACK_DAYS` | `30` | `watermark.py` | `from` 不得早于 30 天前 |
| `PROGRESS_MIN_INTERVAL_MS` | `500` | `orchestrator.py` | `scan.progress` 节流 |
| `RETRY_TIMEOUT_SECONDS` | `60` | `orchestrator.py` | 单批重试上限 |
| `DEFAULT_HISTORY_LIMIT` / `MAX_HISTORY_LIMIT` | `50` / `200` | `orchestrator.py` | 历史分页 |

## 6. 实现步骤
1. **窗口**：`end = now`；硬下限 `floor = end - 30 days`。有显式 `from` 时 `start = max(from, floor)`。无显式值时，`base = watermark`；没有水位线用 `end - first_lookback_days`。`start = max(base, end - 72 hours)`，并令 `used_startup_catch_up = watermark is not None and start > watermark`。
2. **水位线推进**：`advance_watermark` 写 `max(旧值, covered_until)`，禁止回退；只在 D-03 完整返回窗口列表后调用。披露抓取失败时水位线不变。
3. **启动恢复**：`recover_on_startup` 在一个事务内把全部 `running` 改为 `interrupted`、设置 `finished_at = clock.now()`，返回修改行数。MVP-0 不自动调用模型；用户下一次点扫描时由第 1 步补跑 72 小时窗口。
4. **开始运行**：事务内检查同市场是否存在 `queued/running`；存在则 `CONFLICT`。读取设置，缺 Jev 密钥或 SEC 邮箱则 `CONFIG_REQUIRED`。插入运行，字段引擎、模型和问题集来自 S-05/C-04。
5. **发现披露**：读取标的与逻辑；无逻辑标的计入 `skipped_no_thesis`。对每个标的调用 `D-03.fetch_for_instrument`，得到窗口内全部 `FetchedEvent`。对每个事件调用 `persist_passages`：按 `EventFileDraft.seq` 作为 `file_seq` 依次用 S-01 切段，生成 `passage_id(event_id,file_seq,start,end)`，在**一个写事务**中 `INSERT ... ON CONFLICT(passage_id) DO NOTHING`；`content_status=title_only` 时不调用 S-01，直接把标题作为一个 `file_seq=-1, seq=0` 的段落写入，`content_status='title_only'`。任何事件落段失败则不创建该事件的批次。全部事件处理成功后，在短事务内推进水位线、写每对（标的，披露）一个 `pending` 批次，提交后启动 worker。另把最近 30 天内仍为 `failed` 或预算挂起 `pending` 的（标的，披露）并入本运行，按 `(instrument_id,event_id)` 去重；缓存负责跳过已完成的对。
6. **执行批次**：按 `published_at ASC, event_id ASC` 逐个执行。读取该事件的 `PassageRecord` 与有效逻辑，在事务外调用 `S-05.process_batch(ctx, theses, passages, cancel)`；结果在一个事务内更新批次、运行累计列并提交。任何一批失败只标记该批 `failed`。一个事件如果没有可判定段落（全部为空/解析失败），批次记为 `succeeded`、`passages=0`，并在 `warn` 中记录。
7. **预算耗尽**：S-05 抛 `BUDGET_EXCEEDED` 时，当前批保持 `pending` 并写 `error_code`；停止调度后续批次。已有成功批则运行 `partial`，没有成功批则 `failed`。
8. **终态**：全部批次 `succeeded` → `succeeded`；至少一个成功且另有失败或挂起 → `partial`；没有成功且有失败或挂起 → `failed`；无批次 → `succeeded`。写 `finished_at` 后发 `scan.finished`。
9. **取消**：每个批次边界和网络请求前检查取消令牌。取消后不再启动新批，已提交批保留，终态 `cancelled`。核心进程崩溃留下的 `running` 由第 3 步处理，绝不自动续跑半批。
10. **重试**：读失败批次和所属运行；置 `pending`、`attempts += 1`；同步调用 S-05。成功后更新批次与运行统计；若运行原为 `partial` 且所有失败均消失，改为 `succeeded`。
11. **幂等**：披露由 `event_id` 去重；判定由 S-05 的缓存键去重；同一披露重复扫描可产生新批次记录，但缓存命中不发模型请求且不重复写判定。

## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 同市场已有运行 | 不创建第二个运行 | `CONFLICT` | `error.CONFLICT`，文案“扫描正在进行” |
| `from` 早于 30 天 | 不创建运行，`field="from"` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 缺密钥或邮箱 | 不创建运行，`data.missing` 列明字段 | `CONFIG_REQUIRED` | `error.CONFIG_REQUIRED` |
| 披露列表获取失败 | 运行 `failed`；水位线不推进 | `SOURCE_UNAVAILABLE` / `TIMEOUT` | 对应 `error.*` |
| 单批失败 | 批次 `failed`，其他批继续 | 记录原错误码 | 扫描页显示批次原因 |
| 预算耗尽 | 当前批 `pending`，停调度 | `BUDGET_EXCEEDED` | `error.BUDGET_EXCEEDED` |
| 用户取消 | 已提交保留，终态 `cancelled` | — | 静默 |
| 重试非失败批次 | 不改变状态 | `CONFLICT` | `error.CONFLICT` |
| 运行 ID 不存在 | 不返回空对象 | `NOT_FOUND` | `error.NOT_FOUND` |

## 8. 测试（先写）
### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_first_scan_uses_configured_lookback` | `test_watermark.py` | now `2026-11-02T00:00Z`、水位线 null、回看 7 天 | start `2026-10-26T00:00Z`，`used_startup_catch_up=false` |
| `test_stale_watermark_is_capped_to_72_hours` | 同上 | 水位线 `2026-10-20T00:00Z`、now `2026-11-02T00:00Z` | start `2026-10-30T00:00Z`，标志 true |
| `test_explicit_from_uses_30_day_floor` | 同上 | from `2026-09-01T00:00Z` | `INVALID_ARGUMENT`，`field="from"` |
| `test_watermark_never_moves_backward` | 同上 | 旧值 `2026-11-01T00:00Z`，推进 `2026-10-31T00:00Z` | 仍为旧值 |
| `test_start_returns_before_fetch_completes` | `test_orchestrator.py` | D-03 阻塞 200 ms | 调用 50 ms 内返回 26 字符 runId |
| `test_second_start_same_market_conflicts` | 同上 | 第一次处于 running | `CONFLICT` |
| `test_batch_failure_does_not_stop_other_batches` | 同上 | 3 批，第 2 批抛 `MODEL_ERROR` | 第 1、3 批 succeeded；运行 `partial` |
| `test_no_successful_batch_marks_run_failed` | 同上 | 2 批均失败 | 运行 `failed`，`finished_at` 非空 |
| `test_budget_exhaustion_leaves_batch_pending` | 同上 | 第 1 批成功、第 2 批 `BUDGET_EXCEEDED` | 第 2 批 `pending`，运行 `partial` |
| `test_cancel_keeps_committed_batches` | 同上 | 2 批，第 1 批成功后取消 | 第 1 批 succeeded；运行 `cancelled`；第 3 批未创建 |
| `test_startup_marks_running_interrupted` | 同上 | 数据库有 2 条 running | 返回 2；两行均有 `finished_at` |
| `test_retry_failed_batch_updates_run_to_succeeded` | 同上 | 原 partial 仅剩 1 个失败批，重试成功 | 批次 `succeeded`，attempts 2，运行 `succeeded` |
| `test_same_event_is_not_duplicated_within_run` | 同上 | D-03 返回同一 eventId 两次 | `scan_batch` 仅 1 行 |
| `test_persist_passages_is_idempotent` | 同上 | 同一 `FetchedEvent` 调用 `persist_passages` 两次 | 第二次新增 0 行；`passage_id` 集合不变 |
| `test_event_without_text_succeeds_with_zero_passages` | 同上 | 事件所有文件 `text_status=empty` | 批次 `succeeded`，`passages=0`，无 decision |
### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增文件 | 临时 DuckDB、固定时钟、内存 fake D-03/S-05 | 测试内构造；D-03 依次返回 3 个虚构 accession |

## 9. 验收
### 9.1 命令与期望输出
```bash
(cd core && uv run pytest tests/unit/scan/test_watermark.py tests/unit/scan/test_orchestrator.py -q)
# 期望：15 passed，0 failed
scripts/check.sh
# 期望：exit=0；ruff、mypy 对 sentinel/scan 全绿
```
### 9.2 完成清单
- [ ] 第 4 节全部文件存在，`owns` 外无改动
- [ ] `008_scan.sql` 与 04 §3.8 逐字一致
- [ ] 五个扫描 RPC 按 §5.6 注册，运行状态严格按 §7.1
- [ ] 水位线只在完整抓取列表后单调推进
- [ ] `event_passage` 只由本包调用 S-01 后写入；S-01 不碰数据库
- [ ] 计时使用 `clock.now()`，没有 `datetime.now()`
- [ ] 已写 `docs/wp/status/P-02.md`

## 10. 交接、风险与回退
| 对象 | 使用或风险 | 约定与回退 |
|---|---|---|
| P-03 | 读取成功批次产生的判定 | 清单只信 S-05 已提交的数据 |
| U-05 | 订阅 `scan.progress` 与 `scan.finished` | 通知可能丢失，页面重新获得焦点时调用 `scan.status` |
| v1 调度器 | 复用 `compute_window` | 唤醒补跑范围由调度器传入 `explicit_from`，本包不启动定时器 |
| 终止后重试改变终态 | 用户看到原运行从 `partial` 变 `succeeded` | 仅当全部失败批成功时允许，其他终态字段不变 |
| 72 小时窗口截断更早水位线 | 长时间未启动会漏掉 72 小时以前的数据 | 用户在 30 天范围内显式传 `from`；界面显示实际窗口 |

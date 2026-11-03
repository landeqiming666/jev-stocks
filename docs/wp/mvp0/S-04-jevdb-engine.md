---
id: S-04
title: JEVDB 引擎
phase: mvp0
platform: shared
lane: semantic
deps: [S-02, G0-JEVDB]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [core/sentinel/semantic/engines/jevdb.py, core/tests/unit/semantic/test_jevdb.py, core/tests/fixtures/jevdb/]
appends: []
stubs: []
---

# S-04 JEVDB 引擎

## 0. 一眼看懂

- **目标**：实现与 `jev_direct` 同 Protocol、同 `Probabilities`、同 `PairScore`/`EvidenceScore` 的 JEVDB 引擎；用专用内存 DuckDB 连接和参数化临时表执行语义 SQL。
- **完成后解锁**：S-05 可用同一套流水线跑两个引擎；P-02 的 `auto` 可根据加载结果决定实际引擎。
- **预计规模**：实现约 360 行，测试约 300 行；不新增依赖，使用已有 `duckdb==1.4.3`。

## 1. 背景与边界

### 1.1 为什么需要它
JEVDB 直接把语义判定写进 SQL，适合课程要求的“语义连接”。但它也是研究代码，加载失败必须诚实降级。引擎自身不得偷偷改走直连：只有 S-02 的 `auto` 选择器可以在 `ENGINE_UNAVAILABLE` 时切换，并把 `engine.changed` 暴露给界面。

### 1.2 范围内
1. 扩展加载、专用连接、临时 secret、固定 settings、关闭清理。
2. 生成 `jev_probability` 的评分 SQL 与证据 SQL；用户文字只走表列绑定。
3. 把查询行映射为 `PairScore`；用字符数 ÷ 3.5 估算 token 并标 `tokens_estimated=True`。
4. 记录 `jevdb_stats()`；同步取消调用 `interrupt()`。
5. G0-JEVDB 失败时的失败路径、SQL 单测与 `ENGINE_UNAVAILABLE`；这只允许开发期推进，不能绕过 ADR-018 的最终验收。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 自动切到 `jev_direct` | S-02 `select_engine(auto)`；本引擎绝不降级 |
| 并发多个 DuckDB 连接 | 本引擎单实例串行；并发由上层批调度控制 |
| 复制或改写问题文本、阈值 | S-02 |
| 用 `jevdb_on_error='reject'` 把失败变成“不匹配” | 禁止 |
| 把 JEVDB 的估算 token 冒充实际 usage | 禁止；界面/报告带“≈” |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | 2.3、3.3、4、5.2、6.1、6.4–6.5、7 | 函数、SQL、设置、缓存与降级 |
| [02-技术架构.md](../../02-技术架构.md) | 7.3 连接隔离、12 稳定性 | 专用连接和失败语义 |
| [05-接口契约.md](../../05-接口契约.md) | 3.1–3.3 | 错误码、retryable、requestId |
| [09-测试与评测.md](../../09-测试与评测.md) | 2.2、5 SQL 注入 | 确定性、绑定参数、注入测试 |

## 3. 前置条件

- S-02 已交付 Protocol、问题集、`estimate_tokens()`、`classify()`、错误类型。
- G0-JEVDB 已交付扩展路径、SHA256、加载参数和 settings 结论。
- G0 的本地构建/LOAD 已通过，可加载明确注入的已核对扩展；缺路径或 ABI 异常才抛 ENGINE_UNAVAILABLE。真实非 NULL 模型推理未验证仍阻止最终 M-8，不能以本地可用代替外部闸门（F18-01）。
- 扩展路径只能来自设置或 `SENTINEL_JEVDB_PATH`；不接受 RPC 用户输入。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/semantic/engines/jevdb.py` | 新建 | `JevdbEngine`、SQL 构造、连接生命周期、错误映射 |
| `core/tests/unit/semantic/test_jevdb.py` | 新建 | §8.1 的 10 个测试 |
| `core/tests/fixtures/jevdb/score_rows.json` | 新建 | 2 逻辑 × 3 段落的查询结果 |
| `core/tests/fixtures/jevdb/evidence_rows.json` | 新建 | 4 句证据概率 |
| `core/tests/fixtures/jevdb/error_auth.txt` | 新建 | 上游查询的脱敏 401 文本 |
| `core/tests/fixtures/jevdb/error_rate_limit.txt` | 新建 | 脱敏 429 文本 |

## 5. 接口规格

### 5.1 公开接口
```python
class JevdbEngine:
    name: Literal["jevdb"] = "jevdb"
    def __init__(self, *, extension_path: Path, model_id: str,
                 secret_provider: Callable[[], str],
                 connection_factory: Callable[..., DuckDBConnection] | None = None,
                 endpoint: str | None = None) -> None: ...
    def health(self) -> EngineHealth: ...
    def load(self) -> None: ...
    def close(self) -> None: ...
    def score_pairs(self, company: str, pairs: Sequence[PairInput],
                    cancel: CancelToken) -> list[PairScore]: ...
    def score_event(self, company: str, theses: Sequence[ThesisInput],
                    passages: Sequence[PassageInput], cancel: CancelToken) -> list[PairScore]: ...
    def locate_evidence(self, thesis: ThesisInput, relation: Relation,
                        sentences: Sequence[str], cancel: CancelToken) -> EvidenceScore: ...

def build_score_sql(question_set: dict[str, QuestionSpec], table_suffix: str) -> str: ...
def build_evidence_sql(question_set: dict[str, QuestionSpec], table_suffix: str) -> str: ...
def map_jevdb_error(message: str) -> EngineError: ...
```
`load()` 幂等；未调用 `load()` 时 `score_pairs` 自动调用一次。`close()` 幂等。同一实例的公开方法用 `threading.RLock` 串行，避免临时表名和连接状态互相污染。`score_pairs` 返回数必须严格等于 `len(pairs)`，不得返回未请求的组合；`score_event` 只是全量笛卡尔积包装。`extension_path` 必须绝对、存在、后缀 `.duckdb_extension`，否则 `ENGINE_UNAVAILABLE`。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `BATCH_KEY` | str | 是 | 固定 `"batch"` | 批内键剪枝；同标的批内是空操作 |
| `table_suffix` | str | 是 | `[a-z0-9_]{1,20}` | 临时表名后缀，来自 ULID 小写 |
| `p_relevant/p_against/p_contradicts/p_kill_met/p_supports` | `DOUBLE` | 是 | `[0,1]`；仅 kill 可为 NULL | 查询概率 |
| `PairScore.input_tokens` | int | 是 | `≥0` | 字符估算，不声称实际 |
| `PairScore.tokens_estimated` | bool | 是 | 固定 `True` | 界面显示“≈” |
| `stats` | dict | 否 | `jevdb_stats()` 原列 | 请求、重试、去重输入数 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `DUCKDB_VERSION` | `1.4.3` | `jevdb.py` | 唯一 ABI |
| `JEVDB_THREADS` / `DUCKDB_THREADS` | `4` / `1` | 同上 | 语义并发与 DuckDB 线程 |
| `JEVDB_MAX_RETRIES` | `3` | 同上 | 上游重试 |
| `JEVDB_RETRY_MAX_DELAY` / `JEVDB_RETRY_AFTER_MAX` | `30` / `300` | 同上 | 退避秒数 |
| `JEVDB_TIMEOUT_SEC` | `60` | 同上 | 查询超时 |
| `DEFAULT_RETRY_AFTER_SEC` | `30` | 同上 | 429 未给头时的可展示值 |

## 6. 实现步骤

1. 校验 `duckdb.__version__ == "1.4.3"`；调用 `connection_factory(":memory:", config={"allow_unsigned_extensions":"true"})`，默认使用 `duckdb.connect`。禁止连接主库。
2. 从 `secret_provider()` 取 key；在全局 `_ENV_LOCK` 下暂存 `JEV_API_KEY`，执行 `LOAD '<path>'`（路径先断言无引号/换行/NUL）和 `CREATE SECRET jev (TYPE jev, PROVIDER env)`，随后恢复原环境。key 不保存到实例。
3. 执行固定 settings：`jevdb_backend=jev`、`jevdb_model=<model>`、`jevdb_threads=4`、`jevdb_max_retries=3`、`jevdb_retry_max_delay=30`、`jevdb_on_error=error`、`jevdb_timeout=60`、`threads=1`。禁止 `reject`。
4. 评分 SQL 创建 `th(ref,thesis,kill_condition,keys)`、`ps(pid,document,keys)` 与 `wanted(ref,pid)`；`th/ps` 只插入本次 pair 涉及的去重输入，`wanted` 精确写入请求的 pair。`executemany` 绑定用户文字，keys 都写 `['batch']`；先通过 wanted 连接约束实体对，再对选中的对执行概率函数，不先算笛卡尔积再过滤（F18-01）。
5. `SELECT th.ref, ps.pid` 与五个常量问题；`relevant/against/contradicts/supports` 输入 `{'thesis': th.thesis}` 与 `{'document': ps.document}`；`kill_met` 输入额外 `{'kill_condition': th.kill_condition}`。问题文字仅来自 S-02 的 JEVDB 变体。`score_event` 先生成全量 pair，再调用 `score_pairs`。
6. 每行映射一个 `PairScore`；`classify()` 由上层调用。任一概率为 NULL（除 kill）或越界抛 `MODEL_ERROR`，不得填 0。查询后调用 `SELECT * FROM jevdb_stats()` 写 debug 日志。
7. token 估算：每个 pair 按 `estimate_tokens(len(thesis)+len(kill or "")+len(document)+question_chars)`，`tokens_estimated=True`；`latency_ms` 为整条查询墙钟，同批复用。
8. 证据 SQL 建临时表 `ev(sid,sentence,thesis,kill_condition)`；每行调用 `jev_probability`，问题来自 `build_evidence_questions(..., flavor="jevdb")`；返回 `s1..sN` 对应概率。句子原文不进入模型输出，偏移由 S-05 计算。
9. `finally` 中 `DROP TABLE IF EXISTS` 清理所有本次创建的 th/ps/wanted 或 ev 临时表；失败路径也清理。`close()` 先 `DROP SECRET jev`，再关闭连接。
10. 取消：另一个控制线程调用 `connection.interrupt()`；查询捕获 interrupt 错误后转 `CancelledError`。已被 selector 加载失败时 `load()` 抛 `ENGINE_UNAVAILABLE`。
11. 错误映射：文本含 `401` → `UNAUTHENTICATED/INVALID_KEY`；`403` → `UNAUTHENTICATED/FORBIDDEN`；`429` → `RATE_LIMITED`（解析不到秒数用 30）；`timeout/timed out` → `TIMEOUT`；其他 DuckDB 查询错误 → `MODEL_ERROR`。仅加载/ABI/路径错误用 `ENGINE_UNAVAILABLE`。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 扩展缺失/ABI 不符 | `load()` 失败；显式 jevdb 不降级 | `ENGINE_UNAVAILABLE` | `error.ENGINE_UNAVAILABLE` |
| `auto` 模式加载失败 | 本引擎只抛错；S-02 选择器切直连一次 | `ENGINE_UNAVAILABLE` | 切 `jev_direct` 的 `engine.changed` |
| 401/403 | 不重试；保留远端文本摘要 | `UNAUTHENTICATED` | `error.UNAUTHENTICATED` |
| 429 | 上游重试耗尽后映射 | `RATE_LIMITED` | `error.RATE_LIMITED` |
| 查询返回 NULL kill | 合法，对应无失效条件 | 不适用 | 不适用 |
| 其他概率 NULL/越界 | 整批失败 | `MODEL_ERROR` | `error.MODEL_ERROR` |
| 用户文字含 `'`、`;`、`--` | 只作为表值，SQL 原样不变 | 不适用 | 不适用 |
| 扩展统计失败 | 只影响 debug 日志，不影响已成功结果 | 不适用 | 不适用 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_score_pairs_returns_one_pairscore_per_requested_pair` | `core/tests/unit/semantic/test_jevdb.py` | 2 逻辑 × 2 段落，只请求 3 对 | 3 个 PairScore；每个 `tokens_estimated=True` |
| `test_score_event_wraps_full_cartesian_product` | 同上 | 2 逻辑 × 3 段落 | `score_pairs` 收到 6 对；返回 6 个 PairScore |
| `test_score_pairs_sql_joins_wanted_pairs` | 同上 | 3 个请求 pair | SQL 含 `wanted` 连接；结果不含未请求组合 |
| `test_score_sql_contains_no_user_text` | 同上 | 逻辑含 `'; DROP TABLE x; --` | SQL 不含该串；参数列表含原文 |
| `test_score_sql_uses_kill_met_struct_separately` | 同上 | 一条有 kill，一条无 kill | `kill_condition` 只出现在 kill_met 参数 |
| `test_score_pairs_treats_null_probability_as_model_error` | 同上 | `p_against=NULL` | `MODEL_ERROR`；不返回 none |
| `test_missing_extension_raises_engine_unavailable` | 同上 | 不存在路径 | `ENGINE_UNAVAILABLE`；连接创建 0 次 |
| `test_auth_401_and_429_errors_are_distinct` | 同上 | 两段错误文本 | 分别为 `UNAUTHENTICATED`、`RATE_LIMITED` |
| `test_evidence_probabilities_follow_sentence_order` | 同上 | 4 个 sid | 列表长度 4、顺序 s1..s4 |
| `test_cancel_calls_interrupt_and_raises_cancelled` | 同上 | 假连接阻塞后取消 | `interrupt()` 1 次；`CancelledError` |
| `test_temp_tables_are_dropped_on_failure` | 同上 | 查询抛错 | 执行过两个 `DROP TABLE IF EXISTS` |
| `test_repeated_close_is_idempotent` | 同上 | 调用两次 | 第二次不抛错；连接关闭 1 次 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `score_rows.json` | 6 行、5 个概率 | 用虚构 ZZAR 和 G0-JEVDB 查询录制；无真实 key 时手写期望值，不冒充实测 |
| `evidence_rows.json` | 4 句概率 `[0.05,0.91,0.34,0.02]` | 06 §10 虚构段落 |
| `error_auth.txt` / `error_rate_limit.txt` | 上游错误 200 字内摘要 | 真实探针后脱敏；不得含 key 或完整 body |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd core && uv run pytest tests/unit/semantic/test_jevdb.py -q
# 期望：12 passed，0 failed
cd .. && scripts/check.sh
# 期望：exit=0；SQL 注入与临时表清理测试通过
```
若 G0-JEVDB 未通过，以上单元测试仍必须通过；S-04 状态文件必须将真实扩展加载验收标为 BLOCKED，且 I-02 的 M-8 不得通过，不能用 `jev_direct` 或 SQL 字符串测试替代。

### 9.2 完成清单
- [ ] 实现与 `jev_direct` 相同的 Protocol 与返回结构
- [ ] 用户文字从不拼进 SQL；kill_met STRUCT 单独处理
- [ ] `jevdb_on_error='error'`，JEVDB 自身绝不降级；`auto` 降级只由 S-02 完成
- [ ] 失败、取消、临时表清理、401/429 均有测试
- [ ] 第 8.1 节 12 个测试全部通过；已写 `docs/wp/status/S-04.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| S-05 | `JevdbEngine.score_pairs`、`tokens_estimated=True` | 只计算显式 pair；预算按估算值累计；界面显示“≈” |
| P-02 | `health()`、`load()`、`close()` | 应用退出必须调用 `close()`；自动降级由 selector 负责 |
| E-02 | 两引擎同问题集与同返回结构 | 指标按 engine 分开报告 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| JEVDB 构建不可用 | G0-JEVDB 失败 | 开发期可临时使用 `jev_direct`；本包仅保留 SQL 与失败测试，最终验收保持 BLOCKED |
| 上游 SQL 对 STRUCT 字段理解错误 | 概率异常或 NULL | 用 G0 样例改 JEVDB 问题指代，升问题集版本 |
| `interrupt()` 不终止 HTTP | 取消后仍占用 | 超时 60 秒兜底；上层丢弃结果并关闭连接 |
| 估算 token 偏差大 | 与直连样本差异明显 | 报告标注“≈”；不得用于精度结论 |

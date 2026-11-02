---
id: S-05
title: 判定流水线：证据、缓存、落库
phase: mvp0
platform: shared
lane: semantic
deps: [S-01, S-03, C-03]
size: M
owns: [core/sentinel/semantic/pipeline.py, core/sentinel/semantic/evidence.py, core/sentinel/semantic/cache.py, core/sentinel/storage/migrations/006_decision.sql, core/tests/unit/semantic/test_pipeline.py, core/tests/unit/semantic/test_evidence.py, core/tests/unit/semantic/test_cache.py]
appends: []
stubs: []
---

# S-05 判定流水线：证据、缓存、落库

## 0. 一眼看懂
- **目标**：把一个标的 × 一份披露的批次从“缓存检查 → 预算 → 引擎打分 → 事务落库 → 选代表判定 → 找证据 → 回写证据”完整串起来，失败不产生半批结论。
- **完成后解锁**：P-02 扫描编排、P-03 待处理清单、E-02 评测可以直接消费判定与证据。
- **预计规模**：实现约 500 行，测试约 420 行；不新增依赖，网络与模型调用全部在数据库事务外。
## 1. 背景与边界
### 1.1 为什么需要它
判定既贵又要可追溯。缓存键算错会重复付费；半批写入会让用户看到缺段落的结论；证据若不由原文回切，就可能出现模型幻觉。本包把重试放在引擎、把事务放在存储、把证据偏移限制在原文切片内。
### 1.2 范围内
1. 判定缓存键、命中查询、插入新判定、usage 累加。
2. 批处理顺序、预算、引擎调用、全有或全无写入。
3. 每个（逻辑，披露）选一个代表判定，只为 `overturn/weaken/uncertain` 找证据。
4. 标题证据、句子证据、整段回退、偏移校验、证据失败可见。
5. `006_decision.sql` 逐字实现 04 §3.6。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 抓取披露、生成段落 | D-03 |
| HTTP、SDK 重试、JEVDB 连接 | S-03、S-04 |
| 扫描调度、批次状态机、进度通知 | P-02 |
| 清单查询、用户处理动作 | P-03 |
| 评测指标与标注 | E-02 |
| 用模型自由文本当证据 | 禁止；只接受 Noul 概率 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | 4、5、6.1、6.5、7、8 | 分类、证据、缓存、预算、清洗 |
| [04-数据模型.md](../../04-数据模型.md) | 3.6、3.9、4、8.1、8.3 | decision/usage DDL、缓存键、代表判定 |
| [05-接口契约.md](../../05-接口契约.md) | 3.1–3.3、`DecisionSummary/Evidence` | 错误与证据结构 |
| [02-技术架构.md](../../02-技术架构.md) | 7.3、12 | 网络不得在事务内、失败不生成结论 |

## 3. 前置条件
- C-03 已提供 `Database.read()` 与 `Database.write()` 上下文管理器：`read()` 返回 `SqlExecutor`（只读游标），`write()` 返回 `WriteTx`（同时实现 `SqlExecutor`）；写上下文提交或回滚。
- S-01 已提供 `split_sentences()`、`TextSpan`；S-03 已实现 `SemanticEngine`。
- S-02 已提供 `classify()`、`headline()`、`reserve_tokens()`、`estimate_tokens()`、`cost_usd()`。
- 主库连接与引擎连接分离；本包只使用主库连接。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/semantic/cache.py` | 新建 | 文本规范化、3 个哈希、缓存查询、decision 插入、usage 更新 |
| `core/sentinel/semantic/evidence.py` | 新建 | 代表判定选择、句子/整段/标题证据、偏移校验 |
| `core/sentinel/semantic/pipeline.py` | 新建 | `DecisionPipeline.process_batch()`、事务边界、预算与统计 |
| `core/sentinel/storage/migrations/006_decision.sql` | 新建 | 逐字复制 04 §3.6 的 DDL 与索引 |
| `core/tests/unit/semantic/test_cache.py` | 新建 | §8.1 的缓存/哈希/落库测试 |
| `core/tests/unit/semantic/test_evidence.py` | 新建 | 代表判定、回切、标题与回退测试 |
| `core/tests/unit/semantic/test_pipeline.py` | 新建 | 批处理、预算、全有或全无测试 |

## 5. 接口规格
### 5.1 公开接口
```python
@dataclass(frozen=True)
class PassageRecord:
    passage_id: str; event_id: str; instrument_id: str; seq: int
    text: str; content_hash: str; content_status: Literal["full_text","title_only"]

@dataclass(frozen=True)
class BatchContext:
    run_id: str; batch_id: str; event_id: str
    instrument_id: str; company: str

@dataclass(frozen=True)
class BatchOutcome:
    status: Literal["succeeded"]
    new_decisions: int; cached_decisions: int
    input_tokens: int; estimated_tokens: int
    evidence_failures: int; truncated_passages: bool

def norm_text(value: str) -> str: ...
def thesis_content_hash(statement: str, kill_condition: str | None) -> str: ...
def passage_content_hash(text: str) -> str: ...
def decision_cache_key(engine: str, model_id: str, question_set_version: str,
                       thesis_hash: str, passage_hash: str) -> str: ...
def select_representative(rows: Sequence[DecisionRow]) -> DecisionRow | None: ...

class DecisionPipeline:
    def __init__(self, db: Database, engine: SemanticEngine, *,
                 model_id: str, daily_budget: int) -> None: ...
    def process_batch(self, ctx: BatchContext, theses: Sequence[ThesisInput],
                      passages: Sequence[PassageRecord], cancel: CancelToken) -> BatchOutcome: ...
```
`process_batch` 的 theses 为 1–5 条、passages 为 1–60 条；超过 60 段截断并令 `truncated_passages=True`。`status` 只返回成功；预算、模型、数据库错误均抛出，由 P-02 把批次置为 pending/failed。服务端或数据库异常不得返回空列表冒充成功。

`BatchOutcome.input_tokens` 与 `estimated_tokens` 是**判定请求与证据请求之和**；证据请求的用量在第 11 步第二次写事务成功后累加，因此返回前必须已完成该累加。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `DecisionRow` | dataclass | 是 | 与 04 §3.6 列一一对应 | 内存中的判定行 |
| `DecisionRow.headline` | float | 是 | `headline()` 结果 | 界面显示概率 |
| `DecisionRow.evidence_kind` | str \| None | 否 | `sentence/passage/title` | 清单判定必须有值 |
| `cache_key` | str | 是 | 64 位小写十六进制 | 唯一缓存身份 |
| `usage_daily` | row | 是 | `(UTC date,engine,model)` | 实际/估算 token 分开 |
| `EvidenceResult` | dataclass | 是 | `kind,start,end,text,warn` | 回写字段与可见警告 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MAX_PASSAGES` | `60` | `pipeline.py` | 每份披露最多判定段落 |
| `MAX_EVIDENCE_SENTENCES` | `40` | `evidence.py` | 证据请求句子上限 |
| `EVIDENCE_MIN_PROBABILITY` | `0.3` | 同上 | 低于该值回退整段 |
| `RELATION_RANK` | `overturn=0, weaken=1, uncertain=2` | 同上 | 代表判定严重度 |
| `QUESTION_SET_VERSION` | 从 `questions.py` 导入 | `cache.py` | 缓存键一部分 |
| `TOKEN_SOFT_LIMIT_RATIO` | `0.9` | `pipeline.py` | 批前预留后不足 10% 仍拒绝 |

## 6. 实现步骤
1. `norm_text` 按 04 §4：NFC、CRLF/CR→LF、去首尾空白，内部空白原样。逻辑哈希 `sha256(norm(statement)+"\n---\n"+norm(kill or ""))`；段落哈希 `sha256(norm(text))`；缓存键 `sha256(engine|model_id|question_set_version|thesis_hash|passage_hash)`，全部 64 位小写十六进制。
2. 校验段落 `len(text)<=1200`，否则 `ValueError`；超过 60 段按 `seq` 升序截断，记录 warn。按 `(thesis_id,thesis_version,passage_id)` 排序以稳定输出。
3. 用读事务查询所有 cache key。命中行直接转 `DecisionRow`；缺失对组成 pair keys。**缓存命中不发请求、不写 usage**。
4. 预估缺失请求：`raw = sum(estimate_tokens(len(thesis)+len(kill or "")+len(document)+question_chars))`；`reserved=reserve_tokens(raw)`。读取今日 `usage_daily`，`used+reserved>daily_budget` 时抛 `BUDGET_EXCEEDED`，不调用引擎。
5. 在事务外调用 `engine.score_event(ctx.company, needed_theses, needed_passages, cancel)`；返回数必须等于缺失 pair 数，id 集合必须完全匹配。否则抛 `MODEL_ERROR`，不写部分。
6. **进入写事务前先调用 `cancel.raise_if_cancelled()`**：若引擎返回后、事务开始前被取消，丢弃结果，不写 decision 与 usage。随后在**一个写事务**中插入新 decision 行并用 `ON CONFLICT(cache_key) DO NOTHING` 防重复；发生冲突时读回已有行。`decision_id=new_id()`、`created_at=clock.now()`、`content_status=passage.content_status`。同一事务 upsert `usage_daily` 的 `input_tokens/estimated_tokens` 并把 `requests` 加 1（只计判定请求；`jevdb` 的 token 计入 `estimated_tokens`，`jev_direct` 计入 `input_tokens`）。
7. 将新行与缓存行合并；按 `(thesis_id,event_id)` 分组，用 `select_representative()` 按关系严重度、headline 降序、段落 `seq` 升序、`decision_id` 升序选一条。
8. 只对代表且关系为 `overturn/weaken/uncertain` 的判定找证据。`title_only` 直接 `kind=title`；全文按 S-01 切句，取前 40 句。证据预算检查失败时回退整段，不抛预算错误。
9. 证据调用在事务外；成功概率最大值 `>=0.3` 时取该句跨度，平票取序号小者；`<0.3` 回退 `passage`。校验 `passage.text[start:end]==sentence.text`，失败也回退 passage 并记 warn。
10. 证据请求抛 `MODEL_ERROR/TIMEOUT/RATE_LIMITED`（取消除外）时回退 `passage`、保留判定、`evidence_failures += 1`；不重试。取消则整批抛 `CancelledError`，不写证据。
11. 证据与 usage 在第二个写事务中回写；只更新仍为空证据的 decision，并把**证据请求**的 `input_tokens/estimated_tokens` 累加到 `usage_daily`、`requests` 加 1，不得重复累加第 6 步的判定 token。任何一个代表判定最终都必须有 `title/passage/sentence`，否则不得返回成功。
12. 返回 `BatchOutcome`；不在这里写 `scan_batch` 状态或发通知。所有日志带 `run_id/batch_id/event_id`，不含逻辑正文与披露正文。

## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 预算不足 | 引擎调用前停止 | `BUDGET_EXCEEDED` | `error.BUDGET_EXCEEDED` |
| 引擎失败 | 不写 decision/usage | 原引擎错误码 | 对应 `error.*` |
| 返回 pair 数不符 | 整批失败 | `MODEL_ERROR` | `error.MODEL_ERROR` |
| 并发缓存冲突 | 读回已有行，不重复计费 | 不报错 | 不适用 |
| 超过 60 段 | 截断并 warn | 不报错 | 清单标注“仅分析前 60 段” |
| 证据调用失败 | 回退整段，保留判定 | 不报错，记 warn | “未能定位到单句，以下为整段原文” |
| 证据概率低 | 回退整段 | 不报错 | 同上 |
| 用户取消 | 丢弃未写结果 | `CANCELLED` | 不显示 |
| 数据库写失败 | 该事务回滚 | `INTERNAL` | `error.INTERNAL` |

## 8. 测试（先写）
### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_decision_cache_key_changes_with_each_component` | `core/tests/unit/semantic/test_cache.py` | 依次改 engine/model/qs/thesis/passage | 5 个 key 全部不同且 64 位 |
| `test_norm_text_preserves_internal_whitespace` | 同上 | `"  a  b\r\n"` | `"a  b"` |
| `test_cached_pair_does_not_call_engine_or_usage` | `core/tests/unit/semantic/test_pipeline.py` | 全部命中 | 引擎 0 次；usage 增量 0 |
| `test_engine_failure_writes_no_decisions_or_usage` | 同上 | 2 个缺失对，引擎抛 `MODEL_ERROR` | 两表行数不变 |
| `test_wrong_pair_count_fails_whole_batch` | 同上 | 期望 2，返回 1 | `MODEL_ERROR`；不落库 |
| `test_one_new_decision_per_missing_pair_and_usage_once` | 同上 | 1 逻辑 × 2 段落 | 2 行 decision；usage 为响应 token 总和 |
| `test_representative_prefers_overturn_then_headline_then_seq` | `core/tests/unit/semantic/test_evidence.py` | 4 行乱序 | 选 `overturn,0.93,seq=1` |
| `test_sentence_evidence_offsets_round_trip` | 同上 | E1 4 句概率 `[.05,.91,.34,.02]` | `kind=sentence`；回切文字等于证据句 |
| `test_low_evidence_probability_falls_back_to_passage` | 同上 | 全部 `<0.3` | `kind=passage`；`start/end=None` |
| `test_evidence_model_error_keeps_decision_and_warns` | 同上 | 引擎抛 `MODEL_ERROR` | 判定仍在；`kind=passage`；warn 1 条 |
| `test_title_only_uses_title_without_evidence_call` | 同上 | `content_status=title_only` | `kind=title`；调用 0 次 |
| `test_network_never_runs_inside_write_transaction` | 同上 | 记录事务进入/退出与调用顺序 | 引擎调用在第一次写事务之外 |
| `test_cancel_after_engine_returns_writes_nothing` | 同上 | 引擎正常返回后、写事务前置位 cancel | 抛 `CANCELLED`；decision 与 usage 行数不变 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增 fixture 文件 | 复用 `core/tests/fixtures/jev/e1_overturn.json`、`semantic/segment/e1_passage.txt` | 固定虚构 ZZAR 数据；测试不联网 |

## 9. 验收
### 9.1 命令与期望输出
```bash
cd core && uv run pytest tests/unit/semantic/test_cache.py tests/unit/semantic/test_evidence.py tests/unit/semantic/test_pipeline.py -q
# 期望：13 passed，0 failed
cd .. && scripts/check.sh
# 期望：exit=0；迁移 checksum、ruff、mypy、pytest 全绿
```
### 9.2 完成清单
- [ ] `006_decision.sql` 与 04 §3.6 逐字一致，含两个索引与 `UNIQUE(cache_key)`
- [ ] 缓存命中零请求、零费用；逻辑/段落/问题集变化会换 key
- [ ] 网络调用全在写事务外；引擎失败/取消不留下半批数据
- [ ] 每个清单判定都有 title/passage/sentence 证据；句子可精确回切
- [ ] 证据失败回退整段、保留判定并可见
- [ ] 第 8.1 节 13 个测试全部通过；已写 `docs/wp/status/S-05.md`

## 10. 给下游的交接
| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| P-02 | `DecisionPipeline.process_batch()`、`BatchOutcome` | 预算错误置 pending；模型错误置 failed；取消置 cancelled |
| P-03 | 已落库的 decision 与 evidence 字段 | 清单只取代表判定；每条必须有证据 |
| E-02 | cache_key、decision rows、engine/model | 评测按 engine/model/question set 分组 |
| C-03 | `006_decision.sql`、`usage_daily` | 迁移按编号补应用；不得跨事务网络 |

## 11. 风险与回退
| 风险 | 征兆 | 回退 |
|---|---|---|
| C-03 的事务接口不同 | 导入/类型失败 | 先提 CR，统一 `read/write` 适配层；不得自行改 C-03 |
| 缓存键与响应模型漂移 | 重复付费 | 引擎强制 model 相等；S-05 断言 `PairScore.model_id == model_id` |
| 证据句概率普遍偏低 | 大量 passage | 记录比例供评测；不擅自降低 0.3 |
| 写入冲突 | cache_key 唯一错误 | `ON CONFLICT` 读回；仍冲突则回滚并报 `INTERNAL` |
| 事务过长 | 锁定超时 | 只做插入/更新；任何网络、分句、证据调用移出事务 |

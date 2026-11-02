---
id: S-03
title: Jev 直连引擎
phase: mvp0
platform: shared
lane: semantic
deps: [S-02, G0-JEV]
size: M
owns: [core/sentinel/semantic/engines/jev_direct.py, core/tests/unit/semantic/test_jev_direct.py, core/tests/fixtures/jev_direct/]
appends: []
stubs: []
---

# S-03 Jev 直连引擎

## 0. 一眼看懂
- **目标**：实现 `SemanticEngine` 的 `jev_direct` 引擎：按段落打包逻辑，4 路并发调用官方 SDK，校验概率，整批成功或整批失败，并把 401/403/429 等错误准确映射。
- **完成后解锁**：S-05 可以用真实或 fake 引擎跑判定流水线，S-04 可复用错误与响应校验约定。
- **预计规模**：实现约 360 行，测试约 300 行；只使用 WP-00 已锁定的 `typesafe-sdk`，不新增依赖。

## 1. 背景与边界
### 1.1 为什么需要它
Jev 是产品唯一允许产出判定的模型。网络重试若分散在 SDK 与业务层，会产生重复计费；半个披露的判定若入库，清单会出现无法解释的空洞。本包把 SDK 细节收在一个适配层，公开行为只有全成功、全失败或取消。

### 1.2 范围内
1. `JevDirectEngine` 实现 S-02 的 `SemanticEngine` Protocol。
2. 官方 SDK 适配器：构造客户端、调用 `system_one`、读取 `answers/model/usage`、映射异常。
3. 每个段落 1 个请求；`PACK_THESES=False` 时每个（逻辑，段落）1 个请求。
4. 线程池并发 4；只保留 SDK 内一层重试。
5. 证据请求 1 次，按句子返回概率列表。
6. 取消检查、全有或全无、request id 诊断、token 分配。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 定义问题文本、阈值、`Probabilities` | S-02 |
| 缓存、预算、代表判定、数据库 | S-05 |
| 分句与证据偏移 | S-01、S-05 |
| 自动切换 JEVDB | S-02 的选择器与组合根 |
| 在业务层再包重试 | 禁止；会造成双重重试 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | 2.1–2.2、3.2–3.4、5.2、6.1、6.3、8 | 请求、SDK、错误、证据和注入规则 |
| [05-接口契约.md](../../05-接口契约.md) | 3.1–3.3 | 错误对象、retryable、requestId |
| [02-技术架构.md](../../02-技术架构.md) | 7 事务、11 日志、12 稳定性 | 网络在事务外、单层重试、取消 |
| [09-测试与评测.md](../../09-测试与评测.md) | 2.2–2.4 | 假客户端、cassette、固定时钟 |

## 3. 前置条件
- S-02 已交付 `ThesisInput`、`PassageInput`、`PairScore`、`EvidenceScore`、`Probabilities`、`build_score_questions()`、`build_evidence_questions()`、`classify()`。
- G0-JEV 状态报告给出 SDK 的构造参数、`model` 传法、异常导入路径和 retry 行为。若结论为 BLOCKED，本包仍按适配层实现并用 mock 验收，真实调用验收保持阻塞。
- 密钥仅从调用方或钥匙串注入；测试只用 `test-key-do-not-use`。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/semantic/engines/jev_direct.py` | 新建 | 引擎、SDK 适配器、错误映射、并发与取消 |
| `core/tests/unit/semantic/test_jev_direct.py` | 新建 | §8.1 的 10 个测试，全部使用假客户端 |
| `core/tests/fixtures/jev_direct/success_packed.json` | 新建 | 2 逻辑 × 1 段落、9 个答案的成功响应 |
| `core/tests/fixtures/jev_direct/success_evidence.json` | 新建 | 4 句证据概率 |
| `core/tests/fixtures/jev_direct/error_401.json` | 新建 | 401 状态、body、request id 的脱敏结构 |
| `core/tests/fixtures/jev_direct/error_429.json` | 新建 | 429 与 `retry_after_ms=2500` |

## 5. 接口规格
### 5.1 公开接口
```python
class SystemOneClient(Protocol):
    def call(self, *, model: str, state: dict[str, object],
             questions: dict[str, QuestionSpec]) -> SystemOneResponse: ...

@dataclass(frozen=True)
class SystemOneResponse:
    model: str
    answers: Mapping[str, float]
    input_tokens: int
    output_tokens: int

class JevDirectEngine:
    name: Literal["jev_direct"] = "jev_direct"
    def __init__(self, *, api_key: str, model_id: str,
                 client_factory: Callable[[str], SystemOneClient],
                 max_workers: int = 4) -> None: ...
    def health(self) -> EngineHealth: ...
    def score_event(self, company: str, theses: Sequence[ThesisInput],
                    passages: Sequence[PassageInput], cancel: CancelToken) -> list[PairScore]: ...
    def locate_evidence(self, thesis: ThesisInput, relation: Relation,
                        sentences: Sequence[str], cancel: CancelToken) -> EvidenceScore: ...

def map_sdk_exception(exc: BaseException) -> EngineError: ...
def allocate_tokens(total: int, pair_count: int) -> list[int]: ...
```
构造时 `api_key` 只传给 `client_factory`，**不得保存为实例属性、写日志或放进异常**。`max_workers` 必须为 `1..4`，越界抛 `ValueError`。`health()` 不发网络请求：已配置返回 `ok`，上次批次认证失败可返回 `degraded`，缺 key 返回 `unconfigured`。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `SystemOneResponse.model` | str | 是 | 以 `jev-` 开头 | 实际应答模型 |
| `answers` | `Mapping[str,float]` | 是 | 键完整、值 `[0,1]` 有限 | 仅 Noul 概率 |
| `input_tokens/output_tokens` | int | 是 | `≥0` | 服务端 usage |
| `PairScore.input_tokens` | int | 是 | 同批求和等于响应总量 | 打包请求的确定性分摊 |
| `PairScore.tokens_estimated` | bool | 是 | 固定 `False` | 直连有实际 token |
| `PairScore.latency_ms` | int | 是 | `≥0` | 单请求墙钟时间 |
| `EvidenceScore.sentence_probabilities` | list[float] | 是 | 长度等于输入句数 | 每句“是否命中”的概率 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `JEV_CONCURRENCY` | `4` | `jev_direct.py` | 固定最大并发 |
| `REQUEST_TIMEOUT_SEC` | `60.0` | 同上 | SDK 整体调用预算 |
| `MAX_RETRIES` | `3` | 同上 | SDK 内重试次数 |
| `BACKOFF_INITIAL_SEC` / `BACKOFF_MAX_SEC` | `1.0` / `20.0` | 同上 | 退避参数 |
| `MAX_EVIDENCE_SENTENCES` | `40` | 同上 | 证据请求上限 |
| `CONTEXT_RETRY_MIN_THESES` | `2` | 同上 | 上下文超限可拆分的最小逻辑数 |

## 6. 实现步骤

1. `_SdkClient` 适配器在第一次 `call` 前懒加载 `typesafe_sdk`，按 G0 报告的签名构造 `TypeSafeClient`；`RetryPolicy` 精确使用 §5.3。不得在适配器外再捕获 5xx 重试。
2. `score_event` 先校验：theses 数量 `1..5`、passages 非空、每段 `≤1200` 字符、输入内容哈希非空；调用 `cancel.raise_if_cancelled()`。
3. `PACK_THESES=True` 时每个段落构造 `state={"company":...,"document":...,"theses":{ref:...}}` 和该段全部问题；`False` 时每对构造单逻辑状态。请求顺序固定为段落升序、逻辑 ref 字典序。
4. 用 `ThreadPoolExecutor(max_workers=len(requests) if <4 else 4)` 提交；每个线程在网络调用前再次检查 cancel。若取消，设置 `threading.Event`，不再发新请求，等待已发请求返回或超时。
5. 每个响应校验问题名集合等于请求集合；`answers[name]` 必须是有限 float 且 `[0,1]`；任一缺失、多余或越界都抛 `MODEL_ERROR("INCOMPLETE_RESPONSE")`。不得把缺答案填 0。
6. 同一批所有响应的 `model` 必须相同，且等于配置 `model_id`；否则抛 `MODEL_ERROR("MODEL_MISMATCH")`，避免缓存键漂移。
7. 全部成功后才组装 `PairScore`；任一请求失败时等待其余请求结束、丢弃所有结果并抛首个错误。`input_tokens` 用 `allocate_tokens` 均分，余数给请求内第一个 pair。
8. 证据：校验句子数 `1..40`；构造 06 §5.2 的一个请求；问题名为 `s1..sN`；只读取概率，返回与输入等长的 `EvidenceScore`。句子文字从不来自模型响应。
9. 异常映射先读 `status`、`request_id` 与 `retry_after_ms`：401 → `UNAUTHENTICATED/INVALID_KEY`；403 → `UNAUTHENTICATED/FORBIDDEN`；404 → `UNAUTHENTICATED/MODEL_NOT_FOUND`；429 → `RATE_LIMITED`；超时 → `TIMEOUT`；5xx/529/连接/响应校验 → `MODEL_ERROR`；400/422 → `INTERNAL`。
10. 400/422 的 detail 若同时含 `context` 与 `maximum`/`token`，且本请求有至少 2 条逻辑，按创建顺序减半逻辑后重试一次；单逻辑仍失败则 `INTERNAL`。其他 400 不拆分。
11. request id 写入 `EngineError.detail` 的结构化文本，`data.requestId` 只用于日志关联；不把完整响应 body 写日志，只写最长 200 字脱敏摘要。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 缺 key | 工厂抛错，不发请求 | `CONFIG_REQUIRED` | `error.CONFIG_REQUIRED` |
| 401 | 不重试；记 request id | `UNAUTHENTICATED` | `error.UNAUTHENTICATED` |
| 403/404 | 不重试；reason 区分权限与模型 | `UNAUTHENTICATED` | 同上 |
| 429 | 用 `ceil(retry_after_ms/1000)` | `RATE_LIMITED` | `error.RATE_LIMITED` |
| 超时 | 取消该请求并整批失败 | `TIMEOUT` | `error.TIMEOUT` |
| 5xx/529/坏响应 | 整批失败，不写 partial | `MODEL_ERROR` | `error.MODEL_ERROR` |
| 400/422 非上下文 | 视为我们请求有缺陷 | `INTERNAL` | `error.INTERNAL` |
| 用户取消 | 不再发请求，丢弃结果 | `CANCELLED` | 不显示 |
| 并发结果乱序 | 按输入 pair 顺序重排 | 不适用 | 不适用 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_score_event_packs_all_theses_per_passage` | `core/tests/unit/semantic/test_jev_direct.py` | 2 逻辑 × 3 段落 | 调用 3 次；返回 6 个 PairScore |
| `test_score_event_does_not_emit_partial_results` | 同上 | 第 2 个请求抛 `MODEL_ERROR` | 抛错；返回列表不存在 |
| `test_missing_answer_maps_to_model_error` | 同上 | 响应缺 `t1__supports` | `MODEL_ERROR`，detail 含 `INCOMPLETE_RESPONSE` |
| `test_auth_401_and_403_have_distinct_reasons` | 同上 | 两个假异常 | 都 `UNAUTHENTICATED`，reason 分别为 `INVALID_KEY`/`FORBIDDEN` |
| `test_rate_limit_carries_retry_after_seconds` | 同上 | `retry_after_ms=2500` | `RATE_LIMITED`，`retryAfterSec=3` |
| `test_context_limit_splits_multi_thesis_request_once` | 同上 | 4 条逻辑，首次 400 context | 首次 4 题组，一次重试 2 题组，最终成功 |
| `test_evidence_returns_probabilities_in_sentence_order` | 同上 | 4 句，概率 0.05/0.91/0.34/0.02 | 列表精确等于输入概率顺序 |
| `test_cancel_before_request_sends_nothing` | 同上 | token 已取消 | `CancelledError`；客户端调用 0 次 |
| `test_allocate_tokens_preserves_total` | 同上 | total=10，pair_count=3 | `[4,3,3]`；sum=10 |
| `test_engine_never_stores_or_logs_api_key` | 同上 | 构造后触发 401 | `repr(engine)` 与捕获日志均不含测试 key |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `success_packed.json` | 2 逻辑 × 1 段落的 9 个概率 | 从 G0-JEV cassette 复制成功样本，去掉请求 id/headers |
| `success_evidence.json` | 4 句证据概率 | 06 §10 的虚构 ZZAR 页面 |
| `error_401.json` / `error_429.json` | 状态、body 摘要、request id、retry-after | 真实探针记录后脱敏；没有记录时手工构造假异常，不冒充实测 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd core && uv run pytest tests/unit/semantic/test_jev_direct.py -q
# 期望：10 passed，0 failed
cd .. && scripts/check.sh
# 期望：exit=0；无裸 except、无第二层 5xx 重试、日志无密钥
```

### 9.2 完成清单
- [ ] 实现 S-02 Protocol，不复制问题文本或阈值
- [ ] 4 路并发；全部成功才返回，任一失败无部分结果
- [ ] 401/403/429/404/400/5xx/超时映射有测试；request id 保留
- [ ] 证据只返回句子概率，不解析模型自由文本
- [ ] 第 8.1 节 10 个测试全部通过；已写 `docs/wp/status/S-03.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| S-05 | `JevDirectEngine.score_event/locate_evidence` | 网络在事务外；失败不落判定 |
| S-04 | `map_sdk_exception` 的 reason 命名风格 | 不共享 SDK 客户端 |
| P-02 | `health()` 与 `EngineError` | 授权错误引导设置；模型错误可重试批次 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| SDK 异常类与文档不同 | ImportError/属性错误 | 只修 `_SdkClient` 适配器；公开接口不变 |
| 打包请求上下文超限 | 400 context | 每条逻辑单独请求一次；仍失败则 `INTERNAL` |
| 取消后线程仍占用连接 | 关闭慢 | SDK 超时 60 秒兜底；批次结果丢弃，RPC 已返回 |
| 响应模型漂移 | `MODEL_MISMATCH` | 停止入库，修复配置；不得用返回模型改配置缓存 |

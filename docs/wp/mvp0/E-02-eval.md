---
id: E-02
title: 标注集与评测脚本
phase: mvp0
platform: shared
lane: semantic
deps: [S-05]
size: L
size_approval: cr/F18-01-closure-clarifications.md
owns: [core/sentinel/evaluation/, scripts/eval.py, core/tests/fixtures/eval/, core/tests/unit/evaluation/]
appends: []
stubs: []
---
# E-02 标注集与评测脚本

## 0. 一眼看懂

- **目标**：用 60 对固定数据、一条离线命令和可机读报告实现提醒类指标、语言分层与可选基线对比；synthetic 功能回放与真实双人标注/模型录制分开，MVP-0 不设 F1 硬阈值（F18-01）。
- **完成后解锁**：I-02。
- **预计规模**：约 600 行，含数据校验、评测、统计、基线和测试；数据 60 行 JSONL。

## 1. 背景与边界

### 1.1 为什么需要它
没有固定数据时，每次调问题措辞都会“看起来更好”。本包把数据、阈值、模型 ID、问题集版本和报告口径全部固定，使同一版本可复现，调参集与测试集不混用。

### 1.2 范围内
1. 60 对中文/英文逻辑与披露段落，双人标注、商定标签和证据句。
2. 严格口径与宽松口径的混淆矩阵、精确率、召回率、F1、Wilson 区间和 bootstrap 区间。
3. 与逐对通用 LLM 基线的质量、调用数、输入/输出 token、耗时和费用对比。
4. `scripts/eval.py` 的离线回放、真实引擎和可选基线三种模式。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 修改问题文本、阈值或分类器 | S-02、S-05；本包只调用 |
| 新增 RPC 方法 | 不做；评测只在核心进程外运行 |
| 把评测结果自动写回产品 | 不做；报告只落 `eval/reports/` |
| 训练或微调模型 | 不做；MVP-0 只评测 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [09-测试与评测.md](../../09-测试与评测.md) | 9.1～9.7 | 数据格式、指标、基线、复现要求 |
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | 5 分类、6.5 缓存、7.3 费用 | 预测与费用口径 |
| [05-接口契约.md](../../05-接口契约.md) | 3.2 错误码 | 失败时报告而不是伪造结果 |
| [00-术语与约定.md](../../00-术语与约定.md) | 1.4 虚构数据、4 时间与数值 | 数据与浮点规则 |
| [decisions.md](../../decisions.md) | ADR-015 | 固定完整模型 ID |

## 3. 前置条件

- 已提供 SemanticEngine、domain.classify 与 S-05 的公共接口；本包显式装配评测，不假定 load_pipeline 等未提供函数。
- G0 真实 cassette 未齐，可完成显式 synthetic replay 功能测试；报告必须标来源，不能称为真实模型质量验收。
- `resources/pricing.toml` 存在，含固定模型 ID 的输入与输出单价。
- Python 进程可读 `EVAL_BASELINE_*` 环境变量，但默认不存在；密钥只从环境读取。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/tests/fixtures/eval/dataset.jsonl` | 新建 | 60 对权威标注数据 |
| `core/tests/fixtures/eval/manifest.json` | 新建 | 计数、比例、哈希、生成参数 |
| `core/tests/fixtures/eval/cassettes/` | 新建 | 12 份 P/R 回放帧，覆盖四类关系 |
| `core/tests/fixtures/eval/baseline_example.jsonl` | 新建 | 3 条通用 LLM 输出样例，不联网 |
| `core/sentinel/evaluation/__init__.py` | 新建 | 导出 `EvaluationRunner` 与 `evaluate` |
| `core/sentinel/evaluation/dataset.py` | 新建 | 读取、schema 校验、哈希、split 过滤 |
| `core/sentinel/evaluation/metrics.py` | 新建 | 混淆矩阵、P/R/F1、Wilson、bootstrap |
| `core/sentinel/evaluation/runner.py` | 新建 | 逐样本预测、取消、超时与报告聚合 |
| `core/sentinel/evaluation/baselines.py` | 新建 | OpenAI 兼容逐对基线 |
| `core/sentinel/evaluation/report.py` | 新建 | Markdown、JSON、predictions 输出 |
| `core/tests/unit/evaluation/test_{dataset,metrics,runner,baselines,report}.py` | 新建 | §8.1 的测试 |
| `scripts/eval.py` | 新建 | CLI 入口与退出码 |

## 5. 接口规格

### 5.1 公开接口
```python
class EvalSample(BaseModel):
    id: str; split: Literal["tuning", "test"]; lang: Literal["zh", "en"]; subsets: list[str]
    instrument: str; thesis: ThesisRef; passage: PassageRef; label: Label
    annotators: list[AnnotatorLabel]; adjudicated: bool; notes: str

def load_dataset(path: Path) -> Dataset: ...
def validate_dataset(dataset: Dataset) -> None: ...
def compute_metrics(rows: Sequence[PredictionRow], positives: set[str]) -> Metrics: ...
def evaluate(config: EvalConfig, engine: SemanticEngine, pipeline: Pipeline) -> EvalReport: ...
def run_baseline(config: BaselineConfig, samples: Sequence[EvalSample]) -> BaselineReport: ...
def write_report(report: EvalReport, out_dir: Path) -> ReportPaths: ...
```
`evaluate` 对样本逐条调用 S-05 的同一分类函数，不复制阈值；任一引擎错误使该样本 `status=failed`，按失败数列出，不映射成 `none`。默认 60 秒超时，取消令牌在每次请求前检查。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `id` | str | 是 | `p-0001`…`p-0060` 唯一 | 样本 ID |
| `split` | str | 是 | `tuning/test` 各 30 | 禁止运行前混用 |
| `lang` | str | 是 | 每个 split 各 15 个 `zh/en` | 语言分层 |
| `subsets` | list[str] | 是 | `numeric/title_only/adversarial/long/multi_thesis` | 可多选 |
| `eventState` | str | 是 | `planned/completed/cancelled/na` | 事件状态；`completed` 才能作为 `kill_met` 正例 |
| `label.relation` | str | 是 | `none/support/weaken/overturn` | 金标准，不含 `uncertain` |
| `label.evidenceSentence` | int\|null | 是 | 阳性必填，`none/support` 为 `null` | 从 1 开始的句号 |
| `prediction.relation` | str | 是 | 五类 | 系统输出 |
| `usage.calls` | int | 是 | ≥ 0 | 模型请求数 |
| `usage.inputTokens` | int | 是 | ≥ 0；JEVDB 标 `estimated=true` | 输入 token |
| `usage.outputTokens` | int | 是 | ≥ 0 | 基线输出 token；JEV 可为 0 |
| `usage.latencyMs` | int | 是 | ≥ 0 | 单样本墙钟耗时 |
| `usage.costUsd` | Decimal | 是 | ≥ 0，6 位小数 | 按定价表计算 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `SPLIT_SEED` | `20261102` | `manifest.json` | 分层抽样种子 |
| `BOOTSTRAP_SEED` | `20261102` | `metrics.py` | F1 区间重采样种子 |
| `BOOTSTRAP_N` | `1000` | `metrics.py` | 重采样次数 |
| `POSITIVE_CLASSES` | `{"weaken","overturn"}` | `metrics.py` | 提醒类 |
| `GATE_F1` | `0.80` | `runner.py` | 测试集严格 F1 门槛 |
| `GATE_LANG_DELTA` | `0.05` | `runner.py` | 中文不得低于英文超过 0.05 |

## 6. 实现步骤

1. 读取 JSONL，拒绝重复 ID、空白文本、未知字段、未商定 `adjudicated=false`、split 比例不为 30/30；校验总分布 `overturn=8/weaken=14/support=10/none=28`、每 split `4/7/5/14`、正负 `22:38`。`kill_met` 正例必须 `eventState=completed`；`planned/cancelled` 只能作为削弱或无关负例。
2. 校验每个 split 中文 15/英文 15 与子集 `5/3/3/3/3`；计算 SHA-256，与 manifest 不一致时退出 2，不运行模型。
5. `--split test` 只读 30 条；没有 `--allow-tuned-test` 时拒绝 `tuning` 与 `test` 混合报告。
6. 默认禁用判定缓存，使用临时内存库；每条记录 `question_set_version`、`model_id`、阈值、引擎和代码版本。
7. 严格口径只把预测 `weaken/overturn` 算正；宽松口径另把 `uncertain` 算正。四类金标准 × 五类预测生成混淆矩阵。
8. F1 用 `2TP/(2TP+FP+FN)`；精确率/召回率 Wilson 95%；F1 用 1,000 次 bootstrap，输出 2.5% 与 97.5% 分位。
9. 证据命中率的分母为“金标准阳性且宽松预测阳性”；单句命中才为成功，整段/标题证据分别计数。
10. `--baselines` 逐对发送一个综合提示，要求只返回四类标签；每对计算质量、调用、输入/输出 token、墙钟耗时和费用，不重试模型错误。
11. 写出 `report.md`、`report.json`、`predictions.jsonl`；报告头写数据哈希、代码版本、模型、问题集、阈值、日期和总费用。
12. `--gate` 时严格 F1 `< 0.80` 或中文 F1 比英文低 `> 0.05`，退出 3；输出 `gate.passed=false`，不得静默降级。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码/退出码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 数据比例或哈希不符 | 不调用模型 | CLI 2 | `eval.invalid_dataset` |
| 真实引擎认证失败 | 中止并保留已产生预测 | `UNAUTHENTICATED` | `error.UNAUTHENTICATED` |
| 单样本超时 | 记 failed，继续下一条 | `TIMEOUT` | 报告中“超时 1 条” |
| cassette 缺失 | 中止 replay，不跳过 | CLI 4 | `eval.missing_cassette` |
| 基线环境变量缺失 | 只跑 Jev，报告 `baseline=not_run` | 退出 0 | `eval.baseline_not_configured` |
| F1 未达门槛 | 报告完整结果 | CLI 3 | `eval.gate_failed` |
| 输出目录已存在 | 新建时间戳子目录 | — | 不覆盖旧报告 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_dataset_has_exact_composition` | `test_dataset.py` | `dataset.jsonl` | 60；`22` 正、`38` 负；split 各 30 |
| `test_dataset_rejects_tuning_test_overlap` | 同上 | 复制一条 ID 到另一 split | `ValueError`，字段 `id` |
| `test_planned_sale_is_not_kill_met_positive` | 同上 | `eventState=planned` 且 label 标 `overturn` | 拒绝数据集；错误说明 kill_met 只允许 completed |
| `test_manifest_hash_change_is_rejected` | 同上 | 改一个字符 | 退出码 2 |
| `test_confusion_matrix_matches_hand_counted_example` | `test_metrics.py` | 5 条固定预测 | 矩阵 `[[2,0,0,0],[0,2,1,0]]`，F1 `0.8` |
| `test_wilson_interval_for_zero_success` | 同上 | `0/10` | 上界 `0.2775`（4 位） |
| `test_bootstrap_is_deterministic` | 同上 | 同一输入两次 | 区间完全相同 |
| `test_failed_prediction_is_not_counted_as_none` | `test_runner.py` | engine 抛 `MODEL_ERROR` | `failed=1`，混淆矩阵不增 |
| `test_replay_uses_no_network` | 同上 | `SENTINEL_OFFLINE=1` + cassette | 30 条完成，HTTP 调用 0 |
| `test_baseline_reports_calls_tokens_latency_cost` | `test_baselines.py` | 3 条固定响应 | `calls=3`、token 合计、p95 耗时、费用精确到 6 位 |
| `test_gate_fails_below_080` | `test_runner.py` | 严格 F1 `0.79` | `gate.passed=false`，退出 3 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `dataset.jsonl` | 60 对虚构逻辑与披露；22 正、38 负 | 两名成员独立标注后商定；不得用模型生成标签 |
| `manifest.json` | split、语言、子集、标签分布与 SHA-256 | 由离线 `--make-manifest` 生成后人工 review |
| `cassettes/*.json` | 至少 12 份固定答案，覆盖四类 | G0-JEV 录制后删除密钥与请求头 |
| `baseline_example.jsonl` | 3 条通用 LLM JSON 输出 | 手工构造，含 usage 与 latency |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd core && uv run pytest tests/unit/evaluation -q
# 期望：10 passed，0 failed
SENTINEL_OFFLINE=1 uv run --project core python ../scripts/eval.py --replay ../core/tests/fixtures/eval/cassettes --split test --out ../eval/reports/replay
# 期望：退出码 0；report.json 中 samples=30、strict.f1 有数值、positiveCount=11
uv run --project core python ../scripts/eval.py --split test --gate --out ../eval/reports/final
# 期望：达到门槛时退出 0；低于 0.80 时退出 3，report.md 首行含“门槛未通过”
scripts/check.sh
# 期望：失败 0
```

### 9.2 完成清单
- [ ] 数据集精确满足 §6 的 60/30/30、22:38、15/15 与子集计数；两名标注者、`adjudicated=true`、κ 已写入报告
- [ ] §8.1 的 10 个测试全部存在且通过；默认评测不需要网络，`--baseline` 缺环境时明确 `not_run`
- [ ] 报告不含密钥、Authorization 或真实个人信息；已写 `docs/wp/status/E-02.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| I-02 | `scripts/eval.py --replay`、`report.json` | MVP 验收固定用 `test` split 与 cassette |
| S-02 / S-05 | 预测行格式和失败计数 | 问题或阈值改变必须升 `question_set_version` 后重跑 |
| 课程报告 | 严格/宽松 F1、语言差、基线成本 | 必须同时报告样本数与置信区间 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 用测试集反复调参 | 同一数据哈希被多次评测 | 报告记录次数；改用调参集，测试集只做最终一次 |
| 通用 LLM 费用失控 | 60 对超出预算 | 默认关闭基线；只允许 test split 且上限 100 次调用 |
| 小样本 F1 波动大 | 区间宽于 0.2 | 如实报告；MVP-0 不据此宣称泛化能力 |

---
id: G0-JEV
title: 闸门探针：Jev 直连实测
phase: mvp0
platform: shared
lane: semantic
deps: [WP-00]
size: L
size_approval: cr/N10-01-execution-clarifications.md
owns: [scripts/probe_jev.py, scripts/tests/test_probe_jev.py, core/tests/fixtures/jev/]
appends: []
stubs: []
---

# G0-JEV 闸门探针：Jev 直连实测

## 0. 一眼看懂

- **目标**：用一份可重复执行的探针确认 Jev 的真实端点、模型、SDK 调用方式、错误状态、request id、token 用量、延迟、跨语言判定和证据句定位。探针输出机器可读报告与脱敏 cassette。
- **完成后解锁**：S-02 可以冻结问题集阈值与定价，S-03 可以按实测 SDK 接口实现直连引擎。
- **预计规模**：脚本约 220 行，单元测试约 120 行；不新增依赖，使用 WP-00 已锁定的 `httpx` 与 `typesafe-sdk`。

## 1. 背景与边界

### 1.1 为什么需要它
文档中的 SDK 细节目前来自官方文档，而不是本机实测。2026-11-02 对测试网关的请求已收到 HTTP 401 `Invalid token`，这只证明网关可达，**不能证明模型可用，更不能算闸门通过**。S-03 不允许在 SDK 构造参数、异常类型和重试行为上靠猜。

### 1.2 范围内
1. 校验 `GET /v1/models`（可配置端点）与一次 `POST /v1/systemone`。
2. 区分 401、403、429 与其他协议错误，记录来源请求 id，不记录密钥。
3. 测 5 个 Noul 的完整一次调用；20 次小请求的 p50/p95 延迟。
4. 对比打包多条逻辑与逐条请求；记录 token 实际值与“字符数 ÷ 3.5”的偏差。
5. 跑 5 个中文逻辑 × 英文披露、10 个证据定位样例，输出结果供人工复核。
6. 只把成功响应写成 cassette；认证失败写成不含请求正文的 blocked 报告。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 正式引擎、并发、批次事务 | S-03 |
| 修改问题文本、阈值、模型常量 | S-02（G0 只提出证据） |
| 修改 `decisions.md` 或任何设计文档 | 协调者按状态报告更新 |
| 压测生产账号、共享真实密钥 | 不做 |
| 用失败响应生成测试 cassette | 禁止 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | 2.1 Jev API、2.2 SDK、3.2–3.4、5、6.3、7.2、11 | 请求结构、问题集、证据、定价与待核实项 |
| [05-接口契约.md](../../05-接口契约.md) | 3.2 错误码、3.3 外部错误映射 | 401/403/429 的分类依据 |
| [09-测试与评测.md](../../09-测试与评测.md) | 2.3–2.4、9.3、9.5 | 假引擎、cassette、评测与注入样本 |
| [decisions.md](../../decisions.md) | 附录 G0-JEV | 必须填写的闸门结论 |

## 3. 前置条件

- WP-00 已合并；从仓库根可运行 `cd core && uv run python ../scripts/probe_jev.py`。
- 开发机设置 `JEV_ENDPOINT`（完整 URL，默认 `https://api.typesafe.ai/v1/systemone`）和 `JEV_API_KEY`。
- 可选 `JEV_MODEL`，默认 `jev-1.14.0`；拒绝 `jev-latest` 与 `jev-preview`。
- 当前已知网关 `https://pool.futureppo.top/v1/systemone` 对已提供的测试 key 返回 401。这里不保存该 key；执行者必须换一枚有效 key。
- 网络测试标记 `network`，默认测试不联网。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `scripts/probe_jev.py` | 新建 | 命令行、HTTP/SDK 探针、报告与 cassette 写入 |
| `scripts/tests/test_probe_jev.py` | 新建 | 用 `httpx.MockTransport` 覆盖 200/401/403/429/5xx/坏 JSON |
| `core/tests/fixtures/jev/e1_overturn.json` | 新建 | 06 §10 的虚构 E1 成功请求/响应 |
| `core/tests/fixtures/jev/e2_weaken.json` | 新建 | 虚构 `weaken` 成功样本 |
| `core/tests/fixtures/jev/e3_support_zh.json` | 新建 | 中文逻辑 × 英文披露成功样本 |
| `core/tests/fixtures/jev/e4_adversarial.json` | 新建 | 注入文本成功样本，只含虚构内容 |
| `core/tests/fixtures/jev/manifest.json` | 新建 | 每个 cassette 的模型、录制时间、请求哈希 |

## 5. 接口规格

### 5.1 公开接口
```python
@dataclass(frozen=True)
class ProbeConfig:
    endpoint: str
    api_key: str
    model: str
    timeout_sec: float = 30.0
    sample_size: int = 20
    output_dir: Path | None = None

def extract_request_id(headers: Mapping[str, str], body: object) -> tuple[str | None, str]: ...
def classify_probe_status(status: int) -> str: ...
def run_probe(config: ProbeConfig, *, client: httpx.Client, clock: Callable[[], datetime]) -> ProbeReport: ...
def write_report(report: ProbeReport, output_dir: Path) -> Path: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```
`main` 退出码：`0` 全部必测项通过；`2` 认证被拒（401/403）；`3` 限流且重试耗尽；`4` 端点或响应协议不符；`1` 本地参数、I/O 或未预期错误。401 与 403 都返回 2，但报告状态分别写 `AUTH_INVALID` 与 `AUTH_FORBIDDEN`。429 最多尝试 2 次，`Retry-After` 上限 5 秒，仍为 429 则退出 3。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `status` | str | 是 | `PASS/BLOCKED/FAILED` | 闸门结论，只有 PASS 可解锁 S-03 |
| `reason` | str | 是 | 枚举 | `AUTH_INVALID/AUTH_FORBIDDEN/RATE_LIMITED/...` |
| `http_status` | int \| None | 否 | 100–599 | 最后响应状态 |
| `request_id` | str \| None | 否 | ≤ 128 字符 | 来源 `x-request-id`、`request-id`、`cf-ray` 或 body `request_id/id` |
| `request_id_source` | str | 是 | `header:<名>/body:<名>/local` | 便于定位网关 |
| `model_requested` / `model_returned` | str | 是 | `jev-` 开头 | 配置模型与实际响应 |
| `checks` | list[dict] | 是 | 每项含 name/ok/detail | models、call、latency、tokens、pack、zh、evidence |
| `fixtures_written` | list[str] | 是 | 仓库相对路径 | 成功 cassette |
| `started_at` / `finished_at` | str | 是 | ISO 8601 UTC `Z` | 报告时刻 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `DEFAULT_ENDPOINT` | `https://api.typesafe.ai/v1/systemone` | `probe_jev.py` | 官方默认端点 |
| `DEFAULT_TIMEOUT_SEC` | `30.0` | 同上 | 当前探针为网络操作超时；总请求时限尚未验证，报告不得声称已验证 |
| `SAMPLE_SIZE` | `20` | 同上 | 延迟/token 对比样本数 |
| `MAX_RETRY_AFTER_SEC` | `5` | 同上 | 探针等待上限，不模拟生产长退避 |
| `YES` / `NO` | `0.7` / `0.3` | 同上 | 只用于报告分类，不改变问题 |

## 6. 实现步骤

1. 读取环境变量；`endpoint` 必须是 `https`，URL 不得包含用户名、密码或查询参数中的 key。缺少 key 时打印 `AUTH_INVALID missing JEV_API_KEY` 并返回 2。
2. 构造 `httpx.Client(timeout=30.0, follow_redirects=False)`；每次请求头只放 `Authorization: Bearer <key>` 与 `Content-Type: application/json`。日志和异常不得包含 headers。
3. 先 `GET {origin}/v1/models`，若 404 记 `models=SKIP` 但继续 POST；401/403 立即停止并写 blocked 报告；429 按 §5.1 重试。
4. POST 一个虚构 E1 请求：1 个段落、2 条逻辑，问题名固定为 `t1__relevant`、`t1__against`、`t1__contradicts`、`t1__kill_met`、`t1__supports` 与 `t2` 的 4 个问题。问题文本逐字来自 `docs/06` §3.3；本探针不另造措辞。
5. 成功条件：HTTP 200、`answers` 含全部问题键、每个 `noul` 是 `[0,1]` 有限数、`usage.input_tokens > 0`、`model` 以 `jev-` 开头。任一不满足记 `FAILED`，不得写 cassette。
6. 依次记录 401、403、429 的原始 `status`、`Content-Type`、request id 与最多 200 字的响应摘要；摘要先过 `redact_text`。401 不重试，403 不重试，429 仅按规则重试。
7. 延迟测试复用同一小请求，默认 20 次，记录每次 `duration_ms`，输出最近秩的 p50/p95。只对 200 响应计样本；少于 20 个样本时报告 `latency=INCOMPLETE`，闸门不得 PASS。
8. 打包对比：同一 E1 分别发送“2 条逻辑 × 4/5 题”和“每条逻辑单独请求”；比较 9 个概率的最大绝对差。差值 > 0.20 时在报告写 `pack_review=REQUIRED`，交 S-02 决定 `PACK_THESES`。
9. 中文样例与证据样例使用 06 §10 的虚构公司；证据请求只接收句子概率，不接受自由文本。人工复核结果写 `checks[].detail`，不自动改阈值。
10. 成功 cassette 只保存 `recorded_at`、`model`、`request`、`response`，删除 Authorization、Cookie、request id 和任何含 key 的字段；写前递归断言 key 原文不在序列化文本中。
11. 输出 `<output_dir>/g0-jev.json`；未指定目录时写 `SENTINEL_DATA_DIR/g0-jev/`。目录必须 `0o700`，报告文件 `0o600`。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码/报告 | 用户可见文案（messages 键） |
|---|---|---|---|
| 401 `Invalid token` | 立即停止，不重试，不算通过 | `AUTH_INVALID` / `UNAUTHENTICATED` | `error.UNAUTHENTICATED` |
| 403 | 停止；记录是否有 request id，提示权限或模型问题 | `AUTH_FORBIDDEN` / `UNAUTHENTICATED` | 同上，`detail` 区分 403 |
| 429 + `Retry-After` | 最多重试 2 次；等待上限 5 秒 | `RATE_LIMITED` | `error.RATE_LIMITED` |
| 5xx / 529 / 坏 JSON | 记 `MODEL_ERROR`，不写 cassette | `MODEL_ERROR` | `error.MODEL_ERROR` |
| 200 但缺答案或 `noul` 越界 | 视为响应契约失败 | `MODEL_ERROR` | `error.MODEL_ERROR` |
| request id 缺失 | 生成本地 `local-<ULID>`，明确标记来源 | 不算失败 | 不适用 |
| key 出现在报告 | 测试失败并拒绝落盘 | `INTERNAL` | 不适用（不得发生） |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_probe_401_is_blocked_and_not_recorded` | `scripts/tests/test_probe_jev.py` | Mock 401 + `x-request-id: req-1` | exit 2；`status=BLOCKED`；`reason=AUTH_INVALID`；无 cassette |
| `test_probe_403_is_distinct_from_401` | 同上 | Mock 403 | `reason=AUTH_FORBIDDEN`；仍 exit 2 |
| `test_probe_429_records_retry_after` | 同上 | 两次 429，`Retry-After: 2` | 请求 2 次；`retryAfterSec=2`；exit 3 |
| `test_probe_rejects_partial_answers` | 同上 | 200 缺 `t1__supports` | `MODEL_ERROR`；exit 4；无 cassette |
| `test_request_id_prefers_header_then_body_then_local` | 同上 | 三种响应 | 返回 `header:x-request-id`、`body:request_id`、`local` |
| `test_success_fixture_has_no_authorization_or_key` | 同上 | 200 完整响应 | cassette 可从 JSON 读取；序列化文本不含 `Authorization` 与测试 key |
| `test_classify_probe_status_maps_known_http_codes` | 同上 | 200/401/403/429/500 | `PASS/AUTH_INVALID/AUTH_FORBIDDEN/RATE_LIMITED/MODEL_ERROR` |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `core/tests/fixtures/jev/e1_overturn.json` | 06 §10 的虚构 E1，概率 0.97/0.89/0.84/0.93/0.03 | 首次有效 key 实测后录制，或先手写再以实测核对 |
| `e2_weaken.json` | 虚构监管问询导致逻辑削弱 | 实测录制；无有效 key 时保持缺失，不伪造 |
| `e3_support_zh.json` | 中文逻辑与英文回购段落 | 实测录制，用于跨语言报告 |
| `e4_adversarial.json` | 06 §8 的注入文本 | 实测录制，期望 `relevant < 0.3` |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd core && uv run pytest ../scripts/tests/test_probe_jev.py -q
# 期望：7 passed，0 failed

JEV_ENDPOINT="https://pool.futureppo.top/v1/systemone" JEV_API_KEY="<有效密钥>" \
  uv run python ../scripts/probe_jev.py --live --output ../.dev-data/g0-jev
# 期望成功：exit=0；status=PASS；checks 含 models/call/latency/tokens/pack/zh/evidence
# 当前测试 key 的已知结果：exit=2；status=BLOCKED；reason=AUTH_INVALID；http_status=401
```

### 9.2 完成清单
- [ ] 第 4 节脚本和 4 个成功 cassette 已交付；失败响应没有生成 cassette
- [ ] 第 8.1 节 7 个测试全部通过
- [ ] 401、403、429 的报告字段可区分，且 request id 有来源
- [ ] 401 从未被写成 PASS；报告不含密钥、Authorization 或 Cookie
- [ ] 已写 `docs/wp/status/G0-JEV.md`，闸门结论交给协调者更新 `decisions.md`
- [ ] `scripts/check.sh` 通过

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| S-02 | 实际模型 ID、`effective_from`、token 偏差、打包结论 | 只有 `status=PASS` 才能冻结参数；否则保持 `TODO-VERIFY(G0-JEV)` |
| S-03 | 实测 SDK 构造参数、异常导入路径、retry 行为、cassette | 以状态报告为准；不得从网络博客猜 API |
| E-02 | 中文/证据样例结果 | 只作调参证据，不把测试样例并入测试集 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 测试 key 仍被网关拒绝 | 401 `Invalid token` | 阻塞 S-02/S-03 的真实调用验收，保留全 mock 实现；换有效 key 后重跑 |
| 网关不支持 `/v1/models` | 404 | 记录 `models=SKIP`，以一次真实 POST 为准 |
| SDK 与 HTTP 探测行为不一致 | 同一 key 一成一败 | 以 SDK 为准实现，报告两种路径，交协调者裁定 |
| 录制内容含敏感文本 | 扫描发现邮箱/密钥/真实持仓 | 删除 cassette，改回虚构或裁剪数据后重录 |

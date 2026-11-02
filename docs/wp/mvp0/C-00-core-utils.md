---
id: C-00
title: 基础模块：ID、时钟、错误、日志、脱敏、文案
phase: mvp0
platform: shared
lane: core
deps: [WP-00]
size: S
owns: [core/sentinel/ids.py, core/sentinel/clock.py, core/sentinel/errors.py, core/sentinel/logging_setup.py, core/sentinel/security/__init__.py, core/sentinel/security/redact.py, core/sentinel/messages/, core/tests/unit/test_ids.py, core/tests/unit/test_clock.py, core/tests/unit/test_errors.py, core/tests/unit/test_logging_setup.py, core/tests/unit/test_redact.py, core/tests/unit/test_messages.py]
appends: []
stubs: []
---

# C-00 基础模块：ID、时钟、错误、日志、脱敏、文案

## 0. 一眼看懂

- **目标**：提供全仓库共用的六个底座：确定性 ID、统一时钟、15 个错误码与错误对象、结构化日志、脱敏、中文文案目录。它们没有业务逻辑，但所有后续代码都依赖。
- **完成后解锁**：C-01、C-03、C-05、D-01、D-02、P-04、S-01、S-02。
- **预计规模**：6 个实现模块约 250 行，6 个测试文件约 150 行；只使用标准库，不新增依赖。

## 1. 背景与边界

### 1.1 为什么需要它
ID、时间、错误码、日志格式一旦各写一套，合并后无法对账：同一错误在前端显示不同文案，同一时刻在不同机器上解释不同，密钥可能被写进日志。本包把这些约定一次性编码成可测试的模块。

### 1.2 范围内
1. `ids.py`：ULID 生成与解析、确定性 `passage_id`。
2. `clock.py`：UTC 当前时间、ISO 8601 解析与格式化、测试时钟。
3. `errors.py`：错误码枚举、四个错误族、`to_wire()`。
4. `logging_setup.py`：JSON Lines 日志、5 MB × 3 轮转、必填字段、写前脱敏。
5. `security/redact.py`：文本与对象的脱敏、进程内密钥登记。
6. `messages/`：文案目录、`render()`、15 个错误文案与应用生命周期文案。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| RPC 解析、分发、`$/cancel`、错误响应封装 | C-01 |
| 数据库、迁移、备份 | C-03 |
| 钥匙串读写（`security/secrets.py`） | 设置类工作包（不在本包 `owns`） |
| HTTP 重试、熔断、限流 | D-01 |
| 发给 Jev 的英文问题文本 | S-02（`semantic/questions.py`） |
| 前端文案与国际化 | U-00（`apps/desktop/src/i18n/`） |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | 3.1 业务 ID、3.3 语言、4 时间与数值、5 环境变量 | ID 格式、UTC 规则、`SENTINEL_CLOCK` |
| [02-技术架构.md](../../02-技术架构.md) | 11 日志与可观测性、12 稳定性设计、16 分层规则 | 日志字段、错误分层、`messages` 属于基础层 |
| [05-接口契约.md](../../05-接口契约.md) | 3.1 错误对象、3.2 错误码、3.3 外部错误映射 | `to_wire()` 的输出契约 |
| [09-测试与评测.md](../../09-测试与评测.md) | 2.1 命名与标记、2.2 确定性 | 测试命名、固定时钟 |

## 3. 前置条件

- WP-00 已合并：`core/pyproject.toml` 可运行 `uv run pytest`，`sentinel.logging_setup` 在分层白名单内（[WP-00](WP-00-skeleton.md) §5.4）。
- 仅用标准库：`hashlib`、`secrets`、`datetime`、`logging`、`logging.handlers`、`json`、`re`、`threading`、`collections.abc`。
- 不需要网络、密钥或数据库。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/ids.py` | 新建 | `new_id`、`is_ulid`、`ulid_to_timestamp_ms`、`passage_id` |
| `core/sentinel/clock.py` | 新建 | `now`、`parse_iso`、`to_iso`、`utc_today` |
| `core/sentinel/errors.py` | 新建 | `ErrorCode`、`RETRYABLE`、错误类、`to_wire` |
| `core/sentinel/logging_setup.py` | 新建 | `configure`、`get_logger`、`log_event`、`JsonFormatter` |
| `core/sentinel/security/__init__.py` | 新建 | 空文件，声明子包 |
| `core/sentinel/security/redact.py` | 新建 | `register_secret`、`clear_secrets`、`redact_text`、`redact_obj` |
| `core/sentinel/messages/__init__.py` | 新建 | 合并目录、`render`、`MessageKeyError`、`INTERNAL_FALLBACK` |
| `core/sentinel/messages/common.py` | 新建 | 15 个 `error.*` 文案、`MISSING_LABELS` |
| `core/sentinel/messages/app.py` | 新建 | `core.*` 生命周期文案 |
| `core/tests/unit/test_{ids,clock,errors,logging_setup,redact,messages}.py` | 新建 | §8.1 的测试 |

## 5. 接口规格

### 5.1 公开接口
```python
def new_id(*, timestamp_ms: int | None = None, entropy: bytes | None = None) -> str: ...
def is_ulid(value: str) -> bool: ...
def ulid_to_timestamp_ms(value: str) -> int: ...
def passage_id(event_id: str, file_seq: int, start: int, end: int) -> str: ...

def now() -> datetime: ...                     # 始终带 UTC 时区
def utc_today() -> date: ...
def to_iso(moment: datetime) -> str: ...        # "2026-11-02T00:35:00Z"
def parse_iso(value: str) -> datetime: ...      # 拒绝无时区的串

class SentinelError(Exception):
    def __init__(self, code: ErrorCode, message_key: str | None = None, *, params: Mapping[str, object] | None = None, field: str | None = None, reason: str | None = None, detail: str | None = None, retryable: bool | None = None) -> None: ...
    def to_wire(self, request_id: str | None = None) -> dict[str, object]: ...
class UserError(SentinelError): ...        # INVALID_ARGUMENT / NOT_FOUND / CONFLICT / CONFIG_REQUIRED / ORDER_REJECTED / DATA_INSUFFICIENT
class SourceError(SentinelError): ...      # SOURCE_UNAVAILABLE / RATE_LIMITED / TIMEOUT
class EngineError(SentinelError): ...      # UNAUTHENTICATED / ENGINE_UNAVAILABLE / MODEL_ERROR / BUDGET_EXCEEDED
class InternalError(SentinelError): ...    # INTERNAL
class CancelledError(SentinelError): ...   # CANCELLED

def configure(log_dir: Path, level: str = "info") -> None: ...
def get_logger(module: str) -> logging.Logger: ...
def log_event(logger: logging.Logger, level: int, *, event: str, request_id: str | None = None, method: str | None = None, duration_ms: int | None = None, error_code: str | None = None, **fields: object) -> None: ...
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str: ...

def register_secret(value: str) -> None: ...
def clear_secrets() -> None: ...
def redact_text(text: str) -> str: ...
def redact_obj(value: object, _depth: int = 0) -> object: ...

class MessageKeyError(Exception): ...
def render(key: str, params: Mapping[str, object] | None = None) -> str: ...
```
错误行为：`new_id` 的 `timestamp_ms ∉ [0, 2^48-1]` 或 `entropy` 不是 10 字节 → `ValueError`（调用方缺陷）；`is_ulid` 只返回布尔，不抛；`ulid_to_timestamp_ms` 对非法值 → `ValueError`；`passage_id` 的 `file_seq < 0` 或不在 `0 ≤ start < end` → `ValueError`；`to_iso`/`parse_iso` 对无时区或非法串 → `ValueError`；`SentinelError` 的 `code` 不属于该子类 → `ValueError`；`configure` 无法建目录或打开文件 → `InternalError("INTERNAL", detail=str(exc))`；`render` 缺键或缺参数 → `MessageKeyError`。全部函数线程安全；`configure` 在进程内只应调用一次，重复调用会替换 handler。

### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| ULID | 前 10 字符 | str | 是 | Crockford Base32，首字符 `0`–`7` | 48 位毫秒时间戳 |
| | 后 16 字符 | str | 是 | 同上 32 个字符 | 80 位随机数 |
| `passage_id` | — | str | 是 | 32 位小写十六进制 | `sha256` 摘要前 32 位 |
| 错误 `data` | `retryable` | bool | 是 | 见 §5.3 | 是否值得重试 |
| | `field` / `reason` / `detail` | str | 否 | `detail` 只放英文技术细节 | 诊断信息 |
| | `requestId` | str | INTERNAL 必填 | 与日志 `request_id` 相同 | 错误编号 |
| 日志记录 | `ts` `level` `module` `request_id` `method` `duration_ms` `error_code` | 混合 | 是 | 缺省写 `null`；`ts` 为 `to_iso(clock.now())` | 检索与关联 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `CROCKFORD` | `"0123456789ABCDEFGHJKMNPQRSTVWXYZ"` | `ids.py` | ULID 字母表，无 `I L O U` |
| `MAX_TIMESTAMP_MS` | `281474976710655` | `ids.py` | `2^48 - 1` |
| `RETRYABLE` | 5 个 true：`SOURCE_UNAVAILABLE` `RATE_LIMITED` `MODEL_ERROR` `TIMEOUT` `INTERNAL`；其余 10 个 false | `errors.py` | 与 [05](../../05-接口契约.md) §3.2 一致；`CANCELLED` 为 false |
| `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` | `5242880` / `3` | `logging_setup.py` | 5 MB × 3 轮转 |
| `MAX_REDACT_DEPTH` | `8` | `redact.py` | 对象递归上限，超过后返回 `"<max-depth>"` |
| `MASK` | `"***REDACTED***"` | `redact.py` | 统一占位符 |
| `INTERNAL_FALLBACK` | `"发生了意外错误，请重试。"` | `messages/__init__.py` | 文案缺失时的兜底 |

## 6. 实现步骤

1. **ULID**：取 `ts`（缺省时用 `(clock.now() - EPOCH) // 1ms`）与 10 字节熵；组成整数 `(ts << 80) | int.from_bytes(entropy, "big")`；从低位起每 5 位查 `CROCKFORD`，共 26 次后反转。解析时把 26 个字符还原成整数，右移 80 位得到毫秒。
2. **`passage_id`**：`payload = f"{event_id}|{file_seq}|{start}|{end}"`，返回 `sha256(payload.encode("utf-8")).hexdigest()[:32]`，不做大小写转换。
3. **时钟**：`now()` 读取 `SENTINEL_CLOCK`；未设置时返回 `datetime.now(timezone.utc)`；已设置时走 `parse_iso` 并转 UTC。`parse_iso` 要求 `tzinfo is not None`，把 `+08:00` 规范化为 UTC。
4. **错误**：`to_wire()` 组装 `{"code", "message", "data"}`；`message` 由 `messages.render(message_key or f"error.{code}", params)` 生成；`MessageKeyError` 时改用 `INTERNAL_FALLBACK` 并把 `data.detail` 设为 `f"missing message: {key}"`；`INTERNAL` 且 `request_id is None` → `ValueError`。
5. **日志**：`configure` 在 `sentinel` logger 上设 `propagate=False`，清空旧 handler，再加 `StreamHandler(stderr)` 与 `RotatingFileHandler(log_dir/"core.jsonl", maxBytes=LOG_MAX_BYTES, backupCount=3, encoding="utf-8")`；级别取 `debug/info/warn/error`，未知值降为 `info` 并写一条 `config.log_level_invalid`。
6. **日志行**：`log_event` 把 `event`、六个字段与 `fields` 放进 `record.sentinel`；`JsonFormatter` 取 `clock.now()` 生成 `ts`，输出 `json.dumps(payload, ensure_ascii=False, separators=(",", ":"))` 后再经 `redact_obj`，异常时序列化为 `"<unserializable>"`。
7. **脱敏顺序**：① 已登记密钥按长度降序做字面替换；② `sk-[A-Za-z0-9_-]{8,}`；③ `(?i)bearer\s+[A-Za-z0-9._~+/-]+=*` 保留 `Bearer ` 前缀；④ `\b[0-9a-fA-F]{32,}\b`；⑤ 对象里键名匹配 `(?i)(api[_-]?key|token|secret|password|authorization|cookie)` 的值整体替换。
8. **文案**：`__init__` 用 `common.MESSAGES | app.MESSAGES` 合并；`render` 用 `template.format_map(defaultdict(str, params))`——缺参数即抛 `MessageKeyError`，不得输出半截文案。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 参数缺失或非法 | 调用方构造 `UserError` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT`：“填写的内容不正确，请检查后重试。” |
| 缺 Jev 密钥或 SEC 邮箱 | `data.missing` 列出 `jevKey` / `secEmail` | `CONFIG_REQUIRED` | `error.CONFIG_REQUIRED`：“还需要完成设置：{missing}。” |
| 脱敏后仍含已登记密钥 | 视为缺陷，测试失败 | — | 不适用（不得发生） |
| `render` 未知键 | 返回兜底并写 `detail` | `INTERNAL` | `INTERNAL_FALLBACK` |
| 日志目录不可写 | 启动期失败，不静默吞掉 | `INTERNAL` | `error.INTERNAL`：“发生了意外错误，请复制错误编号 {requestId} 并重试。” |
| `SENTINEL_CLOCK` 非法 | 抛 `ValueError`，进程启动失败 | `INTERNAL` | `error.INTERNAL` |
| 空字符串密钥登记 | 忽略，不加入集合 | — | 不适用 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_new_id_with_fixed_entropy_returns_expected_ulid` | `core/tests/unit/test_ids.py` | `timestamp_ms=1700000000000`, `entropy=b"\x00"*10` | `"01HF7YAT000000000000000000"` |
| `test_new_id_round_trips_timestamp` | 同上 | 同上 | `ulid_to_timestamp_ms(...) == 1700000000000`；`len == 26` |
| `test_ulid_rejects_out_of_range_timestamp` | 同上 | `timestamp_ms=281474976710656` | `ValueError` |
| `test_passage_id_is_stable_and_32_hex` | 同上 | `("us:0001234567-26-000123", 1, 0, 120)` | `"e4d8d292502f3875926ca657013c0720"` |
| `test_now_reads_sentinel_clock` | `core/tests/unit/test_clock.py` | 环境变量 `2026-11-02T08:35:00+08:00` | `2026-11-02T00:35:00+00:00` |
| `test_parse_iso_rejects_naive_datetime` | 同上 | `"2026-11-02T00:35:00"` | `ValueError` |
| `test_to_iso_always_ends_with_z` | 同上 | `datetime(2026,11,2,0,35,tzinfo=timezone.utc)` | `"2026-11-02T00:35:00Z"` |
| `test_internal_error_wire_requires_request_id` | `core/tests/unit/test_errors.py` | `InternalError(); to_wire()` | `ValueError` |
| `test_source_error_wire_marks_retryable` | 同上 | `SourceError("SOURCE_UNAVAILABLE"); to_wire("r-1")` | `data == {"retryable": True}`，`message` 含“数据源” |
| `test_log_line_is_single_json_object_with_required_fields` | `core/tests/unit/test_logging_setup.py` | `configure(tmp_path)`, `log_event(..., event="scan.start", request_id="r-1")` | 文件 1 行；JSON 含 §5.2 的 7 个键；`error_code is None` |
| `test_log_never_contains_registered_secret` | 同上 | `register_secret("sk-test-do-not-use-1234")`；`log_event(..., note=secret)` | 文件内容不含该串，含 `***REDACTED***` |
| `test_redact_text_masks_sk_and_bearer` | `core/tests/unit/test_redact.py` | `"key sk-abcdefgh12345678 header Bearer abc.def"` | `"key ***REDACTED*** header Bearer ***REDACTED***"` |
| `test_redact_obj_masks_sensitive_keys_and_is_cycle_safe` | 同上 | `{"apiKey": "x", "n": {"token": "y"}}` 加自引用字典 | 两个值均为 `MASK`；不抛 `RecursionError` |
| `test_render_fills_placeholders` | `core/tests/unit/test_messages.py` | `render("error.RATE_LIMITED", {"retryAfterSec": 30})` | 含 `30` |
| `test_render_unknown_key_raises_message_key_error` | 同上 | `render("error.NOPE")` | `MessageKeyError` |
| `test_every_error_code_has_message` | 同上 | 遍历 `ErrorCode` 的 15 个取值，提供文案所需参数 | 全部 `render(f"error.{code}", params)` 成功；缺少模板参数必须抛错 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增 fixture 文件 | 所有输入在测试内构造；日志写入 `tmp_path` | 不需要录制数据 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd "core" && uv run pytest tests/unit/test_ids.py tests/unit/test_clock.py tests/unit/test_errors.py tests/unit/test_logging_setup.py tests/unit/test_redact.py tests/unit/test_messages.py -q
# 期望：16 passed，0 failed
scripts/check.sh
# 期望：exit=0；ruff、mypy 对 sentinel/ 全绿
```

### 9.2 完成清单
- [ ] 第 4 节每个文件都已创建，`security/__init__.py` 与 `messages/__init__.py` 非空规则见 §5
- [ ] 第 8.1 节 16 个测试全部存在且通过
- [ ] `scripts/check.sh` 全绿
- [ ] 未修改 `owns` 之外的文件；未新增依赖
- [ ] 已写 `docs/wp/status/C-00.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| C-01 | `SentinelError.to_wire()`、`CancelledError`、`get_logger` | 每个请求一个 `request_id`；`INTERNAL` 必须带它 |
| C-03 | `new_id()`、`clock.now()`、`InternalError` | 实体主键一律 ULID，时间一律 UTC |
| C-05 | `ErrorCode`、`retryable` 表 | 生成 TypeScript 类型时以本模块为唯一来源 |
| D-01 / D-02 | `SourceError`、`RATE_LIMITED` 的 `retryAfterSec` | 重试策略留在 HTTP 层，本包不做 |
| 所有后端工作包 | `messages.render()`、`register_secret()` | 新文案写入 `messages/<域>.py` 前，先向协调者申请 `owns` 变更 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 其他工作包争用 `messages/` 目录 | 两个分支各建 `messages/settings.py` | 协调者把新文件指派给对应工作包，C-00 只保留 `__init__`、`common`、`app` |
| 32 位十六进制规则误伤 `passage_id` | 日志里证据 ID 变成占位符 | 已知代价，按 [02](../../02-技术架构.md) §11 接受；证据 ID 从数据库取，不依赖日志 |
| 测试环境已有 root handler 造成重复行 | 一条日志出现两次 | `configure` 使用独立 `sentinel` logger 且 `propagate=False` |

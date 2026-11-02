---
id: D-01
title: HTTP 基础设施：重试、熔断、限速、缓存
phase: mvp0
platform: shared
lane: data
deps: [C-00]
size: M
owns: [core/sentinel/http/, core/tests/unit/http/, core/tests/fixtures/http/]
appends: []
stubs: []
---

# D-01 HTTP 基础设施：重试、熔断、限速、缓存

## 0. 一眼看懂

- **目标**：给 SEC、腾讯、纳斯达克提供同一个 HTTP 客户端，把超时、三次尝试、5 次失败熔断、令牌桶限速、条件缓存、编码回退、5 MB 上限、取消检查一次性实现。
- **完成后解锁**：D-02、D-03、D-04，以及 v1 的汇率源。
- **预计规模**：6 个实现模块约 420 行，5 个测试文件约 380 行；这是唯一直接使用 `httpx` 的模块。

## 1. 背景与边界

### 1.1 为什么需要它
三个数据源的失败方式不同，但调用方不应该各自实现退避与熔断。HTTP 层必须让“SEC 被限流”只影响 SEC，“腾讯变慢”不会拖垮核心进程，并且所有错误都映射到统一错误码。

### 1.2 范围内
1. `SourcePolicy` 与策略注册表。
2. 每次网络尝试连接 5 秒、读取 20 秒、总计 30 秒的超时；重试等待单独计时并可取消。
3. 三次尝试与 1、2、4 秒退避，乘 0.5 到 1.0 的随机系数。
4. `Retry-After` 优先、上限 60 秒。
5. 每来源独立熔断：连续 5 次失败打开 10 分钟，半开只放 1 个请求。
6. 每来源独立令牌桶，SEC 为 5 次每秒、容量 5。
7. `GET` 条件缓存（键 `sha256(url)`）、编码回退、5 MB 截断、`CancelToken` 检查、结构化日志。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| SEC 字段解析、URL 拼接 | D-02、D-03、D-04 |
| 行情行序与 `$` 前缀处理 | D-04 |
| 后台定时刷新、代理设置、响应正文日志 | P-02、v1 设置页、不做 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [07-美股数据源.md](../../07-美股数据源.md#3-http-客户端d-01) | §3 HTTP 客户端 | 全部数值的唯一来源 |
| [05-接口契约.md](../../05-接口契约.md#33-外部错误到错误码的映射) | §3.3 外部错误映射 | 状态码到错误码 |
| [02-技术架构.md](../../02-技术架构.md#11-日志与可观测性) | §11 日志 | 必填日志字段 |

## 3. 前置条件

- C-00 提供 `SentinelError`、`SourceError`、`UserError`、`CancelledError`、`ErrorCode`、`register_secret`、`get_logger`。
- WP-00 已安装 `httpx`；不得引入 `requests`、`aiohttp`、`tenacity`。
- 测试使用 `httpx.MockTransport`，不联网。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/http/__init__.py` | 新建 | 导出 `HttpClient`、`HttpResponse`、`SourcePolicy`、`POLICIES` |
| `core/sentinel/http/policy.py` | 新建 | 策略数据类、默认策略、按来源注册与查询 |
| `core/sentinel/http/retry.py` | 新建 | 可重试判定、退避计算、`Retry-After` 解析 |
| `core/sentinel/http/breaker.py` | 新建 | `CircuitBreaker` 状态机与线程安全计数 |
| `core/sentinel/http/ratelimit.py` | 新建 | `TokenBucket.acquire(timeout_s)` |
| `core/sentinel/http/cache.py` | 新建 | `HttpCache`：键、主体、元数据、304 复用 |
| `core/sentinel/http/client.py` | 新建 | `HttpClient` 主流程与 `CancelToken` 协议 |
| `core/tests/unit/http/test_{retry,breaker,ratelimit,cache,client}.py` | 新建 | §8.1 的测试 |

## 5. 接口规格

### 5.1 公开接口
```python
@dataclass(frozen=True)
class SourcePolicy:
    name: str
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 20.0
    total_timeout_s: float = 30.0
    max_attempts: int = 3
    backoff_s: tuple[float, ...] = (1.0, 2.0, 4.0)
    jitter: tuple[float, float] = (0.5, 1.0)
    rate_per_s: float | None = None
    burst: int = 0
    rate_wait_max_s: float = 30.0
    cache_enabled: bool = False
    max_bytes: int = 5_242_880

@dataclass(frozen=True)
class HttpResponse:
    status: int; headers: Mapping[str, str]; content: bytes; text: str
    from_cache: bool; attempts: int; elapsed_ms: int

class CancelToken(Protocol):
    def is_cancelled(self) -> bool: ...

class HttpClient:
    def __init__(self, *, cache_dir: Path | None = None, transport: httpx.BaseTransport | None = None, on_degraded: Callable[[str, float], None] | None = None, sleeper: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic, uniform: Callable[[float, float], float] = random.uniform) -> None: ...
    def get(self, url: str, *, source: str, headers: Mapping[str, str] | None = None, cancel: CancelToken | None = None, use_cache: bool | None = None) -> HttpResponse: ...
    def get_text(self, url: str, *, source: str, **kwargs: object) -> str: ...
    def get_json(self, url: str, *, source: str, **kwargs: object) -> object: ...

class CircuitBreaker:
    def __init__(self, *, failure_threshold: int = 5, open_seconds: float = 600.0, monotonic: Callable[[], float] = time.monotonic) -> None: ...
    def allow(self) -> bool: ...
    def record_success(self) -> None: ...
    def record_failure(self, *, force_open: bool = False) -> None: ...
    @property
    def state(self) -> Literal["closed", "open", "half_open"]: ...

def register_policy(policy: SourcePolicy) -> None: ...
def get_policy(name: str) -> SourcePolicy: ...
```
`get` 在发请求前检查 `cancel.is_cancelled()`，为真时抛 `CancelledError`；超时抛 `SourceError("TIMEOUT")`；SEC 403 抛 `SourceError("SOURCE_UNAVAILABLE", reason="SEC_FORBIDDEN")` 并立刻打开熔断；429 抛 `SourceError("RATE_LIMITED", params={"retryAfterSec": n})`；其余 5xx 重试耗尽后抛 `SOURCE_UNAVAILABLE`；4xx（429 除外）不重试，抛 `SOURCE_UNAVAILABLE`，`reason` 为 `HTTP_<status>`。所有公开方法线程安全。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `SourcePolicy.max_attempts` | int | 是 | 1 到 4 | 含首次请求的总尝试数 |
| `SourcePolicy.backoff_s` | tuple | 是 | 每个值 > 0 | 第 n 次重试前取第 n 个值 |
| `HttpResponse.status` / `content` / `text` | int / bytes / str | 是 | 状态码 100 到 599；正文 ≤ 5 MB | 原始响应与解码文本 |
| `HttpResponse.from_cache` | bool | 是 | — | 304 或命中缓存 |
| `cache/<key>.meta.json` | dict | 是 | 含 `url`、`etag`、`last_modified`、`fetched_at` | 条件请求元数据 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `DEFAULT_MAX_ATTEMPTS` / `BACKOFF_SECONDS` | `3` / `(1.0, 2.0, 4.0)` | `policy.py` / `retry.py` | 三次尝试，实际使用前两个退避值 |
| `FAILURE_THRESHOLD` / `OPEN_SECONDS` | `5` / `600.0` | `breaker.py` | 连续 5 次失败后熔断 10 分钟 |
| `SEC_RATE_PER_S` / `SEC_BURST` | `5.0` / `5` | `policy.py` | SEC 全局限速 |
| `MAX_RETRY_AFTER_S` | `60.0` | `retry.py` | `Retry-After` 上限 |
| `MAX_BYTES` | `5242880` | `policy.py` | 单响应 5 MB |

## 6. 实现步骤

1. `POLICIES` 预置 `sec`：`rate_per_s=5.0`、`burst=5`、`cache_enabled=True`；`tencent` 与 `nasdaq` 使用默认 20 秒读取、30 秒总时限。D-04 可注册 tencent 的 30 秒读取覆盖；未知来源使用默认策略并 `warn` 一次。
2. 每次 `get`：取策略 → `breaker.allow()`，否则抛 `SOURCE_UNAVAILABLE`、`reason="CIRCUIT_OPEN"` → 取令牌（等待超过 30 秒抛 `TIMEOUT`）→ 检查 `cancel` → 构造请求；每次重试前都重新检查。
3. 缓存：仅 `GET` 且 `cache_enabled`。键 `sha256(url.encode()).hexdigest()`；正文使用 `<key>.<body_sha256>.body` 的不可变文件，原子发布 `.meta.json` 清单后才清理该 URL 的旧正文，避免新正文配旧验证器。读取快照持有正文 bytes，更新后删除旧文件不影响正在执行的 304。无任何验证器时不写缓存。
4. 发送：用 `client.stream("GET", ...)` 读取最多 5 MB；用 `monotonic` 限定每次网络尝试总计 30 秒；令牌等待与可取消的重试等待单独计时。超过上限截断并 `warn`。304 时使用已读取的缓存快照并返回 `from_cache=True`；缓存缺失时无条件重新请求。
5. 可重试：429、500 到 599（含 529）、`ConnectError`、`ReadTimeout`、`ConnectTimeout` 为真；其他 4xx 为假。第 n 次重试用 `backoff_s[n-1] * uniform(0.5, 1.0)`；有 `Retry-After` 时取 `max(backoff, retry_after)` 并截到 60 秒；HTTP 日期格式按 0 处理并 `warn`。
6. 熔断计数：重试耗尽记 1 次失败；成功记成功；closed 状态的非 429 普通 4xx 不计数，half_open 探测的任意失败重新打开；SEC 403 立即 `record_failure(force_open=True)`；打开时发 `source.degraded` 通知回调，回调异常只记日志。
7. 编码：优先 `response.encoding`；缺失时依次 `utf-8`、`windows-1252`；全部失败抛 `SOURCE_UNAVAILABLE`、`reason="DECODE_FAILED"`。
8. 日志：字段 `source`、`method`、`url`（去掉查询串中的 `token`、`key`、`apikey`）、`status`、`duration_ms`、`attempts`、`from_cache`；不记录响应体。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 离线或熔断打开 | 不发请求 | `SOURCE_UNAVAILABLE` | `error.SOURCE_UNAVAILABLE` |
| SEC 403 | 立即熔断 10 分钟 | `SOURCE_UNAVAILABLE` | `error.SOURCE_UNAVAILABLE`，`reason=SEC_FORBIDDEN` |
| 429；令牌或读取超时 | 重试后仍失败；放弃 | `RATE_LIMITED` / `TIMEOUT` | `error.RATE_LIMITED` / `error.TIMEOUT` |
| 解码失败或缓存损坏 | 不返回半截文本；损坏缓存删除后重取 | `SOURCE_UNAVAILABLE` / — | `error.SOURCE_UNAVAILABLE` |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_retry_stops_after_three_attempts` | `core/tests/unit/http/test_retry.py` | 连续 503 | `attempts == 3`；`sleep` 调用两次，值在 `[0.5,1.0]` 与 `[1.0,2.0]` |
| `test_retry_honors_retry_after_and_skips_405` | 同上 | 429 加 `Retry-After: 120`；405 | 等待 `60.0`；405 的 `attempts == 1` |
| `test_breaker_opens_after_five_failures` | `core/tests/unit/http/test_breaker.py` | 5 次 `record_failure` | `state == "open"`；`allow() is False` |
| `test_breaker_half_open_then_closes` | 同上 | 推进 601 秒，探测成功 | 第一次 `allow()` 真、第二次假；成功后 `state == "closed"` |
| `test_token_bucket_limits_and_times_out` | `core/tests/unit/http/test_ratelimit.py` | 容量 5；等待上限 0.1 秒 | 第 6 次等待 `1.0` 秒；超限抛 `SourceError("TIMEOUT")` |
| `test_cache_reuses_body_on_304` | `core/tests/unit/http/test_cache.py` | 首次 200 加 `ETag`，再次 304 | 第二次 `from_cache is True`，正文等于首次 |
| `test_client_maps_403_to_sec_forbidden_and_opens_breaker` | `core/tests/unit/http/test_client.py` | SEC 403 | `reason=SEC_FORBIDDEN`；紧接着第二次请求未发出 |
| `test_client_truncates_five_mb_body` | 同上 | 6 MB 响应 | `len(content) == 5_242_880` |
| `test_client_decodes_cp1252_when_header_missing` | 同上 | 字节 `0x93hi0x94` | `text` 含弯引号，不抛错 |
| `test_client_cancel_and_offline_skip_transport` | 同上 | 已取消；`SENTINEL_OFFLINE=1` | `CancelledError` / `reason=OFFLINE`，transport 均未调用 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `core/tests/fixtures/http/error_429_retry_after_2.http` | 429 响应头；503 页同目录 | 手写 |
| `core/tests/fixtures/http/etag_304.json` | 首次 200 与 304 的元数据 | 手写 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd "/Users/lijiaxuan/Documents/ChatGPT/JEV Stocks/core"
uv run pytest tests/unit/http -q
# 期望：10 passed，0 failed
cd .. && scripts/check.sh
# 期望：exit=0；ruff 与 mypy 对 sentinel/http 全绿
```

### 9.2 完成清单
- [ ] 第 4 节 8 个文件全部创建；10 个测试通过；无网络访问；日志不含正文与密钥；已写状态文件

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| D-02 / D-03 / D-04 / P-02 | `get_json`、`get_text`、来源策略、`source.degraded` 回调 | 未填邮箱先抛 `CONFIG_REQUIRED`；403 本层熔断；D-04 注册腾讯 30 秒覆盖 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| MockTransport 不兼容或熔断误伤 | 测试挂起；10 分钟内全部失败 | 用 `content=` 构造响应；半开成功即关闭 |

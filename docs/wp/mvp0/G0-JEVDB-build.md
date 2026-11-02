---
id: G0-JEVDB
title: 闸门探针：macOS 构建并加载 JEVDB
phase: mvp0
platform: macos
lane: semantic
deps: [WP-00]
size: M
owns: [scripts/probe_jevdb.py, scripts/build_jevdb.sh, scripts/build_jevdb.ps1, scripts/tests/test_probe_jevdb.py, scripts/tests/test_build_jevdb.py, vendors/jevdb/]
appends: []
stubs: []
---

# G0-JEVDB 闸门探针：macOS 构建并加载 JEVDB

## 0. 一眼看懂

- **目标**：在 macOS arm64、DuckDB 1.4.3 上从固定源码构建 JEVDB 0.1.0，静态链接 OpenSSL，用 `allow_unsigned_extensions` 加载，并实测 `jev_probability` 与 `jev_keys_overlap`。
- **完成后解锁**：S-04。通过则实现完整 JEVDB 引擎；失败则 S-04 只保留接口、SQL 生成与降级测试，产品使用 `jev_direct`。
- **预计规模**：两个脚本约 260 行，两个测试文件约 120 行；源码和构建产物不提交，只提交 pin、脚本与报告。

## 1. 背景与边界

### 1.1 为什么需要它
PyPI `jevdb 0.1.0` 只有 Linux x86-64 wheel，macOS 必须从源码编译。JEVDB 又是研究代码，扩展 ABI、OpenSSL 链接和未签名加载都可能失败。这个闸门先用最小成本证伪，避免 S-04 建立在不可用组件上。

### 1.2 范围内
1. 把 JEVDB 固定到审核过的 commit，并记录 DuckDB、许可证、源码 URL 与 SHA256。
2. 下载 DuckDB 1.4.3 与 JEVDB 源码到 `.dev-data/jevdb/`，调用上游 `scripts/build.sh`。
3. 构建 `jevdb.duckdb_extension`，优先静态链接 OpenSSL，计算扩展 SHA256。
4. Python 探针用专用内存连接加载扩展，调用 `jev_probability` 与 `jev_keys_overlap`，记录加载耗时和 `jevdb_stats()`。
5. 用无效 key 验证失败模式；用有效 key 验证真实概率。失败必须中止查询，不能变成 `false`/`NULL`。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| JEVDB 引擎的 SQL 生成与 Protocol 实现 | S-04 |
| Windows/MSVC 构建 | W-03 |
| 修改 DuckDB 版本或仓库内其他依赖 | 不做；需要时提 CR |
| 把上游源码、dylib 或构建目录提交仓库 | 禁止 |
| 用 `jevdb_on_error='reject'` 掩盖失败 | 禁止 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | 2.3 JEVDB、6.4 连接与查询、6.5 缓存 | 加载参数、设置、函数和失败语义 |
| [02-技术架构.md](../../02-技术架构.md) | 4 依赖、7.3 连接隔离、12 稳定性 | DuckDB 版本和专用连接 |
| [05-接口契约.md](../../05-接口契约.md) | 3.2–3.3 | `ENGINE_UNAVAILABLE`/`UNAUTHENTICATED`/`MODEL_ERROR` |
| [decisions.md](../../decisions.md) | ADR-008、G0-JEVDB 附录 | 通过/失败后的产品决策 |

## 3. 前置条件

- macOS arm64，WP-00 已安装 `uv`；`duckdb` Python 包必须为 1.4.3。
- 已有 C++17 编译器、CMake ≥ 3.16、Ninja、Git。OpenSSL 头文件和静态库需已安装；脚本只检测，不自动安装。
- 可访问 `codeload.github.com`。构建约需 2 GB 临时磁盘、10–20 分钟。
- 真实调用需要 `JEV_API_KEY`；没有 key 时可以完成 build/load，但 G0 结论只能是 `BLOCKED`。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `scripts/build_jevdb.sh` | 新建 | 校验工具、下载固定源码、构建、写 lock 文件与 SHA256 |
| `scripts/build_jevdb.ps1` | 新建 | macOS 车道使用的成对占位；打印“Windows 构建由 W-03 负责”并 exit 1 |
| `scripts/probe_jevdb.py` | 新建 | 加载扩展、执行函数、记录耗时/SHA/错误 |
| `scripts/tests/test_build_jevdb.py` | 新建 | 测 URL/pin/工具检查与静态库诊断，不真正编译 |
| `scripts/tests/test_probe_jevdb.py` | 新建 | 用假连接测 SQL、设置、错误映射与报告 |
| `vendors/jevdb/README.md` | 新建 | 上游来源、MIT 许可证、构建边界、复现命令 |
| `vendors/jevdb/pin.json` | 新建 | `commit=47a9070cba09012bedcc60f5e47e09ccb5c2c1fe`、DuckDB 1.4.3、源码 URL |
| `vendors/jevdb/build.lock.json` | 生成 | 扩展 SHA256、OpenSSL 路径、构建时刻、工具版本 |

## 5. 接口规格

### 5.1 公开接口
```python
@dataclass(frozen=True)
class BuildPin:
    source_url: str
    commit: str
    duckdb_version: str
    extension_version: str

def load_pin(path: Path) -> BuildPin: ...
def build_plan(pin: BuildPin, work_dir: Path, openssl_prefix: Path) -> list[list[str]]: ...
def sha256_file(path: Path) -> str: ...
def run_probe(extension_path: Path, *, connect: Callable[..., object], env: Mapping[str, str], clock) -> dict[str, object]: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```
`main` 退出码：`0` BUILD_LOAD_CALL 全通过；`2` 构建/加载成功但认证被拒；`3` 构建失败；`4` 加载或 ABI 失败；`1` 参数/本地错误。`build_jevdb.sh` 成功时最后一行打印扩展绝对路径，失败时打印首个失败命令与日志路径。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `build.status` | str | 是 | `PASS/FAILED/SKIPPED` | 是否产出扩展 |
| `load.status` | str | 是 | `PASS/FAILED` | `LOAD` 是否成功 |
| `call.status` | str | 是 | `PASS/BLOCKED/FAILED` | 语义函数结果 |
| `extension_sha256` | str | 是 | 64 位小写十六进制 | 构建产物身份 |
| `load_ms` | int | 是 | ≥ 0 | 从 `connect` 到 `LOAD` 完成 |
| `duckdb_version` | str | 是 | 必须 `1.4.3` | ABI 对齐 |
| `request_id` | str \| None | 否 | ≤ 128 字符 | 远端错误可关联值 |
| `stats` | dict | 否 | `jevdb_stats()` 原值 | 请求数、重试数、去重输入数 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `JEVDB_COMMIT` | `47a9070cba09012bedcc60f5e47e09ccb5c2c1fe` | `pin.json` | 2026-11-02 核对的 `main` |
| `DUCKDB_VERSION` | `1.4.3` | `pin.json`、`probe_jevdb.py` | 唯一支持的 ABI |
| `JEVDB_VERSION` | `0.1.0` | `pin.json` | 上游扩展版本 |
| `MAX_WORK_DIR_BYTES` | `2147483648` | `build_jevdb.sh` | 2 GiB 预检阈值 |
| `LOAD_TIMEOUT_SEC` | `30` | `probe_jevdb.py` | 本地加载上限 |

## 6. 实现步骤

1. `build_jevdb.sh` 检查 `uname -sm == Darwin arm64`、`cmake`、`ninja`、`git`、`cc`、`duckdb` Python 版本和 OpenSSL 静态库；任一缺失打印安装建议并返回 3，不自行安装。
2. 在 `.dev-data/jevdb/` 下创建 `dependencies/`、`src/`、`logs/`。若源码不存在，下载 `https://codeload.github.com/PDAIS/JEVDB/tar.gz/47a9070cba09012bedcc60f5e47e09ccb5c2c1fe`，解压后断言 `LICENSE` 的 SPDX 是 MIT。
3. 下载 `https://codeload.github.com/duckdb/duckdb/tar.gz/refs/tags/v1.4.3` 到 `build/dependencies/duckdb-v1.4.3.tar.gz`，校验解压目录名为 `duckdb-1.4.3`。
4. 调用上游 `bash scripts/build.sh -DOPENSSL_ROOT_DIR=<prefix> -DOPENSSL_USE_STATIC_LIBS=ON`，stdout/stderr 写 `logs/build.log`；只接受产物 `build/release/extension/jevdb/jevdb.duckdb_extension`。
5. 记录 `shasum -a 256`、`cmake --version` 首行、`ninja --version`、`cc --version` 首行、OpenSSL 路径到 `build.lock.json`；文件所有者只读权限 `0o600`。
6. `probe_jevdb.py` 校验 Python `duckdb.__version__ == 1.4.3`，创建 `duckdb.connect(":memory:", config={"allow_unsigned_extensions": "true"})`。
7. 执行 `LOAD '<绝对路径>'`。路径用绑定参数不支持 `LOAD`，所以先断言路径不含 `'`、换行和 NUL；以单引号转义后执行。加载失败按 4 退出。
8. 执行 `CREATE SECRET jev (TYPE jev, PROVIDER env)`，只建临时 secret；依次设置 `jevdb_backend=jev`、`jevdb_model=jev-1.14.0`、`jevdb_threads=4`、`jevdb_max_retries=3`、`jevdb_retry_max_delay=30`、`jevdb_on_error=error`、`jevdb_timeout=60`、`threads=1`。
9. 执行虚构查询：`SELECT jev_probability(?, ?), jev_keys_overlap(?, ?)`，用户文本全部绑定；期望概率在 `[0,1]`，重叠布尔为 true。401/403 记 BLOCKED，429/5xx 记 FAILED，不能转成 false。
10. 在 `finally` 中查询 `jevdb_stats()` 写报告，再 `DROP SECRET jev` 并关闭连接；报告不含 key、Authorization、请求正文。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码/报告 | 用户可见文案（messages 键） |
|---|---|---|---|
| 非 arm64 macOS | 不构建，返回 3 | `ENGINE_UNAVAILABLE` | `error.ENGINE_UNAVAILABLE` |
| OpenSSL 只有动态库 | 构建前提示安装静态库；不偷偷改为动态链接 | `ENGINE_UNAVAILABLE` | 同上 |
| 扩展 ABI 不匹配/加载失败 | 保留 build 日志，返回 4 | `ENGINE_UNAVAILABLE` | 同上 |
| 401/403 | build/load 仍 PASS，call BLOCKED，返回 2 | `UNAUTHENTICATED` | `error.UNAUTHENTICATED` |
| 429 | 记录 retry-after；重试耗尽 FAILED | `RATE_LIMITED` | `error.RATE_LIMITED` |
| 查询错误 | 不设置 `reject`，保留异常文本 | `MODEL_ERROR` | `error.MODEL_ERROR` |
| 源码 commit 漂移 | tar 包内容与 pin 不符时中止 | `ENGINE_UNAVAILABLE` | 同上 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_pin_rejects_non_mvp0_duckdb_version` | `scripts/tests/test_build_jevdb.py` | `1.4.2` | `ValueError` |
| `test_build_plan_uses_static_openssl_and_unsigned_extension` | 同上 | 固定 pin/prefix | 参数含 `OPENSSL_USE_STATIC_LIBS=ON`；产物路径固定 |
| `test_build_plan_rejects_space_and_quote_in_extension_path` | 同上 | `a'b/c.duckdb_extension` | `ValueError` |
| `test_probe_sets_required_jevdb_settings` | `scripts/tests/test_probe_jevdb.py` | 假连接 | 7 条 `SET` 全部执行，`jevdb_on_error='error'` |
| `test_probe_401_is_blocked_not_passed` | 同上 | 假连接抛 401 | exit 2；`call.status=BLOCKED` |
| `test_probe_query_error_is_not_treated_as_false` | 同上 | 假连接抛 `MODEL_ERROR` | 不返回 false/NULL；`call.status=FAILED` |
| `test_probe_report_does_not_contain_key` | 同上 | 环境含测试 key | 序列化报告不含 key 字面量 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `vendors/jevdb/pin.json` | GitHub API 核对的 commit、MIT 许可证、DuckDB 1.4.3 | 已确认；执行时再次校验 |
| 无响应 cassette | 本包不保存 JEVDB 网络响应 | 输出只记状态、耗时、统计；密钥不入档 |

## 9. 验收

### 9.1 命令与期望输出
```bash
python3 -m unittest scripts.tests.test_build_jevdb scripts.tests.test_probe_jevdb -v
# 期望：7 tests，OK

scripts/build_jevdb.sh --openssl-prefix "$(brew --prefix openssl@3)"
# 期望：最后一行是 .dev-data/jevdb/src/build/release/extension/jevdb/jevdb.duckdb_extension

cd core && uv run python ../scripts/probe_jevdb.py \
  --extension ../.dev-data/jevdb/src/build/release/extension/jevdb/jevdb.duckdb_extension \
  --report ../.dev-data/g0-jevdb/report.json
# 期望有效 key：exit=0；build/load/call 全 PASS；duckdb_version=1.4.3
# 无 key/无效 key：build/load PASS；call BLOCKED；总体不得记 PASS
```

### 9.2 完成清单
- [ ] 固定 commit 构建成功，许可证为 MIT，扩展 SHA256 已记录
- [ ] `LOAD`、`jev_probability`、`jev_keys_overlap`、`jevdb_stats()` 均有结果或明确阻塞原因
- [ ] 第 8.1 节 7 个测试全部通过
- [ ] 报告和日志不含 key、Authorization 或披露正文
- [ ] 已写 `docs/wp/status/G0-JEVDB.md`；结论交协调者更新闸门附录
- [ ] `scripts/check.sh` 通过

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| S-04 | 扩展路径、加载参数、settings、build.lock、错误模式 | 通过：完整实现；失败：只保留 SQL/接口/降级测试 |
| W-03 | pin.json、构建参数、静态 OpenSSL 结论 | Windows 不复用 dylib，只参考参数 |
| 协调者 | 闸门结论与扩展 SHA256 | `auto` 模式降级必须可见 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| OpenSSL 静态库缺失 | CMake 找不到 `.a` | 记录阻塞；产品全程 `jev_direct` |
| DuckDB 1.4.3 编译过慢/失败 | 日志出现 OOM 或 target 失败 | 提高虚拟内存或减少并行到 2；仍失败则闸门失败 |
| 扩展加载被签名策略拒绝 | `LOAD` 报 unsigned | 只在进程配置启用 `allow_unsigned_extensions`，不得修改系统策略 |
| 上游源码结构变化 | `scripts/build.sh` 不存在 | pin 已固定；若仍缺失，闸门失败并保留证据 |

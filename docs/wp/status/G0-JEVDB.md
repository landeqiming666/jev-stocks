# G0-JEVDB 实施与真实闸门状态

## 主 agent 独立复核

主审完整读取下载、哈希、受限解压、静态构建及隔离探针代码，要求并复验调用方 env 应用于子进程、JEV_ENDPOINT 完整地址安全转换为前缀。37 项专项回归（35 subtests）与全门禁 16/0/1 通过；真实静态扩展从主集成 Python 1.4.3 宿主加载成功，本地三种 overlap 与 NULL 短路一致，32 个统计字段且 requests/retries/input_tokens/errors 全部为 0，原 wheel 未变。

主审 retained artifact 为主集成 `.dev-data/jevdb/verified-static/jevdb.duckdb_extension`，SHA256 `d9f3f1d613847900436af87422f0cc7c3e8e9268934559f207433e6e6d3ffd9a`；源码构建原 lock 和日志已在 ignored 目录保留。主审日志 `/tmp/jev-next10-native-main-review.log`、`/tmp/jev-next10-jevdb-main-probe.log`、`/tmp/jev-next10-jevdb-main-gate.log`。真实 CLI exit 2，call BLOCKED，未配置有效密钥，不将本地 NULL 短路计为真实语义闸门。

> 版本：v1.0 · 2026-11-03 · 状态：已定稿

工作目录：`/Users/lijiaxuan/.codex/worktrees/mac-n10-jevdb/JEV Stocks`。
基线：`7b366dc7ae1a48863d8375fcc9a1a4179faf3452`。
除用户明确授权继承的前置外，仅修改 owns 与本状态文件。未新建 worktree、push、merge、
修改 main、安装工具、修改依赖版本或锁文件、改变系统签名策略。未写方案库或个人日志。

## 结论

代码验收 **PASS**；固定源码真实 build / LOAD / 本地函数 **PASS**。
远端语义闸门及最终 M-8 **BLOCKED**，唯一未通过原因是没有有效 `JEV_API_KEY`。
非 NULL 的 `jev_probability` / `jev_holds` 与无效 key 的真实 401/403 均未执行，
没有向模型发任何请求。mock 只用于单测，不能替代真实远端验收。

| 检查 | 实际结果 |
|---|---|
| `(cd core && uv sync --frozen --offline)` | PASS；已安装 DuckDB 1.4.3，锁文件未变 |
| 初始先测后实现 | 20 项全 FAIL，规定 7 项与空格/缺 key/ABI 均覆盖 |
| 静态模式 / 固定元数据红测 | 分别 2 项 / 1 项 FAIL 后修复；日志保留 |
| 固定 JEVDB / DuckDB 源码与 MIT | PASS；哈希及标准 MIT 文本核实，无 SPDX 行 |
| OpenSSL 与 DuckDB 静态扩展、并行 2 | PASS；首次完整静态构建 299 个 Ninja 步骤 |
| 固定 DuckDB metadata 复建 | PASS；3 个 Ninja 步骤，source_id 固定为 d1dc88f950 |
| 原 wheel 的真实 LOAD | PASS；676 ms，专用内存连接，未签名仅进程配置 |
| jev_keys_overlap | PASS；重叠 true，空列表 false，未知列表 true |
| NULL jev_probability / jev_holds 短路 | PASS；均为 SQL NULL |
| jevdb_stats() | PASS；32 个字段，请求/重试/token/错误数均 0 |
| 扩展目录函数注册 | PASS；jevdb 已 loaded，实际扩展版本 0.1.0 |
| 原 Python wheel 前后哈希 | 完全相同，未替换 wheel |
| 当前无 key 的真实探针 | build/load/local PASS，call BLOCKED / CONFIG_REQUIRED，exit 2 |
| 非 NULL 语义函数及真实 401/403 | BLOCKED / 未验证；没有远端请求 |
| 专项 core unittest | 37 项 PASS |
| 专项 core pytest | 37 项 PASS，35 subtests PASS，0 skip |
| 脚本全量 core pytest | 235 项 PASS，4317 subtests PASS，0 skip |
| 自有脚本 Ruff lint / format，strict doccheck | PASS |
| 完整 scripts/check.sh | exit 0；15 PASS / 0 FAIL / 2 未就绪或 opt-in 步骤 SKIP |
| Rust cargo test --locked -- --test-threads=1 | 3 + 28 = 31 项 PASS，0 ignored |

源码、扩展、下载、lock 和所有运行日志均在被忽略的 `.dev-data/jevdb/`，不提交。
报告不含 key、Authorization 或披露/响应正文。统计只输出已核实字段的有限数字与 NULL。

## 主审补丁：子进程环境与 gateway 端点

基于已验收的 `4bbd6d2f88ce0902b9fe02728ffb1afc7633a5c4` 补两项主审发现。
本轮仅改 probe、probe tests 与本状态；没有另下载、重建、改 wheel 或依赖锁。

- `isolated_probe(path, env)` 仅传递 `JEV_API_KEY`、`SENTINEL_OFFLINE`、`SSL_CERT_FILE`、
  `JEV_ENDPOINT` 配置。worker 在 spawn 子进程且 import DuckDB 之前，仅把前三项写入
  子进程环境；映射中缺省的项移除继承值。`JEV_ENDPOINT` 只作 SQL 配置，不覆盖进程环境。
  worker 拒绝在父进程直接执行，父环境不变，无关变量不按映射覆盖。
- 原生 C++ 读取 getenv 的时机已核实；新增真实 spawn + libc getenv 单测，父 key 与映射
  不同、父 offline/CA 与映射不同以及映射缺项的情况均通过；全父环境快照保持相同。
  DuckDB 连接/模型结果在该单测中是明确的 fake，没有发模型请求或伪造真实认证结果。
- `src/jev_client.cpp:197–205` 会在前缀后追加 systemone，`:217` 读取 SSL_CERT_FILE。
  完整 HTTPS `/v1/systemone` 配置规范化成同一 host/port 的 `/v1/` 前缀，以
  `con.execute('SET jevdb_endpoint = ?', [prefix])` 绑定，并在 CREATE SECRET / 模型查询前执行。
  没有配置时保留官方端点；有 gateway 配置时不会把 gateway key 发向官方默认。
- 拒绝 userinfo、query（含空 query）、fragment、非 HTTPS、控制/空白字符、非法 host/port
  和不匹配的完整路径。报错只给 INVALID_ARGUMENT 和固定文案；端点绑定异常也不回显 URL
  或 key。缺 key / offline 优先运行本地核实并 BLOCKED，不验证或请求远端端点。
- 新回归先红后绿：`logs/endpoint-child-env-red.log`。补丁后专项 37 项通过，包含 6 个新增
  环境/Endpoint 用例和 13 个非法 URL 子例。真实 30 秒隔离进程绑定设置成功，NULL 短路
  与 requests=0 见 `logs/endpoint-binding-local.log`。
- 原 d9f3... 产物再次 LOAD：9 ms；overlap 三值、NULL、32 stats 均通过，请求/重试/token
  均 0，call BLOCKED / CONFIG_REQUIRED，exit 2。见 `report-endpoint-child-env.json` 和
  `logs/probe-endpoint-child-env.log`。扩展 SHA 与 wheel SHA 均与原值完全相同。

本轮完整门禁 `logs/full-check-endpoint-child-env.log`：15 PASS / 0 FAIL / 原两个条件 SKIP；
脚本 235 项、4317 subtests、core 1267 项、web lint/types/test、Rust fmt/clippy 全通过。
专项 `logs/endpoint-child-env-tests.log` / `logs/unittest-endpoint-child-env.log` 均通过。
Ruff lint / format 与 strict doccheck 通过，临时 node_modules 链接已移除。

## 已批准 CR 与前置

主 agent 已批准 N10-01 §9 并修正规范，规模为 L，约 1500 行预算。继承关系如下：

| 主 agent 原提交 | 本树 cherry-pick |
|---|---|
| `78673adf3f3a7407fa216292b0fe61ff8b2cf5a3` | `de44df0c92203db8554737539a20e35aa770ce1d` |
| `ef80707cb1deaef707aee2f1deda4675d5bbf19f` | `cf827941aa4a09bba970244173103a1d311a7ce8` |
| `5c92f2084be14843c84301e37147c486eb19885c` | `539861107a75ebffc18a808ca51cd0e5dafdda62` |
| `760753154a9aa7f9e27d7e5c467dc9ba079a2cbc` | `91e362d233ab52fdfbc100633566b7536b794a69` |

1. 上游 `scripts/build.sh:5` 将 `"$@"` 转发给 CMake；OpenSSL 的 -D 参数有效。
   `:15` 硬编码并行 4，驱动执行等价 CMake 配置并显式并行 2，上游源码保持原样。
2. `LICENSE:1` 为标准 MIT License，没有 SPDX 行；使用 MIT 文本与整个固定源码哈希核实。
3. `src/jevdb_extension.cpp:651` 注册概率函数的 VARCHAR condition + ANY varargs；
   `:434` bind 限定 2–4 参数且 condition 可折叠。`:855` 注册
   `jev_keys_overlap(VARCHAR[], VARCHAR[]) -> BOOLEAN`。用户文本和键列表分别绑定。
4. 原动态模式编译成功但 LOAD exit 4，缺
   `__ZN6duckdb12PhysicalJoin14BuildPipelinesERNS_8PipelineERNS_12MetaPipelineE`。
   `nm -gU` 确认 wheel 只有 Python / ADBC 两个入口；不能将此归因 OpenSSL 或签名策略。
   DuckDB `CMakeLists.txt:897–927` 明确静态扩展为分发主路线。已批准并实测
   `BUILD_EXTENSIONS_ONLY=OFF`、`EXTENSION_STATIC_BUILD=ON`，保留 OpenSSL 静态及并行 2。
   ABI 问题已在静态扩展中解决，原 wheel 未改。
5. 原 checker 误扫 ignored 上游源码产生 16 处失败，已由批准前置修复扫描范围，
   没有删除源码/测试、临时移走源码或跳过检查伪造通过。
6. 新核实的复现细节：DuckDB `CMakeLists.txt:302–320` 收到 version-only override 时
   会读取外层 repo HEAD。按同一 JEVDB pin 的 `python/CMakeLists.txt` 固定
   `OVERRIDE_GIT_DESCRIBE=v1.4.3-0-gd1dc88f950` 与 `GIT_COMMIT_HASH=d1dc88f950`，
   版本与下载源码不变，避免提交不同导致 embedded source_id 漂移。该命令/参数已亲读核实；
   原 wheel 的 `pragma_version()` 同样返回 `v1.4.3 / d1dc88f950 / Andium`。

## 产物身份

| 对象 | SHA256 / 值 |
|---|---|
| JEVDB commit | `47a9070cba09012bedcc60f5e47e09ccb5c2c1fe` |
| JEVDB archive | `cd52048a08b54a34409e507373b7b1d48c6885f28ef2d76db4e080a584c1d775` |
| DuckDB v1.4.3 archive | `b6a2afd09d9cf07e50d5cd07077df7f7697b61cca2eb00754f5adf89a1ae6c64` |
| 上游 scripts/build.sh | `a98c86f5b60951196f81834adeac30da7594cd5c0bb6f7b635f18030e66cec87` |
| 最终静态 extension | `d9f3f1d613847900436af87422f0cc7c3e8e9268934559f207433e6e6d3ffd9a` |
| 原 wheel 构建前后 | `6386253a68ebc77565fb505073f587741ac82d50e4f2215d67964869d1a429d0` |
| 扩展尺寸 | 32,382,974 bytes |
| CMake / Ninja / cc | 4.3.4 / 1.13.2 / Apple clang 21.0.0 |
| OpenSSL | `/opt/homebrew/Cellar/openssl@3/3.6.2`，libssl.a + libcrypto.a |

产物：`.dev-data/jevdb/src/build/release/extension/jevdb/jevdb.duckdb_extension`。
`otool -L` 仅列扩展自身、libc++.1.dylib、libSystem.B.dylib，无动态 OpenSSL / DuckDB 依赖。
0600 的 `build.lock.json` 保存完整 argv、模式、source_id、工具版本及 wheel 前后 SHA。
`.dev-data/jevdb/report.json` 保存真实 LOAD、本地结果和全部 32 个统计字段。

实际 catalog：`jev_probability(VARCHAR, ANY...) -> DOUBLE`、
`jev_holds(VARCHAR, ANY...) -> BOOLEAN`、`jev_keys_overlap(VARCHAR[], VARCHAR[]) -> BOOLEAN`、
`jevdb_stats()` 为 table function。见 `logs/local-catalog.log`；binder 的参数限制以源码为准。

## 复验命令与检查记录

```bash
scripts/build_jevdb.sh --link-mode static --openssl-prefix /opt/homebrew/opt/openssl@3
SENTINEL_OFFLINE=1 core/.venv/bin/python scripts/probe_jevdb.py \
  --extension .dev-data/jevdb/src/build/release/extension/jevdb/jevdb.duckdb_extension \
  --report .dev-data/jevdb/report.json
core/.venv/bin/python -m unittest scripts.tests.test_build_jevdb scripts.tests.test_probe_jevdb -v
uv run --project core --frozen --offline python -m pytest -q scripts/tests
core/.venv/bin/ruff check --config core/pyproject.toml --target-version py39 \
  scripts/probe_jevdb.py vendors/jevdb/build.py \
  scripts/tests/test_build_jevdb.py scripts/tests/test_probe_jevdb.py
core/.venv/bin/ruff format --check --config core/pyproject.toml --target-version py39 \
  scripts/probe_jevdb.py vendors/jevdb/build.py \
  scripts/tests/test_build_jevdb.py scripts/tests/test_probe_jevdb.py
python3 scripts/check_docs.py --strict
UV_FROZEN=1 UV_OFFLINE=1 \
  CARGO_TARGET_DIR='/Users/lijiaxuan/.codex/worktrees/mac-batch-10/JEV Stocks/apps/desktop/src-tauri/target' \
  scripts/check.sh
CARGO_TARGET_DIR='/Users/lijiaxuan/.codex/worktrees/mac-batch-10/JEV Stocks/apps/desktop/src-tauri/target' \
  cargo test --locked --manifest-path apps/desktop/src-tauri/Cargo.toml -- --test-threads=1
```

最终构建日志 `logs/build.log`；完整首次静态编译 `logs/build-static-first.log`；
最终探针 `logs/probe-static-run.log`；全部红测 `red-tests.log` / `static-mode-red.log` /
`metadata-red.log`；最终门禁 `logs/full-check-final.log`；Rust `logs/rust-tests-final.log`；
专项 unittest `logs/unittest-final.log`。旧动态诊断 artifact / lock / report 保留在 ignored 目录，
其 SHA 不得作为最终静态扩展身份。构建目录占用约 564 MiB，预检仍要求至少 2 GiB 可用空间。

原 runner 的未就绪 C-05 generated-ts 与 opt-in E2E 不属于本包的已就绪门禁，明确单列；
脚本 pytest 收集全部 unittest / pytest，不因缺依赖跳过。前端检查临时复用集成树
node_modules，结束后移除临时链接。第一次 Rust 并行复验曾出现旧 bridge 时序断言失败，
批准前置后全部 31 项串行通过，日志均保留，本包未自行修改 Rust。
最终完整门禁的 core pytest 1267 项 PASS，web lint/types/test（1 项）PASS，
Rust fmt/clippy PASS；strict doccheck 0 错误、0 警告。

实现加测试实际 **1371 行**，包含空行：probe 416、build driver 383、sh 8、ps1 2、
build tests 184、probe tests 378；实现 809 行、测试 562 行。pin 与说明/状态文档另计。
规模 L / 约 1500 行已批准，没有删测试压缩规模。

## 安全与下游边界

下载固定 URL 并验证 SHA；解压拒绝路径穿越、hardlink、链接逃逸及链接下嵌套成员，
保留原源码内安全测试链接；复用源码时逐文件验证。未知 pin / URL / hash / 模式中止。
支持普通空格路径，LOAD 路径拒绝单双引号、NUL、CR、LF。没有运行主库或真实用户数据库。

connect/LOAD 有 30 秒隔离进程上限，正常 finally 读取数字统计、DROP 临时 secret 并 close；
native 卡死/崩溃由进程退出释放内存连接。CREATE SECRET 使用非 PERSISTENT env provider，
不拼入 key；没有 key 或离线时不执行非 NULL 语义查询。on_error 固定 error，禁用正文 dump。
远端进程预算 450 秒、retry-after cap 30 秒；未实测远端耗尽时序，不声称端到端已通过。
异常只输出错误类别/状态，request_id 保留 null，未暴露的 retry-after 不虚构。

S-04 可复用已实测的 static 构建、加载配置、本地函数、SHA 与统计结构；凭据就绪后仍需
真实非 NULL 概率、认证失败模式与完整产品流程验收，才能解除 G0 和最终 M-8。

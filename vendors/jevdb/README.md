# JEVDB 固定源码构建

这里只提交来源 pin 和构建驱动，不包含上游源码、扩展或本机运行 lock。
上游 [PDAIS/JEVDB](https://github.com/PDAIS/JEVDB/tree/47a9070cba09012bedcc60f5e47e09ccb5c2c1fe)
固定为 `47a9070cba09012bedcc60f5e47e09ccb5c2c1fe`，扩展版本 `0.1.0`，许可证 MIT。
访问并核实日期：2026-11-03。DuckDB 唯一支持版本为 `1.4.3`。

`pin.json` 同时固定两个源码 URL 与 SHA256。DuckDB 哈希来自该 JEVDB pin 的
`python/CMakeLists.txt:12`，已与实际下载包复核。JEVDB 的 `LICENSE` 是标准 MIT 文本，
没有 SPDX 行；许可证随完整源码哈希一并验证。

```bash
cd core && uv sync --frozen --offline
cd ..
scripts/build_jevdb.sh --link-mode static --openssl-prefix /opt/homebrew/opt/openssl@3
core/.venv/bin/python scripts/probe_jevdb.py \
  --extension .dev-data/jevdb/src/build/release/extension/jevdb/jevdb.duckdb_extension \
  --report .dev-data/jevdb/report.json
uv run --project core --frozen --offline python -m pytest -q \
  scripts/tests/test_build_jevdb.py scripts/tests/test_probe_jevdb.py
```

构建前检测 macOS arm64、已安装 DuckDB、cmake/ninja/git/cc、OpenSSL 静态库和头文件、
至少 2 GiB 可用空间。脚本不安装工具、不修改依赖或系统签名策略。
源码、下载包、编译产物、日志和 `0600` 的运行 lock 都写入 `.dev-data/jevdb/`。
普通空格路径通过 argv 传递；LOAD 路径拒绝单双引号、NUL、CR 和 LF。
下载错误、未知 pin 或哈希、解压越界都会中止。安全的源码内测试符号链接保留；
链接逃逸、hardlink 和链接下的嵌套归档成员拒绝。重跑时逐文件复核已解压源码。

该 pin 的 `scripts/build.sh` 接受额外 CMake 参数，但硬编码 `--parallel 4`。
DuckDB 1.4.3 `CMakeLists.txt:897–927` 指定静态 DuckDB 为分发扩展的主路线，适用于
宿主使用 RTLD_LOCAL 或不导出 C++ 符号的场景。本驱动默认 `--link-mode static`，
设置 `BUILD_EXTENSIONS_ONLY=OFF`、`EXTENSION_STATIC_BUILD=ON`，其余配置沿用上游，
再以 `--parallel 2` 构建，并显式指定静态 `libssl.a`、`libcrypto.a`。
`--link-mode dynamic` 保留上游 `BUILD_EXTENSIONS_ONLY=ON`、`EXTENSION_STATIC_BUILD=OFF`，
仅用于诊断；当前 Python wheel 下该模式已实测因缺 C++ 符号不能 LOAD。
上游源码保持原样；实际 argv、模式、上游脚本哈希、工具版本、产物哈希、
原 wheel 构建前后哈希和 `otool -L` 结果写入运行 lock。
DuckDB 的完整版本描述固定为同一 pin 的 `python/CMakeLists.txt` 中的
`v1.4.3-0-gd1dc88f950`，并显式传 `GIT_COMMIT_HASH=d1dc88f950`，防止解压源码
意外继承外层工作仓库 HEAD。版本仍为 1.4.3，下载源码不变。
构建成功时最后一行是扩展绝对路径；失败时打印首个失败命令与日志位置。

探针仅在隔离进程的内存连接启用 `allow_unsigned_extensions`。connect/LOAD 有 30 秒
进程上限；正常路径在 finally 中读取数字统计、删除临时 secret 并关闭连接。
进程强制超时或 native 崩溃时由操作系统释放进程及内存连接。
固定条件是 SQL 字面量，虚构用户文本与列表均绑定参数。
本地验证列表重叠、空列表/未知列表及 NULL 输入短路；没有 key 或离线时绝不执行
非 NULL 语义查询。远端异常只记录错误码、HTTP 状态和存在且有限的结构化 retry-after，
不记录响应正文、key 或 Authorization。上游没有提供可可靠提取的结构化 request_id，
报告保留为 null；上游只抛 HTTP 状态而未暴露 retry-after 时不能虚构该值。

探针退出码：0 全通过；2 已加载但远端被认证、缺 key 或离线阻塞；3 无构建产物；
4 LOAD/ABI 失败；1 参数、本地核实或远端模型失败。`build.status=PASS` 仅表示给定
扩展文件存在且已计算 SHA；完整构建来源记录需复核 `build.lock.json`。

静态模式已由 [N10-01 §9](../../docs/wp/cr/N10-01-execution-clarifications.md) 批准；
真实构建、LOAD、本地函数与远端调用分别记录于 [本包状态](../../docs/wp/status/G0-JEVDB.md)。
缺 key 时远端闸门仍 BLOCKED，不得将本地核实替代最终 M-8 验收。

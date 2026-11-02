---
id: W-03
title: Windows 上尝试构建 JEVDB（MSVC）
phase: mvp0
platform: windows
lane: windows
size: M
deps: [W-01, G0-JEVDB]
owns: [scripts/build_jevdb_msvc.ps1, vendors/jevdb-msvc/]
appends: []
stubs: []
---
# W-03 Windows 上尝试构建 JEVDB（MSVC）

## 0. 一眼看懂

- **目标**：在 Windows 11 x64 上用 MSVC、vcpkg OpenSSL、DuckDB 1.4.3 构建并加载 `jevdb.duckdb_extension`；无论成功失败都留下可复现记录。
- **失败时**：产品自动使用 `jev_direct`，不阻塞 Windows MVP-0；不得声称 JEVDB 可用。
- **预计规模**：约 380 行，PowerShell 260 行、自检与说明 120 行。

## 1. 背景与边界

### 1.1 为什么需要它
PyPI 的 `jevdb` 0.1.0 只提供 Linux x86-64 扩展。Windows 能否运行 JEVDB 决定 Windows 是否能使用同一加速引擎；不能则必须由 S-03 的 Jev 直连保底。

### 1.2 范围内
1. 固定 JEVDB 提交、DuckDB 版本、vcpkg triplet 和产物路径。
2. 下载、校验、配置、编译、加载、SHA-256 记录。
3. 可选真实 Jev 冒烟；没有密钥时只验证加载和键函数。
4. 失败分类与 `jev_direct` 降级记录。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 修改产品引擎选择或共享接口 | S-04、C-04；本包只产出扩展与报告 |
| 打包进 v1 NSIS | v1 |
| 改 DuckDB 版本 | 禁止；必须 1.4.3 |
| 提交 OpenSSL 私钥、Jev 密钥或用户数据 | 永远不做 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [02-技术架构.md](../../02-技术架构.md) | 4 依赖白名单、9 平台层、12 降级 | 版本与降级边界 |
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | 6.4 JEVDB 引擎 | 加载与临时 secret 规则 |
| [09-测试与评测.md](../../09-测试与评测.md) | 第 10 节 G0-JEVDB | 闸门口径 |
| [decisions.md](../../decisions.md) | ADR-015、ADR-016 | 固定模型与平台隔离 |
| [W-01-windows-platform-layer.md](W-01-windows-platform-layer.md) | 5.4 PowerShell、9.1 | 脚本编码与执行方式 |

## 3. 前置条件

- Windows 11 x64，Visual Studio Build Tools 已安装“使用 C++ 的桌面开发”，`cl.exe` 可用。
- CMake ≥ 3.24、Ninja、Git、Python 3.12、PowerShell 5.1。
- vcpkg 位于 `C:\tools\vcpkg`，并已执行 `bootstrap-vcpkg.bat`。
- G0-JEVDB 已记录 macOS 构建经验与 DuckDB 1.4.3 提交基线。
- 网络可访问 GitHub；不要求 Jev 密钥。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `scripts/build_jevdb_msvc.ps1` | 新建 | 一键下载、构建、加载、哈希与报告 |
| `vendors/jevdb-msvc/pins.json` | 新建 | JEVDB 提交、DuckDB 版本/哈希、vcpkg triplet |
| `vendors/jevdb-msvc/README.md` | 新建 | Windows 构建步骤与失败含义 |
| `vendors/jevdb-msvc/.gitignore` | 新建 | 忽略源码缓存、构建目录和二进制 |
| `vendors/jevdb-msvc/self-test.ps1` | 新建 | `-DryRun` 参数与路径断言 |
| `vendors/jevdb-msvc/artifacts/x64-windows/SHA256SUMS` | 生成并提交 | 扩展、源码包、CLI 的哈希 |
| `vendors/jevdb-msvc/artifacts/x64-windows/build-result.json` | 生成并提交 | 成功/失败、耗时、错误分类 |
| `docs/wp/status/W-03.md` | 新建 | 命令输出与人工复核 |

## 5. 接口规格

### 5.1 脚本参数
```powershell
param([switch]$DryRun, [switch]$Clean, [switch]$SmokeWithJev,
  [string]$VcpkgRoot = "C:\tools\vcpkg", [string]$OutputDir = "$PSScriptRoot\..\vendors\jevdb-msvc\artifacts\x64-windows")
```
退出码：`0` 成功或已明确降级；`10` 工具链缺失；`20` 下载/哈希失败；`30` CMake 配置失败；`31` 编译失败；`32` 扩展加载失败；`40` 可选 Jev 冒烟失败。任何非 0 都写 `build-result.json`。

### 5.2 `pins.json`
| 字段 | 类型 | 必填 | 值/约束 | 含义 |
|---|---|---|---|---|
| `jevdbCommit` | str | 是 | `47a9070cba09012bedcc60f5e47e09ccb5c2c1fe` | 固定提交 |
| `duckdbVersion` | str | 是 | `1.4.3` | 必须与核心一致 |
| `duckdbSha256` | str | 是 | `b6a2afd09d9cf07e50d5cd07077df7f7697b61cca2eb00754f5adf89a1ae6c64` | 官方 tar.gz |
| `vcpkgTriplet` | str | 是 | `x64-windows-static-md` | OpenSSL 静态、CRT 动态 |
| `extensionRelativePath` | str | 是 | `build/release/extension/jevdb/jevdb.duckdb_extension` | CMake 输出 |

### 5.3 `build-result.json`
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `status` | str | 是 | `built/load_failed/build_failed/prerequisite_failed` | 结果 |
| `fallback` | str | 是 | `none/jev_direct` | 产品后续引擎 |
| `duckdbVersion` | str | 是 | `1.4.3` | 版本 |
| `triplet` | str | 是 | `x64-windows-static-md` | vcpkg 目标 |
| `extensionSha256` | str\|null | 是 | 64 位十六进制或 null | 产物哈希 |
| `durationSeconds` | int | 是 | ≥ 0 | 总耗时 |
| `errorClass` | str\|null | 是 | `TOOLCHAIN/DOWNLOAD/CONFIGURE/COMPILE/LOAD/SMOKE` | 失败分类 |

## 6. 实现步骤

1. 脚本首行设置 `$ErrorActionPreference = "Stop"`；检测 `cmake --version ≥ 3.24`、`ninja --version`、`cl`、`py -3`。
2. 从 `pins.json` 读取版本；固定下载：
   ```powershell
   Invoke-WebRequest "https://codeload.github.com/duckdb/duckdb/tar.gz/refs/tags/v1.4.3" -OutFile $duck; Invoke-WebRequest "https://codeload.github.com/PDAIS/JEVDB/tar.gz/47a9070cba09012bedcc60f5e47e09ccb5c2c1fe" -OutFile $jev
   ```
3. 计算 SHA-256；DuckDB 必须等于 pins 值。JEVDB 包哈希首次构建后写入 `SHA256SUMS`，后续必须相等；不相等退出 20。
4. 安装 OpenSSL：
   ```powershell
   & "$VcpkgRoot\vcpkg.exe" install openssl:x64-windows-static-md --clean-after-build
   ```
5. 在 VS Developer PowerShell 中配置：
   ```powershell
   cmake -S $duckdbSrc -B $buildDir -G Ninja -DCMAKE_BUILD_TYPE=Release `
     -DCMAKE_C_COMPILER=cl -DCMAKE_CXX_COMPILER=cl -DCMAKE_CXX_FLAGS="/EHsc /bigobj /utf-8" `
     -DCMAKE_TOOLCHAIN_FILE="$VcpkgRoot\scripts\buildsystems\vcpkg.cmake" -DVCPKG_TARGET_TRIPLET=x64-windows-static-md `
     -DOPENSSL_ROOT_DIR="$VcpkgRoot\installed\x64-windows-static-md" -DOPENSSL_USE_STATIC_LIBS=ON `
     -DBUILD_EXTENSIONS_ONLY=ON -DEXTENSION_STATIC_BUILD=OFF -DBUILD_UNITTESTS=OFF -DBUILD_SHELL=OFF `
     -DDISABLE_BUILTIN_EXTENSIONS=ON -DDUCKDB_EXTENSION_CONFIGS="$jevSrc\extension_config.cmake" `
     -DOVERRIDE_GIT_DESCRIBE=v1.4.3
   ```
6. 编译：`cmake --build $buildDir --target jevdb_loadable_extension --parallel 4`。
7. 从官方 DuckDB 1.4.3 Windows amd64 release 下载 `duckdb_cli-windows-amd64.zip`，校验 zip 哈希并解压到 `.cache\duckdb-cli`。
8. 启动 `duckdb.exe -unsigned`，执行：
   ```sql
   LOAD 'C:\path\jevdb.duckdb_extension';
   SELECT jev_keys_overlap(['us:ZZAR'], ['us:ZZAR']);
   ```
   期望第二行 `true`。未出现 `LOAD` 错误才算加载成功。
9. 只有 `-SmokeWithJev` 且存在 `JEV_API_KEY` 时，执行一次 `SELECT jev_probability('The text is positive', 'good');`；密钥不打印、不写入 SQL 文件。
10. 将扩展复制到 `artifacts\x64-windows\jevdb.duckdb_extension`，对扩展、源码包、CLI zip 运行 `Get-FileHash -Algorithm SHA256`，按文件名排序写入 `SHA256SUMS`。
11. 任何失败写 `status/fallback/errorClass`：工具链或编译/加载失败一律 `fallback=jev_direct`；不得改动 S-04 或设置默认引擎。
12. 在状态文件写明 Windows 上是否可用；同步更新对等矩阵与闸门记录。

## 7. 错误与边界情况

| 情形 | 行为 | 退出码 | 用户可见结果 |
|---|---|---|---|
| 缺少 `cl`/CMake/Ninja | 不下载、不编译 | 10 | W-05 使用 Jev 直连 |
| DuckDB 哈希不符 | 删除下载并停止 | 20 | `fallback=jev_direct` |
| vcpkg OpenSSL 失败 | 保留日志，停止配置 | 30 | 报告含 triplet |
| 编译失败 | 保留 `CMakeError.log` 路径 | 31 | 不生成“已构建” |
| `LOAD` 报签名/格式错误 | 记录原文 | 32 | 产品继续直连 |
| 可选 Jev 冒烟 401 | 记录 401，不影响加载结论 | 40 | 标“加载成功、真实调用未通过” |
| 无管理员权限安装 vcpkg | 不修改系统，退出 10 | 10 | 开发笔记记录 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `Test-DryRunWritesNoFiles` | `vendors/jevdb-msvc/self-test.ps1` | `-DryRun` | 退出 0，artifacts 不新增文件 |
| `Test-PinsMatchRequiredVersions` | 同上 | `pins.json` | DuckDB `1.4.3`，JEVDB 提交 40 位 |
| `Test-MissingCompilerExitsTen` | 同上 | 伪造空 PATH | 退出 10，errorClass `TOOLCHAIN` |
| `Test-BadDuckDbHashExitsTwenty` | 同上 | 篡改哈希 | 退出 20，不进入 CMake |
| `Test-OutputPathIsExact` | 同上 | 构建成功 | 路径以 `extension/jevdb/jevdb.duckdb_extension` 结尾 |
| `Test-ShaFileHasThreeEntries` | 同上 | 成功产物 | `SHA256SUMS` 3 行且每行 64 位哈希 |
| `Test-NoSecretInLogs` | 同上 | 假 `JEV_API_KEY` 冒烟失败 | 日志与 JSON 不含该值 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `vendors/jevdb-msvc/tests/fake-tools/` | 空 `cmake.bat`、`ninja.exe` 占位 | 自检运行时临时创建，不入库 |
| `vendors/jevdb-msvc/tests/pins.bad.json` | 错误 DuckDB 哈希 | 复制 pins 后改一位 |
| 无 Jev 密钥 fixture | — | 冒烟默认跳过 |

## 9. 验收

### 9.1 命令与期望输出
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File vendors\jevdb-msvc\self-test.ps1
# 期望：7 passed；0 failed
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_jevdb_msvc.ps1 -DryRun
# 期望：退出 0；打印 DuckDB 1.4.3、x64-windows-static-md、目标路径
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_jevdb_msvc.ps1
# 成功：退出 0，build-result.json status=built
# 失败：按 §5.1 退出，status/fallback 明确，不得崩溃
```

### 9.2 完成清单
- [ ] 构建固定 DuckDB 1.4.3、JEVDB 提交和 `x64-windows-static-md`；成功时 `jev_keys_overlap` 返回 `true`；扩展、源码包、CLI 的 SHA-256 已记录
- [ ] 失败时明确写 `fallback=jev_direct`；日志、JSON、SQL 无密钥；已写 `docs/wp/status/W-03.md` 并更新对等矩阵和闸门记录

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| W-05 | `build-result.json` | JEVDB 失败不阻塞；继续验证 Jev 直连 |
| S-04 | 可选扩展路径 | 只读路径与 SHA，不在 Windows 改共享引擎 |
| v1 打包 | `artifacts/x64-windows` 的哈希 | 二进制未签名，不得默认随发布分发 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| MSVC 与静态 CRT 不匹配 | 链接冲突或加载崩溃 | 坚持 `x64-windows-static-md`，不改 DuckDB 版本 |
| OpenSSL 运行库缺失 | `LOAD` 报 DLL 找不到 | 使用静态 OpenSSL；仍失败则 Jev 直连 |
| 上游提交变化 | tarball 哈希变化 | 按固定提交下载；哈希不符立即停止 |
| 编译时间过长 | 30 分钟未完成 | 记录超时，保留日志，不把未完成当失败代码 |

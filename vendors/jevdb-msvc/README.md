# W-03 Windows JEVDB 构建

使用 MSVC x64、DuckDB 1.4.3、JEVDB 0.1.0 和 vcpkg 的静态 OpenSSL 构建扩展。DuckDB 运行库和锁文件沿用项目版本。源包、编译目录和扩展留在本地。

| 输入 | 固定来源 |
|---|---|
| JEVDB 源码和 MIT 许可证 | [上游 47a9070c 提交](https://github.com/PDAIS/JEVDB/commit/47a9070cba09012bedcc60f5e47e09ccb5c2c1fe) |
| DuckDB 源码和 CLI | [上游 1.4.3 发布页](https://github.com/duckdb/duckdb/releases/tag/v1.4.3) |
| CLI ZIP SHA-256 | [Microsoft winget 1.4.3 x64 安装清单](https://github.com/microsoft/winget-pkgs/blob/master/manifests/d/DuckDB/cli/1.4.3/DuckDB.cli.installer.yaml) |
| OpenSSL 3.6.0#3 | [Microsoft vcpkg 固定端口](https://github.com/microsoft/vcpkg/blob/3af1d1e60af2b2abf55760538cd607829029b07a/ports/openssl/vcpkg.json) |

pins.json 锁定三个输入包的 SHA-256。vcpkg.json 固定仓库 baseline 与 OpenSSL 端口，目标为 x64-windows-static-md。DuckDB 内嵌 source ID 固定为 d1dc88f950，Windows 使用静态链接 DuckDB 的扩展模式，构建目标为 jevdb_loadable_extension。

## 本地运行

先打开 Visual Studio 的 x64 Developer PowerShell，确保 CMake ≥ 3.24、Ninja、Git 和 Python 3.12 可用，项目虚拟环境有 DuckDB 1.4.3。Visual Studio 随附的 vcpkg 可通过 -VcpkgRoot 指定。使用独立 vcpkg 时默认路径为 C:\tools\vcpkg。

~~~powershell
.\scripts\build_jevdb_msvc.ps1 -DryRun

$vcpkg = Join-Path $env:VSINSTALLDIR 'VC/vcpkg'
.\scripts\build_jevdb_msvc.ps1 -Preflight -VcpkgRoot $vcpkg
.\scripts\build_jevdb_msvc.ps1 -VcpkgRoot $vcpkg
~~~

DryRun 仅读取 pin，输出配置参数和目标路径。Preflight 验证工具、三个输入包，并分别报告静态 OpenSSL 是否可用。Offline 仅使用已校验的输入缓存和固定的 OpenSSL 安装记录。每次构建创建自己的源码与日志目录，Clean 同时要求 CMake 使用 fresh 配置。默认并行 2，可通过 Parallel 调整。

OpenSSL 的 jom 在含中文的缓存路径上会把目录替换成问号。项目在此类路径下时，可把仓库或其专用构建目录临时映射到空闲盘符，再用短路径传入 CacheDir。先确认盘符空闲，结束后用 subst /D 解除自己创建的映射。ArchiveDir 和 OutputDir 可单独指定，CacheDir 仍指向当前工作区中的物理目录。解除映射后，可用报告的 cacheRun 名称在物理缓存下找到日志。

~~~powershell
$physicalCache = [IO.Path]::GetFullPath((Join-Path $PWD.Path 'vendors/jevdb-msvc/.cache'))
[IO.Directory]::CreateDirectory($physicalCache) | Out-Null
if ([IO.Directory]::Exists('W:\')) { throw '请改用空闲盘符。' }
subst.exe W: $physicalCache
if ($LASTEXITCODE -ne 0) { throw '缓存映射失败。' }
try {
    .\scripts\build_jevdb_msvc.ps1 -VcpkgRoot $vcpkg -CacheDir 'W:\'
    $buildExitCode = $LASTEXITCODE
} finally {
    subst.exe W: /D
}
$buildExitCode
~~~

源码解包通过 Python 3.12 保留 Unicode 文件名。DuckDB 中两个已知的测试用 symlink 不参与本构建，解包时省略。

固定 JEVDB 提交的 Retry-After 日期解析调用 timegm。msvc_compat.cmake 只给 jevdb_loadable_extension 目标定义 timegm=_mkgmtime，让 MSVC 保留 UTC 转换语义。上游源包内容保持原样。[Microsoft CRT 文档](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/mkgmtime-mkgmtime32-mkgmtime64?view=msvc-170)

构建完成后，脚本在临时内存数据库中加载扩展并要求 jev_keys_overlap 返回 true。成功生成 build-result.json 和 SHA256SUMS。SHA256SUMS 记录扩展、JEVDB 源码包与 CLI ZIP。DuckDB 源码包哈希另在 pins.json 和 build-result.json 的 inputs 记录。失败写入失败阶段与 jev_direct 开发降级。使用产物时核对本次 build-result.json 的 built、load=passed 和哈希。

Windows PowerShell 5.1 读取 build-result.json 时使用 Get-Content -Raw -Encoding UTF8。

SmokeWithJev 需要显式启用并提供有效的 JEV_API_KEY。该步骤复用 G0-JEVDB 的隔离探针，调用失败时保留已通过的 LOAD 结论，退出 40。没有密钥或启用 Offline 时会记录未运行。构建工具与本地加载测试不接收 JEV_API_KEY。

~~~powershell
.\vendors\jevdb-msvc\self-test.ps1 -VcpkgRoot $vcpkg
~~~

自检覆盖只读 DryRun、固定版本、缺编译器退出码、缓存哈希失败、产物路径、校验文件和测试密钥不出现在错误记录。校验文件用例读取本机真实构建结果，可通过 VerifiedOutputDir 指定。

| 退出码 | 阶段 |
|---|---|
| 0 | 构建并加载成功，或 DryRun / Preflight 成功 |
| 10 | 工具链不齐 |
| 20 | 源码包下载、校验或解压失败 |
| 30 | OpenSSL 准备或 CMake 配置失败 |
| 31 | 编译或产物写入失败 |
| 32 | 扩展加载或键函数检查失败 |
| 40 | 可选远端语义冒烟失败 |

param(
    [switch]$DryRun,
    [switch]$Preflight,
    [switch]$Clean,
    [switch]$Offline,
    [switch]$SmokeWithJev,
    [string]$VcpkgRoot = 'C:\tools\vcpkg',
    [string]$OutputDir = "$PSScriptRoot\..\vendors\jevdb-msvc\artifacts\x64-windows",
    [string]$CacheDir = "$PSScriptRoot\..\vendors\jevdb-msvc\.cache",
    [string]$ArchiveDir,
    [string]$PythonExe,
    [ValidateRange(1, 16)][int]$Parallel = 2
)

$ErrorActionPreference = 'Stop'
$clock = [Diagnostics.Stopwatch]::StartNew()
$utf8 = [Text.UTF8Encoding]::new($false)
$vendor = [IO.Path]::GetFullPath("$PSScriptRoot\..\vendors\jevdb-msvc")
$cache = [IO.Path]::GetFullPath($CacheDir)
$output = [IO.Path]::GetFullPath($OutputDir)
$vcpkg = [IO.Path]::GetFullPath($VcpkgRoot)
if (-not $ArchiveDir) { $ArchiveDir = Join-Path $cache 'downloads' }
$archives = [IO.Path]::GetFullPath($ArchiveDir)
$vcpkgCache = Join-Path $cache 'vcpkg'
$installed = Join-Path $vcpkgCache 'installed'
$failure = 'DOWNLOAD'
$exitCodes = @{ TOOLCHAIN=10; DOWNLOAD=20; CONFIGURE=30; COMPILE=31; LOAD=32; SMOKE=40 }
$report = [ordered]@{
    status = 'build_failed'; fallback = 'jev_direct'; duckdbVersion = '1.4.3'
    triplet = 'x64-windows-static-md'; extensionSha256 = $null; durationSeconds = 0
    errorClass = $null; detail = $null; load = 'not_run'; smoke = 'not_requested'
}

function Get-Application([string]$Name) {
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $command) { throw "找不到 $Name，请在 x64 VS Developer PowerShell 中运行。" }
    return $command.Source
}

function Invoke-Native([string]$Program, [string[]]$Arguments, [string]$Log, [switch]$Capture) {
    # Windows PowerShell 5.1 可把本机 stderr 包成 ErrorRecord。
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    $writer = if ($Log) { [IO.StreamWriter]::new($Log, $false, $utf8) }
    try {
        & $Program @Arguments 2>&1 | ForEach-Object {
            $line = $_.ToString()
            if ($writer) { $writer.WriteLine($line) }
            if ($Capture) { $line }
        }
        if ($LASTEXITCODE -ne 0) {
            throw "$([IO.Path]::GetFileName($Program)) 退出 $LASTEXITCODE。日志：$Log"
        }
    } finally {
        if ($writer) { $writer.Dispose() }
    }
}

function Assert-Pins($Pins, $Manifest) {
    if ($Pins.duckdbVersion -cne '1.4.3' -or
        $Pins.duckdbCommit -cne 'd1dc88f950d456d72493df452dabdcd13aa413dd' -or
        $Pins.jevdbCommit -cne '47a9070cba09012bedcc60f5e47e09ccb5c2c1fe' -or
        $Pins.vcpkgTriplet -cne 'x64-windows-static-md' -or
        $Pins.vcpkgBaseline -cne $Manifest.'builtin-baseline' -or
        $Pins.vcpkgBaseline -cne '3af1d1e60af2b2abf55760538cd607829029b07a' -or
        $Pins.extensionRelativePath -cne 'build/release/extension/jevdb/jevdb.duckdb_extension') {
        throw 'W-03 版本、提交、triplet 或扩展路径与工作包不符。'
    }
    $port = @($Manifest.overrides)
    if (@($Manifest.dependencies).Count -ne 1 -or $Manifest.dependencies[0] -cne 'openssl' -or
        $port.Count -ne 1 -or $port[0].name -cne 'openssl' -or $port[0].version -cne '3.6.0' -or
        $port[0].'port-version' -ne 3) { throw 'OpenSSL 清单与固定端口版本不符。' }
    foreach ($hash in @($Pins.duckdbSha256, $Pins.jevdbSha256, $Pins.cliSha256)) {
        if ($hash -cnotmatch '^[0-9a-f]{64}$') { throw 'pins.json 含无效的 SHA-256。' }
    }
}

function Get-Archive($Asset) {
    $file = Join-Path $archives $Asset.name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        if ($Offline) { throw "离线缓存中缺少 $($Asset.name)。" }
        [IO.Directory]::CreateDirectory($archives) | Out-Null
        $pending = "$file.$([Guid]::NewGuid().ToString('N')).partial"
        try {
            Invoke-Native (Get-Application 'curl.exe') @('-fsSL', '--proto', '=https',
                '--proto-redir', '=https', '--connect-timeout', '15', '--max-time', '180',
                '--output', $pending, $Asset.url)
            if ((Get-FileHash -LiteralPath $pending -Algorithm SHA256).Hash -ine $Asset.sha256) {
                throw "$($Asset.name) 下载 SHA-256 不匹配。"
            }
            [IO.File]::Move($pending, $file)
        } finally { [IO.File]::Delete($pending) }
    }
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $Asset.sha256) {
        throw "$($Asset.name) 缓存 SHA-256 不匹配，请移除该文件后重试。"
    }
    return $file
}

function Get-ConfigureArgs([string]$Duck, [string]$Jev, [string]$Ninja) {
    $sourceId = $pins.duckdbCommit.Substring(0, 10)
    $arguments = @('-S', $Duck, '-B', (Join-Path $Jev 'build/release'), '-G', 'Ninja',
        "-DCMAKE_MAKE_PROGRAM=$Ninja", '-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_TRY_COMPILE_CONFIGURATION=Release',
        '-DCMAKE_C_COMPILER=cl', '-DCMAKE_CXX_COMPILER=cl', '-DCMAKE_CXX_FLAGS=/EHsc /bigobj /utf-8',
        "-DCMAKE_TOOLCHAIN_FILE=$(Join-Path $vcpkg 'scripts/buildsystems/vcpkg.cmake')",
        "-DVCPKG_TARGET_TRIPLET=$($pins.vcpkgTriplet)", '-DVCPKG_MANIFEST_MODE=OFF',
        "-DVCPKG_INSTALLED_DIR=$installed", "-DOPENSSL_ROOT_DIR=$(Join-Path $installed $pins.vcpkgTriplet)",
        '-DOPENSSL_USE_STATIC_LIBS=ON', '-DBUILD_EXTENSIONS_ONLY=OFF', '-DEXTENSION_STATIC_BUILD=ON',
        '-DBUILD_UNITTESTS=OFF', '-DBUILD_SHELL=OFF', '-DDISABLE_BUILTIN_EXTENSIONS=ON',
        "-DDUCKDB_EXTENSION_CONFIGS=$(Join-Path $Jev 'extension_config.cmake')",
        "-DCMAKE_PROJECT_JevDBExtension_INCLUDE=$(Join-Path $vendor 'msvc_compat.cmake')",
        "-DOVERRIDE_GIT_DESCRIBE=v$($pins.duckdbVersion)-0-g$sourceId", "-DGIT_COMMIT_HASH=$sourceId")
    if ($Clean) { $arguments = @('--fresh') + $arguments }
    return $arguments
}

function Test-PinnedOpenSsl {
    $status = Join-Path $installed 'vcpkg/status'
    if (-not (Test-Path -LiteralPath $status -PathType Leaf)) { return $false }
    $port = $manifest.overrides | Where-Object name -eq 'openssl'
    $version = [regex]::Escape($port.version)
    $triplet = [regex]::Escape($pins.vcpkgTriplet)
    $entry = ((Get-Content -LiteralPath $status -Raw) -split '\r?\n\r?\n') | Where-Object {
        $_ -match '(?m)^Package: openssl\r?$' -and $_ -match "(?m)^Version: $version\r?$" -and
        $_ -match "(?m)^Port-Version: $($port.'port-version')\r?$" -and
        $_ -match "(?m)^Architecture: $triplet\r?$" -and $_ -match '(?m)^Status: install ok installed\r?$'
    }
    if (-not $entry) { return $false }
    foreach ($file in @('include/openssl/ssl.h', 'lib/libssl.lib', 'lib/libcrypto.lib')) {
        if (-not (Test-Path -LiteralPath (Join-Path $installed "$($pins.vcpkgTriplet)/$file") -PathType Leaf)) {
            return $false
        }
    }
    return $true
}

$secret = $null
$savedEnvironment = @{}
try {
    $pins = Get-Content -LiteralPath (Join-Path $vendor 'pins.json') -Raw | ConvertFrom-Json
    $manifest = Get-Content -LiteralPath (Join-Path $vendor 'vcpkg.json') -Raw | ConvertFrom-Json
    Assert-Pins $pins $manifest
    $assets = @(
        @{ name='duckdb-v1.4.3.tar.gz'; sha256=$pins.duckdbSha256
            url='https://codeload.github.com/duckdb/duckdb/tar.gz/refs/tags/v1.4.3' }
        @{ name='jevdb-47a9070c.tar.gz'; sha256=$pins.jevdbSha256
            url="https://codeload.github.com/PDAIS/JEVDB/tar.gz/$($pins.jevdbCommit)" }
        @{ name='duckdb_cli-windows-amd64.zip'; sha256=$pins.cliSha256
            url='https://github.com/duckdb/duckdb/releases/download/v1.4.3/duckdb_cli-windows-amd64.zip' }
    )
    $run = Join-Path $cache ("run-" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    $duck = Join-Path $run "duckdb-$($pins.duckdbVersion)"
    $jev = Join-Path $run "JEVDB-$($pins.jevdbCommit)"
    $extension = Join-Path $jev $pins.extensionRelativePath
    $cmakeBuild = @('--build', (Join-Path $jev 'build/release'),
        '--target', 'jevdb_loadable_extension', '--parallel', "$Parallel")
    if ($DryRun) {
        [ordered]@{
            duckdbVersion=$pins.duckdbVersion; vcpkgTriplet=$pins.vcpkgTriplet
            vcpkgBaseline=$pins.vcpkgBaseline; extensionRelativePath=$pins.extensionRelativePath
            extensionPath=$extension; outputDir=$output; assets=$assets
            configure=(Get-ConfigureArgs $duck $jev 'ninja'); build=$cmakeBuild
        } | ConvertTo-Json -Depth 5
        exit 0
    }

    $failure = 'TOOLCHAIN'
    if ($env:VSCMD_ARG_TGT_ARCH -ne 'x64') { throw '请先启动 x64 VS Developer PowerShell。' }
    $cl = Get-Application 'cl.exe'
    $cmake = Get-Application 'cmake.exe'
    $bundledNinja = Join-Path (Split-Path (Split-Path (Split-Path $cmake))) 'Ninja/ninja.exe'
    $ninja = if (Test-Path -LiteralPath $bundledNinja -PathType Leaf) { $bundledNinja }
        else { Get-Application 'ninja.exe' }
    $null = Get-Application 'git.exe'
    $vcpkgExe = Join-Path $vcpkg 'vcpkg.exe'
    if (-not (Test-Path -LiteralPath $vcpkgExe -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $vcpkg 'scripts/buildsystems/vcpkg.cmake') -PathType Leaf)) {
        throw 'vcpkg 或其 CMake toolchain 不存在，请指定 -VcpkgRoot。'
    }
    if (-not $PythonExe) { $PythonExe = "$PSScriptRoot\..\core\.venv\Scripts\python.exe" }
    $python = Get-Application $PythonExe
    $secret = $env:JEV_API_KEY
    foreach ($name in @('JEV_API_KEY', 'VCPKG_DISABLE_METRICS', 'X_VCPKG_REGISTRIES_CACHE',
            'VCPKG_BINARY_SOURCES', 'X_VCPKG_ASSET_SOURCES', 'GIT_TERMINAL_PROMPT', 'GCM_INTERACTIVE')) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    [Environment]::SetEnvironmentVariable('JEV_API_KEY', $null, 'Process')
    $cmakeVersion = @(Invoke-Native $cmake @('--version') -Capture)[0]
    if ($cmakeVersion -notmatch 'cmake version (\d+\.\d+\.\d+)' -or
        [version]$Matches[1] -lt [version]'3.24.0') { throw '需要 CMake 3.24 或更新版本。' }
    $ninjaVersion = @(Invoke-Native $ninja @('--version') -Capture)[0]
    $verifyPython = "import duckdb, struct, sys; assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8 and duckdb.__version__ == '1.4.3'; print(sys.version.split()[0])"
    $pythonVersion = @(Invoke-Native $python @('-I', '-c', $verifyPython) -Capture)[0]

    $failure = 'DOWNLOAD'
    $files = @($assets | ForEach-Object { Get-Archive $_ })
    $report.inputs = @($assets | ForEach-Object { @{ name=$_.name; sha256=$_.sha256 } })
    if ($Preflight) {
        [ordered]@{
            preflight='passed'; cl=$cl; cmake=$cmakeVersion; ninja=$ninjaVersion; python=$pythonVersion
            duckdbVersion=$pins.duckdbVersion; triplet=$pins.vcpkgTriplet
            archivesVerified=$files.Count; opensslReady=(Test-PinnedOpenSsl)
        } | ConvertTo-Json
        exit 0
    }

    $failure = 'CONFIGURE'
    [IO.Directory]::CreateDirectory($run) | Out-Null
    $report.logDir = $run
    $report.cacheRun = [IO.Path]::GetFileName($run)
    if (-not (Test-PinnedOpenSsl)) {
        if ($Offline) { throw '离线缓存中缺少固定的 vcpkg OpenSSL，请先准备依赖。' }
        if ($vcpkgCache -match '[^\x00-\x7F]') {
            throw 'OpenSSL 构建工具 jom 无法读取此 Unicode 缓存路径，请指定短 ASCII -CacheDir。'
        }
        $env:VCPKG_DISABLE_METRICS = '1'
        $env:X_VCPKG_REGISTRIES_CACHE = Join-Path $vcpkgCache 'registries'
        $env:VCPKG_BINARY_SOURCES = 'clear'
        $env:X_VCPKG_ASSET_SOURCES = 'clear'
        $env:GIT_TERMINAL_PROMPT = '0'
        $env:GCM_INTERACTIVE = 'never'
        [IO.Directory]::CreateDirectory($env:X_VCPKG_REGISTRIES_CACHE) | Out-Null
        Push-Location -LiteralPath $vendor
        try {
            Invoke-Native $vcpkgExe @('install', "--triplet=$($pins.vcpkgTriplet)",
                '--host-triplet=x64-windows', "--x-install-root=$installed",
                "--x-buildtrees-root=$(Join-Path $vcpkgCache 'buildtrees')",
                "--x-packages-root=$(Join-Path $vcpkgCache 'packages')",
                "--downloads-root=$(Join-Path $vcpkgCache 'downloads')") (Join-Path $run 'vcpkg.log')
        } finally { Pop-Location }
        if (-not (Test-PinnedOpenSsl)) { throw 'vcpkg 未产出固定的静态 OpenSSL。' }
    }

    $failure = 'DOWNLOAD'
    $extract = Join-Path $vendor 'extract_sources.py'
    Invoke-Native $python @('-I', $extract, $files[0], $run, "duckdb-$($pins.duckdbVersion)") (Join-Path $run 'extract-duckdb.log')
    Invoke-Native $python @('-I', $extract, $files[1], $run, "JEVDB-$($pins.jevdbCommit)") (Join-Path $run 'extract-jevdb.log')
    if (-not (Test-Path -LiteralPath (Join-Path $duck 'CMakeLists.txt') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $jev 'extension_config.cmake') -PathType Leaf) -or
        (Get-Content -LiteralPath (Join-Path $jev 'LICENSE') -TotalCount 1) -cne 'MIT License') {
        throw '固定源码根目录或 MIT 许可证异常。'
    }

    $failure = 'CONFIGURE'
    Invoke-Native $cmake (Get-ConfigureArgs $duck $jev $ninja) (Join-Path $run 'configure.log')
    $failure = 'COMPILE'
    Invoke-Native $cmake $cmakeBuild (Join-Path $run 'compile.log')
    if (-not (Test-Path -LiteralPath $extension -PathType Leaf)) { throw '编译未生成固定路径的扩展。' }

    $failure = 'LOAD'
    $cliDir = Join-Path $run 'cli'
    Expand-Archive -LiteralPath $files[2] -DestinationPath $cliDir
    $cli = Join-Path $cliDir 'duckdb.exe'
    $sqlPath = $extension.Replace('\', '/').Replace("'", "''")
    $sql = "LOAD '$sqlPath'; SELECT jev_keys_overlap(['us:ZZAR'], ['us:ZZAR']);"
    $value = @(Invoke-Native $cli @('-init', 'NUL', '-unsigned', '-batch', '-bail',
        '-noheader', '-csv', ':memory:', '-c', $sql) (Join-Path $run 'load.log') -Capture)
    if ($value.Count -ne 1 -or $value[0].Trim() -cne 'true') { throw 'jev_keys_overlap 未返回 true。' }
    $report.load = 'passed'

    $failure = 'COMPILE'
    [IO.Directory]::CreateDirectory($output) | Out-Null
    $hash = (Get-FileHash -LiteralPath $extension -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::Copy($extension, (Join-Path $output 'jevdb.duckdb_extension'), $true)
    $sum = @("$hash  jevdb.duckdb_extension")
    $sum += @($assets[1], $assets[2] | Sort-Object { $_.name } |
        ForEach-Object { "$($_.sha256)  $($_.name)" })
    [IO.File]::WriteAllLines((Join-Path $output 'SHA256SUMS'), [string[]]$sum, $utf8)
    $report.status = 'built'
    $report.fallback = 'none'
    $report.extensionSha256 = $hash

    if ($SmokeWithJev) {
        $report.smoke = 'blocked_no_key'
        if ($secret -and -not $Offline) {
            $failure = 'SMOKE'
            $report.smoke = 'failed'
            $probe = Join-Path $PSScriptRoot 'probe_jevdb.py'
            if (-not (Test-Path -LiteralPath $probe -PathType Leaf)) { throw 'G0-JEVDB 冒烟探针尚未集成。' }
            $env:JEV_API_KEY = $secret
            try {
                Invoke-Native $python @($probe, '--extension', $extension, '--report', (Join-Path $run 'smoke.json'))
                $report.smoke = 'passed'
            } finally { [Environment]::SetEnvironmentVariable('JEV_API_KEY', $null, 'Process') }
        } elseif ($Offline) { $report.smoke = 'blocked_offline' }
    }
    $exitCode = 0
} catch {
    $exitCode = $exitCodes[$failure]
    $report.errorClass = $failure
    if ($failure -eq 'TOOLCHAIN') { $report.status = 'prerequisite_failed' }
    if ($failure -eq 'LOAD') { $report.status = 'load_failed'; $report.load = 'failed' }
    $report.detail = if ($failure -eq 'SMOKE') { '可选 Jev 冒烟失败。' } else { $_.Exception.Message }
    if ($secret) { $report.detail = $report.detail.Replace($secret, '[REDACTED]') }
    [Console]::Error.WriteLine($report.detail)
} finally {
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
    }
}

if (-not $DryRun) {
    $report.durationSeconds = [int][Math]::Floor($clock.Elapsed.TotalSeconds)
    [IO.Directory]::CreateDirectory($output) | Out-Null
    $json = $report | ConvertTo-Json -Depth 4
    $temporaryReport = Join-Path $output ("build-result-" + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($temporaryReport, $json + [Environment]::NewLine, $utf8)
        Move-Item -LiteralPath $temporaryReport -Destination (Join-Path $output 'build-result.json') -Force
    } finally { [IO.File]::Delete($temporaryReport) }
    Write-Output $json
}
exit $exitCode

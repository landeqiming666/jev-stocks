<#
.SYNOPSIS
运行 Windows MVP-0 的离线无窗口预检，生成独立的 acceptance.json。
.DESCRIPTION
在当前工作树执行真实的安装、门禁和可用的专项测试。默认离线。
本阶段需另行采集 WebView2 窗口、用户故事录屏和凭据管理器证据。
#>
[CmdletBinding()]
param(
    [switch]$Offline = $true,
    [switch]$NoLaunch,
    [switch]$SkipInstall,
    [string]$ReportDir = "$PSScriptRoot\..\apps\desktop\e2e\windows\results",
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT' -or -not $Offline) {
    Write-Output '本预检需要 Windows 和离线模式。'
    exit 2
}

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$core = Join-Path $repo 'core'

function New-Outcome {
    param([string]$Status = 'not_run', [string]$Reason = '', $Evidence = $null, $ExitCode = $null)
    [ordered]@{status = $Status; reason = $Reason; evidence = $Evidence; exitCode = $ExitCode}
}

function Get-AcceptanceExitCode {
    param([object[]]$Outcomes)
    if ($Outcomes | Where-Object { $_.status -eq 'fail' }) { return 1 }
    if ($Outcomes | Where-Object { $_.status -ne 'pass' }) { return 3 }
    return 0
}

$checks = [ordered]@{}
foreach ($index in 1..5) {
    $checks["WM-$index"] = New-Outcome -Reason '尚未采集证据。'
}
$checks['WM-2'].reason = '尚未采集真实 WebView2 窗口、原生标题栏和六页截图。'
$checks['WM-3'].reason = '尚未完成真实核心联调和 US-01 至 US-15 的 Windows 录屏。'
$checks['WM-4'].reason = '尚未完成 WinVault 自动验证和凭据管理器人工查看。'
$checks['WM-5'].reason = '等待 W-03 构建记录和 Windows 最终门槛 ADR。'
$report = [ordered]@{
    schema = 'windows-acceptance/1'
    platform = 'windows'
    osBuild = $null
    architecture = $null
    repoPath = $repo
    gitHead = $null
    timestampUtc = [DateTime]::UtcNow.ToString('o')
    offline = $true
    noLaunch = $true
    launchRequested = -not [bool]$NoLaunch
    prerequisites = [ordered]@{}
    dependencies = [ordered]@{}
    checks = $checks
    bridge = New-Outcome -Reason '当前工作树缺少 W-02 测试。'
    credentials = New-Outcome -Reason '当前工作树缺少 W-04 测试。'
    integration = New-Outcome -Reason '当前工作树缺少 I-01 测试、C-07 入口或 E-01 演示加载器。'
    jevdb = [ordered]@{status = 'not_run'; built = $null; fallback = $null; evidence = $null}
    overall = 'fail'
    exitCode = 2
}

$pathMatches = $repo -match ' ' -and $repo -match '\p{IsCJKUnifiedIdeographs}'
if ($SelfTest) {
    if (-not $pathMatches) { throw 'test_repo_path_contains_space_and_chinese' }
    if (($report.checks.Keys -join ',') -ne 'WM-1,WM-2,WM-3,WM-4,WM-5') {
        throw 'test_result_json_has_five_checks'
    }
    if ($report.checks['WM-2'].status -ne 'not_run' -or
        $report.checks['WM-3'].status -ne 'not_run' -or $report.overall -ne 'fail' -or
        (Get-AcceptanceExitCode -Outcomes @($checks.Values)) -ne 3) {
        throw 'test_no_launch_marks_wm2_wm3_not_run'
    }
    Write-Output 'Windows smoke report self-tests passed (3).'
    exit 0
}

$reportPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ReportDir)
$reportRoot = [IO.Directory]::CreateDirectory($reportPath).FullName
$runDir = Join-Path $reportRoot ([DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($runDir) | Out-Null

function Invoke-Recorded {
    param([string]$Name, [string]$Command, [string[]]$Arguments = @(), [string]$WorkDir = $repo)
    $log = Join-Path $runDir "$Name.log"
    $consoleEncoding = [Console]::OutputEncoding
    Push-Location -LiteralPath $WorkDir
    try {
        $ErrorActionPreference = 'Continue'
        $PSNativeCommandUseErrorActionPreference = $false
        [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
        if ([IO.Path]::GetExtension($Command) -eq '.ps1') {
            # Keep a wrapper's Stop preference from aborting stderr capture in WinPS 5.1.
            $Arguments = @('-NoProfile', '-File', $Command) + $Arguments
            $Command = (Get-Process -Id $PID).Path
        }
        $global:LASTEXITCODE = -1
        & $Command @Arguments 2>&1 | Out-File -LiteralPath $log -Encoding utf8 -Width 4096
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) {
            return New-Outcome -Status 'pass' -Evidence $log -ExitCode 0
        }
        return New-Outcome -Status 'fail' -Reason "进程退出 $exitCode。" -Evidence $log -ExitCode $exitCode
    }
    catch {
        $_.Exception.GetType().Name | Out-File -LiteralPath $log -Encoding utf8 -Append
        return New-Outcome -Status 'fail' -Reason '命令执行失败。' -Evidence $log -ExitCode 1
    }
    finally {
        [Console]::OutputEncoding = $consoleEncoding
        Pop-Location
    }
}

function Read-JevdbResult {
    $build = Join-Path $repo 'vendors\jevdb-msvc\artifacts\x64-windows\build-result.json'
    if (-not (Test-Path -LiteralPath $build -PathType Leaf)) {
        return
    }
    $report.jevdb.evidence = $build
    try {
        $result = Get-Content -LiteralPath $build -Raw -Encoding utf8 | ConvertFrom-Json
        if ($result.duckdbVersion -ne '1.4.3' -or $result.triplet -ne 'x64-windows-static-md') {
            throw 'W-03 version or triplet mismatch'
        }
        if ($result.status -eq 'built') {
            $extension = Join-Path (Split-Path -Parent $build) 'jevdb.duckdb_extension'
            if ($result.fallback -ne 'none' -or $result.extensionSha256 -notmatch '^[0-9a-fA-F]{64}$' -or
                (Get-FileHash -LiteralPath $extension -Algorithm SHA256).Hash -ne $result.extensionSha256) {
                throw 'W-03 extension hash mismatch'
            }
            $report.jevdb.built = $true
        }
        elseif ($result.status -in @('load_failed', 'build_failed', 'prerequisite_failed') -and
            $result.fallback -eq 'jev_direct') {
            $report.jevdb.built = $false
        }
        else {
            throw 'W-03 result status mismatch'
        }
        $report.jevdb.status = $result.status
        $report.jevdb.fallback = $result.fallback
        $report.jevdb.errorClass = $result.errorClass
        $report.checks['WM-5'] = New-Outcome -Reason 'W-03 构建结果已记录，等待 Windows 最终门槛 ADR。' -Evidence $build
    }
    catch {
        $report.jevdb.status = 'fail'
        $report.checks['WM-5'] = New-Outcome -Status 'fail' -Reason 'W-03 版本、状态或产物哈希无法核验。' -Evidence $build
    }
}

$environment = [ordered]@{
    UV_OFFLINE = '1'
    CARGO_NET_OFFLINE = 'true'
    npm_config_offline = 'true'
    PYTHONUTF8 = '1'
    PYTHONIOENCODING = 'utf-8'
    SENTINEL_OFFLINE = $null
    JEV_API_KEY = $null
    TYPESAFE_API_KEY = $null
    SENTINEL_DATA_DIR = (Join-Path ([IO.Path]::GetTempPath()) ('sentinel-验收 空格-' + [Guid]::NewGuid().ToString('N')))
}
$saved = @{}
foreach ($name in $environment.Keys) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name)
    [Environment]::SetEnvironmentVariable($name, $environment[$name])
}

try {
    $windows = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    $report.osBuild = "$($windows.CurrentBuildNumber).$($windows.UBR)"
    $report.architecture = [string][Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    $report.prerequisites.displayVersion = $windows.DisplayVersion
    $report.prerequisites.pathContainsSpaceAndChinese = $pathMatches
    $report.dependencies['I-01'] = Test-Path -LiteralPath (Join-Path $core 'tests\integration\test_core_lifecycle.py') -PathType Leaf
    $report.dependencies['C-07'] = (Test-Path -LiteralPath (Join-Path $core 'sentinel\__main__.py') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $core 'sentinel\app') -PathType Container)
    $report.dependencies['E-01'] = Test-Path -LiteralPath (Join-Path $PSScriptRoot 'load_demo.py') -PathType Leaf
    if ([int]$windows.CurrentBuildNumber -lt 22000 -or $report.architecture -ne 'X64' -or -not $pathMatches) {
        throw '前置环境需要 Windows 11 x64 和包含中文、空格的仓库路径。'
    }
    $webview = Get-ChildItem -Path @(
        "${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe",
        "$env:LOCALAPPDATA\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe"
    ) -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $webview) { throw '缺少可识别的 WebView2 Runtime。' }
    $report.prerequisites.webView2Version = $webview.VersionInfo.ProductVersion
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere -PathType Leaf) {
        $report.prerequisites.msvc = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
    }
    if (-not $report.prerequisites.msvc) { throw '缺少 Visual Studio x64 C++ 工具链。' }
    $report.prerequisites.doctor = Invoke-Recorded 'doctor' (Join-Path $PSScriptRoot 'doctor.ps1')
    if ($report.prerequisites.doctor.status -ne 'pass') { throw '工具链体检失败，见 doctor.log。' }
    $report.gitHead = & git -C $repo rev-parse HEAD 2>$null
    if (-not $SkipInstall) {
        $report.prerequisites.setup = Invoke-Recorded 'setup' (Join-Path $PSScriptRoot 'setup.ps1')
        if ($report.prerequisites.setup.status -ne 'pass') { throw '离线依赖安装失败，见 setup.log。' }
    }
    else {
        $report.prerequisites.setup = New-Outcome -Reason '按 -SkipInstall 使用现有本地依赖。'
    }

    $report.checks['WM-1'] = Invoke-Recorded 'check' (Join-Path $PSScriptRoot 'check.ps1')
    $tauri = Join-Path $repo 'apps\desktop\src-tauri'
    if (Test-Path -LiteralPath (Join-Path $tauri 'tests\bridge_windows.rs') -PathType Leaf) {
        $report.bridge = Invoke-Recorded 'bridge' 'cargo' @('test', '--offline', '--test', 'bridge_windows') $tauri
    }
    if ($report.dependencies['I-01'] -and $report.dependencies['C-07'] -and $report.dependencies['E-01']) {
        # Unit tests exercise mocked transports. The real-core suite uses offline mode.
        $env:SENTINEL_OFFLINE = '1'
        try {
            $report.integration = Invoke-Recorded 'integration' 'uv' @(
                'run', '--offline', 'pytest', 'tests/integration', '-q', '-m', 'integration and not network'
            ) $core
        }
        finally {
            Remove-Item Env:SENTINEL_OFFLINE
        }
    }
    if ((Test-Path -LiteralPath (Join-Path $core 'tests\unit\secrets\test_windows_backend.py') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $core 'sentinel\secrets\windows_backend.py') -PathType Leaf)) {
        $report.credentials = Invoke-Recorded 'credentials' 'uv' @(
            'run', '--offline', 'pytest', 'tests/unit/secrets/test_windows_backend.py', '-q', '-m', 'windows'
        ) $core
        if ($report.credentials.status -eq 'pass') {
            $probeCode = 'import json; from dataclasses import asdict; from sentinel.secrets.windows_backend import WindowsCredentialBackend; print(json.dumps(asdict(WindowsCredentialBackend().probe())))'
            $probe = Invoke-Recorded 'credential-probe' 'uv' @('run', '--offline', '--no-sync', 'python', '-c', $probeCode) $core
            $report.credentials.probe = $probe
            $checks['WM-4'] = New-Outcome -Reason 'WinVault 自动项通过，等待凭据管理器人工查看。' -Evidence $probe.evidence
            try {
                $details = Get-Content -LiteralPath $probe.evidence -Raw -Encoding utf8 | ConvertFrom-Json
                if ($probe.status -ne 'pass' -or $details.backend -ne 'Windows Credential Locker' -or
                    $details.write_ok -ne $true -or $details.read_ok -ne $true -or $details.delete_ok -ne $true) {
                    throw 'WinVault probe failed'
                }
                $report.credentials.probe.result = [ordered]@{
                    backend = $details.backend
                    service = $details.service
                    account = $details.account
                    write_ok = $details.write_ok
                    read_ok = $details.read_ok
                    delete_ok = $details.delete_ok
                }
            }
            catch {
                $checks['WM-4'] = New-Outcome -Status 'fail' -Reason 'WinVault 探针未完成读写删除。' -Evidence $probe.evidence
            }
        }
        else {
            $checks['WM-4'] = $report.credentials
        }
    }
    Read-JevdbResult
    $outcomes = @($checks.Values) + @($report.bridge, $report.integration, $report.credentials)
    $report.exitCode = Get-AcceptanceExitCode -Outcomes $outcomes
    if ($report.exitCode -eq 0) { $report.overall = 'pass' }
}
catch {
    $report.prerequisites.failure = $_.Exception.Message
}
finally {
    foreach ($name in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name])
    }
    $runReport = Join-Path $runDir 'acceptance.json'
    $encoding = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText($runReport, ($report | ConvertTo-Json -Depth 12) + [Environment]::NewLine, $encoding)
    Copy-Item -LiteralPath $runReport -Destination (Join-Path $reportRoot 'acceptance.json') -Force
}

$summary = ($checks.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value.status)" }) -join ' '
Write-Output "WINDOWS ACCEPTANCE $($report.overall.ToUpperInvariant()) $summary"
Write-Output "Report: $runReport"
exit $report.exitCode

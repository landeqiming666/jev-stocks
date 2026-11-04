<#
.SYNOPSIS
运行 Windows MVP-0 离线验收，生成独立的 acceptance.json。
.DESCRIPTION
在当前工作树执行真实的安装、门禁和可用的专项测试。默认离线。
有可用的业务页面和测试账户时，可启动原生窗口并记录进程退出。
#>
[CmdletBinding()]
param(
    [switch]$Offline = $true,
    [switch]$NoLaunch,
    [switch]$SkipInstall,
    [string]$ReportDir = "$PSScriptRoot\..\apps\desktop\e2e\windows\results",
    [ValidateRange(5, 3600)][int]$WindowCloseTimeoutSeconds = 900,
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
    noLaunch = [bool]$NoLaunch
    launchRequested = -not [bool]$NoLaunch
    prerequisites = [ordered]@{}
    dependencies = [ordered]@{}
    checks = $checks
    bridge = New-Outcome -Reason '当前工作树缺少 W-02 测试。'
    realBridge = New-Outcome -Reason '等待 C-07 提供真实核心入口。'
    credentials = New-Outcome -Reason '当前工作树缺少 W-04 测试。'
    integration = New-Outcome -Reason '当前工作树缺少 I-01 测试、C-07 入口或 E-01 演示加载器。'
    demo = New-Outcome -Reason '当前工作树缺少 E-01 演示加载器。'
    browser = New-Outcome -Reason '尚未执行 Windows Edge 外壳测试。'
    desktop = New-Outcome -Reason '尚未启动本次验收的原生窗口。'
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
    param([string]$Name, [string]$Command, [string[]]$Arguments = @(), [string]$WorkDir = $repo,
        [switch]$JsonOutput)
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
        if ($JsonOutput) {
            $stderr = Join-Path $runDir "$Name.stderr.log"
            & $Command @Arguments 2> $stderr | Out-File -LiteralPath $log -Encoding utf8 -Width 4096
        }
        else {
            & $Command @Arguments 2>&1 | Out-File -LiteralPath $log -Encoding utf8 -Width 4096
        }
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

function Invoke-DemoLoad {
    $outcome = Invoke-Recorded 'load-demo' 'uv' @(
        'run', '--offline', '--project', $core, 'python', 'scripts/load_demo.py',
        '--data-dir', $env:SENTINEL_DATA_DIR, '--json'
    ) -JsonOutput
    if ($outcome.status -ne 'pass') { return $outcome }
    try {
        $demoResult = Get-Content -LiteralPath $outcome.evidence -Raw -Encoding utf8 | ConvertFrom-Json
        $counts = if ($null -ne $demoResult.counts) { $demoResult.counts } else { $demoResult }
        $expected = [ordered]@{instruments = 6; holdings = 5; theses = 6; events = 6; decisions = 12; prices = 1560}
        foreach ($name in $expected.Keys) {
            $value = $counts.$name
            if (($value -isnot [int] -and $value -isnot [long]) -or $value -ne $expected[$name]) {
                throw "演示数据计数错误：$name。"
            }
        }
        $outcome.counts = $expected
    }
    catch {
        return New-Outcome -Status 'fail' -Reason $_.Exception.Message -Evidence $outcome.evidence -ExitCode 1
    }
    return $outcome
}

function Invoke-NativeDesktop {
    $collector = Join-Path $repo 'apps/desktop/e2e/windows/collect-evidence.ps1'
    $devLog = Join-Path $runDir 'native-dev.log'
    $devErrors = Join-Path $runDir 'native-dev-errors.log'
    $devArguments = '-NoProfile -File "' + (Join-Path $PSScriptRoot 'dev.ps1') + '" --no-watch'
    $launch = $null
    $snapshot = $null
    $phase = 'WM-2'
    try {
        $launch = Start-Process -FilePath (Get-Process -Id $PID).Path -ArgumentList $devArguments `
            -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $devLog -RedirectStandardError $devErrors
        $snapshot = & $collector -LaunchPid $launch.Id -ReportDir $runDir -WaitSeconds 180
        if ($snapshot.window.title -cne '投资逻辑哨兵' -or -not $snapshot.window.nativeCaption) {
            throw '原生窗口的标题或标题栏不符合验收条件。'
        }
        $checks['WM-2'] = New-Outcome -Reason '原生标题栏已核验，等待六页截图。' -Evidence $snapshot.evidencePath
        $phase = 'WM-3'
        Write-Host "原生窗口已启动，PID $($snapshot.window.pid)。证据目录：$runDir"
        Write-Host '请完成实机联调清单后关闭窗口。'
        $exitEvidence = & $collector -BaselinePath $snapshot.evidencePath -ReportDir $runDir -WaitSeconds 5 `
            -WindowCloseTimeoutSeconds $WindowCloseTimeoutSeconds
        if (-not $exitEvidence.allObservedExited) {
            $checks['WM-3'] = New-Outcome -Status 'fail' -Reason '观测到本次启动的进程残留。' `
                -Evidence $exitEvidence.evidencePath -ExitCode 1
            return $checks['WM-3']
        }
        if ($launch.ExitCode -ne 0) {
            $checks['WM-3'] = New-Outcome -Status 'fail' -Reason "开发启动器退出 $($launch.ExitCode)。" `
                -Evidence $devLog -ExitCode $launch.ExitCode
            return $checks['WM-3']
        }
        $checks['WM-3'] = New-Outcome -Reason '已核验观测到的进程退出，等待业务录屏。' -Evidence $exitEvidence.evidencePath
        $result = New-Outcome -Status 'pass' -Evidence $snapshot.evidencePath -ExitCode 0
        $result.exitEvidence = $exitEvidence.evidencePath
        return $result
    }
    catch {
        $evidence = if ($snapshot) { $snapshot.evidencePath } else { $devLog }
        $checks[$phase] = New-Outcome -Status 'fail' -Reason $_.Exception.Message -Evidence $evidence -ExitCode 1
        return $checks[$phase]
    }
    finally {
        if ($launch) {
            if (-not $launch.HasExited) {
                $ErrorActionPreference = 'Continue'
                $PSNativeCommandUseErrorActionPreference = $false
                & "$env:SystemRoot\System32\taskkill.exe" /PID $launch.Id /T /F 2>&1 |
                    Out-File -LiteralPath (Join-Path $runDir 'native-cleanup.log') -Encoding utf8
                [void]$launch.WaitForExit(5000)
            }
            $launch.Dispose()
        }
    }
}

$environment = [ordered]@{
    UV_OFFLINE = '1'
    CARGO_NET_OFFLINE = 'true'
    npm_config_offline = 'true'
    PYTHONUTF8 = '1'
    PYTHONIOENCODING = 'utf-8'
    PYTEST_ADDOPTS = $null
    SENTINEL_OFFLINE = $null
    SENTINEL_CLOCK = $null
    JEV_API_KEY = $null
    TYPESAFE_API_KEY = $null
    SENTINEL_CORE_CMD = $null
    VITE_RPC = 'tauri'
    WEBVIEW2_USER_DATA_FOLDER = (Join-Path $runDir 'webview')
    SENTINEL_WINDOWS_PLAYWRIGHT_OUTPUT = (Join-Path $runDir 'playwright')
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
        (Test-Path -LiteralPath (Join-Path $core 'sentinel\app\main.py') -PathType Leaf)
    $report.dependencies['E-01'] = Test-Path -LiteralPath (Join-Path $PSScriptRoot 'load_demo.py') -PathType Leaf
    $report.prerequisites.disposableProfileConfirmed = $env:SENTINEL_WINDOWS_DISPOSABLE_PROFILE -ceq '1'
    $missingPages = @('today', 'holdings', 'trading', 'risk', 'scan', 'settings' | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $repo "apps/desktop/src/pages/$_/index.tsx") -PathType Leaf)
    })
    $report.dependencies['businessPages'] = $missingPages.Count -eq 0
    $report.missingBusinessPages = $missingPages
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

    $env:PYTEST_ADDOPTS = '-m "not integration and not network"'
    try { $report.checks['WM-1'] = Invoke-Recorded 'check' (Join-Path $PSScriptRoot 'check.ps1') }
    finally { Remove-Item Env:PYTEST_ADDOPTS }
    $tauri = Join-Path $repo 'apps\desktop\src-tauri'
    if (Test-Path -LiteralPath (Join-Path $tauri 'tests\bridge_windows.rs') -PathType Leaf) {
        $report.bridge = Invoke-Recorded 'bridge' 'cargo' @('test', '--offline', '--test', 'bridge_windows') $tauri
        if ($report.dependencies['C-07'] -and $report.prerequisites.disposableProfileConfirmed) {
            $report.realBridge = Invoke-Recorded 'bridge-real' 'cargo' @(
                'test', '--locked', '--offline', '--test', 'bridge_windows',
                'test_real_core_accepts_bootstrap_on_windows', '--', '--ignored', '--exact'
            ) $tauri
        }
        elseif ($report.dependencies['C-07']) {
            $report.realBridge.reason = '真实核心测试需要专用 Windows 测试账户。'
        }
    }
    if ($report.dependencies['I-01'] -and $report.dependencies['C-07'] -and $report.dependencies['E-01'] -and
        $report.prerequisites.disposableProfileConfirmed) {
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
    elseif ($report.dependencies['I-01'] -and $report.dependencies['C-07'] -and $report.dependencies['E-01']) {
        $report.integration.reason = '请在专用 Windows 测试账户中确认凭据隔离后运行真实核心验收。'
    }
    if ($report.checks['WM-1'].status -eq 'pass') {
        if ($report.dependencies['E-01']) {
            $env:SENTINEL_OFFLINE = '1'
            $env:SENTINEL_CLOCK = '2026-11-02T08:35:00Z'
            $env:SENTINEL_DATA_DIR = Join-Path $runDir 'demo-cli'
            try {
                $report.demo = Invoke-DemoLoad
                $report.demo.dataDir = $env:SENTINEL_DATA_DIR
            }
            finally {
                Remove-Item Env:SENTINEL_OFFLINE
                Remove-Item Env:SENTINEL_CLOCK
                $env:SENTINEL_DATA_DIR = $environment.SENTINEL_DATA_DIR
            }
        }
        $report.browser = Invoke-Recorded 'playwright' 'pnpm.cmd' @(
            '--dir', 'apps/desktop', 'exec', 'playwright', 'test',
            '--config', 'e2e/windows/playwright.config.ts'
        )
        $report.browser.artifacts = $env:SENTINEL_WINDOWS_PLAYWRIGHT_OUTPUT
    }
    if ((Test-Path -LiteralPath (Join-Path $core 'tests\unit\secrets\test_windows_backend.py') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $core 'sentinel\secrets\windows_backend.py') -PathType Leaf)) {
        $report.credentials = Invoke-Recorded 'credentials' 'uv' @(
            'run', '--offline', 'pytest', 'tests/unit/secrets/test_windows_backend.py', '-q', '-m', 'windows'
        ) $core
        if ($report.credentials.status -eq 'pass') {
            $probeCode = 'import json; from dataclasses import asdict; from sentinel.secrets.windows_backend import WindowsCredentialBackend; print(json.dumps(asdict(WindowsCredentialBackend().probe())))'
            $probe = Invoke-Recorded 'credential-probe' 'uv' @('run', '--offline', '--no-sync', 'python', '-c', $probeCode) $core -JsonOutput
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
    $unfinished = @(
        @($report.checks['WM-1'], $report.bridge, $report.realBridge, $report.integration,
            $report.demo, $report.browser, $report.credentials) |
            Where-Object { $_.status -ne 'pass' }
    )
    if ($NoLaunch) {
        $report.desktop.reason = '按 -NoLaunch 跳过原生窗口。'
    }
    elseif (-not [Environment]::UserInteractive) {
        $report.desktop.reason = '当前会话没有交互式桌面。'
    }
    elseif (-not $report.dependencies['businessPages'] -or $unfinished.Count -gt 0 -or
        $checks['WM-4'].status -eq 'fail' -or $checks['WM-5'].status -eq 'fail') {
        $report.desktop.reason = '等待真实核心、演示数据、业务页面和自动检查就绪。'
    }
    else {
        $env:SENTINEL_OFFLINE = '1'
        $env:SENTINEL_CLOCK = '2026-11-02T08:35:00Z'
        $env:SENTINEL_DATA_DIR = Join-Path $runDir 'desktop-data'
        $report.desktop = Invoke-NativeDesktop
        $report.desktop.dataDir = $env:SENTINEL_DATA_DIR
    }
    $outcomes = @($checks.Values) + @(
        $report.bridge, $report.realBridge, $report.integration, $report.demo, $report.browser,
        $report.credentials, $report.desktop
    )
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

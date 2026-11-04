param(
    [string]$VcpkgRoot = 'C:\tools\vcpkg',
    [string]$PythonExe,
    [string]$VerifiedOutputDir = "$PSScriptRoot\artifacts\x64-windows"
)

$ErrorActionPreference = 'Stop'
$scriptPath = [IO.Path]::GetFullPath("$PSScriptRoot\..\..\scripts\build_jevdb_msvc.ps1")
$shell = (Get-Process -Id $PID).Path
$fixtureRoot = [IO.Path]::GetFullPath("$PSScriptRoot\.cache")
$fixture = Join-Path $fixtureRoot ("test-" + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($fixture) | Out-Null
$pins = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'pins.json') -Raw | ConvertFrom-Json
$script:passed = 0
$script:failed = 0
$script:skipped = 0

function Assert-That([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Invoke-Driver([string[]]$Arguments) {
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    $lines = & $shell -NoProfile -ExecutionPolicy Bypass -File $scriptPath @Arguments 2>&1
    [pscustomobject]@{ code=$LASTEXITCODE; text=($lines | Out-String) }
}

function Test-Case([string]$Name, [scriptblock]$Body) {
    try {
        & $Body
        $script:passed++
        Write-Output "PASS $Name"
    } catch {
        $script:failed++
        Write-Output "FAIL $Name $($_.Exception.Message)"
    }
}

function Invoke-BadArchive([string]$Directory) {
    $archives = Join-Path $Directory 'bad-archives'
    [IO.Directory]::CreateDirectory($archives) | Out-Null
    [IO.File]::WriteAllText((Join-Path $archives 'duckdb-v1.4.3.tar.gz'), 'deliberately invalid')
    $arguments = @('-Offline', '-SmokeWithJev', '-ArchiveDir', $archives, '-CacheDir',
        (Join-Path $Directory 'cache'), '-OutputDir', $Directory, '-VcpkgRoot', $VcpkgRoot)
    if ($PythonExe) { $arguments += @('-PythonExe', $PythonExe) }
    return Invoke-Driver $arguments
}

try {
    $dryOutput = Join-Path $fixture 'dry-output'
    $dryCache = Join-Path $fixture 'dry-cache'
    $dry = Invoke-Driver @('-DryRun', '-OutputDir', $dryOutput, '-CacheDir', $dryCache)
    Test-Case 'Test-DryRunWritesNoFiles' {
        Assert-That ($dry.code -eq 0) 'dry run failed'
        Assert-That (-not (Test-Path -LiteralPath $dryOutput)) 'dry run wrote an output directory'
        Assert-That (-not (Test-Path -LiteralPath $dryCache)) 'dry run wrote a cache directory'
    }
    Test-Case 'Test-PinsMatchRequiredVersions' {
        Assert-That ($pins.duckdbVersion -ceq '1.4.3') 'DuckDB version mismatch'
        Assert-That ($pins.jevdbCommit -cmatch '^[0-9a-f]{40}$') 'JEVDB commit is invalid'
        Assert-That ($pins.vcpkgTriplet -ceq 'x64-windows-static-md') 'vcpkg triplet mismatch'
    }
    Test-Case 'Test-MissingCompilerExitsTen' {
        $originalPath = $env:PATH
        $originalTarget = $env:VSCMD_ARG_TGT_ARCH
        $destination = Join-Path $fixture 'missing-tool'
        try {
            $env:PATH = ''
            $env:VSCMD_ARG_TGT_ARCH = 'x64'
            $result = Invoke-Driver @('-Offline', '-OutputDir', $destination)
        } finally {
            [Environment]::SetEnvironmentVariable('PATH', $originalPath, 'Process')
            [Environment]::SetEnvironmentVariable('VSCMD_ARG_TGT_ARCH', $originalTarget, 'Process')
        }
        $data = Get-Content -LiteralPath (Join-Path $destination 'build-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-That ($result.code -eq 10 -and $data.errorClass -eq 'TOOLCHAIN' -and
            $data.status -eq 'prerequisite_failed' -and $data.fallback -eq 'jev_direct') 'expected exit 10 / TOOLCHAIN'
    }
    Test-Case 'Test-BadDuckDbHashExitsTwenty' {
        $destination = Join-Path $fixture 'bad-hash'
        $result = Invoke-BadArchive $destination
        $data = Get-Content -LiteralPath (Join-Path $destination 'build-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        Assert-That ($result.code -eq 20 -and $data.errorClass -eq 'DOWNLOAD' -and
            $data.detail -match 'SHA-256' -and -not $data.logDir) 'expected hash failure before configuration'
    }
    Test-Case 'Test-OutputPathIsExact' {
        $plan = $dry.text | ConvertFrom-Json
        Assert-That ($plan.extensionRelativePath -ceq $pins.extensionRelativePath -and
            ($plan.extensionPath -replace '\\', '/') -clike "*/$($pins.extensionRelativePath)") 'extension path mismatch'
        Assert-That ($plan.configure -contains '-DOVERRIDE_GIT_DESCRIBE=v1.4.3-0-gd1dc88f950') 'source_id mismatch'
    }
    if (Test-Path -LiteralPath (Join-Path $VerifiedOutputDir 'SHA256SUMS') -PathType Leaf) {
        Test-Case 'Test-ShaFileHasThreeEntries' {
            $result = Get-Content -LiteralPath (Join-Path $VerifiedOutputDir 'build-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            $artifact = Join-Path $VerifiedOutputDir 'jevdb.duckdb_extension'
            $hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant()
            $sums = @(Get-Content -LiteralPath (Join-Path $VerifiedOutputDir 'SHA256SUMS'))
            Assert-That ($result.status -eq 'built' -and $result.load -eq 'passed' -and
                $result.extensionSha256 -ceq $hash) 'native extension or result identity mismatch'
            Assert-That ($sums.Count -eq 3 -and $sums -ccontains "$hash  jevdb.duckdb_extension" -and
                $sums -ccontains "$($pins.jevdbSha256)  jevdb-47a9070c.tar.gz" -and
                $sums -ccontains "$($pins.cliSha256)  duckdb_cli-windows-amd64.zip") 'checksum file mismatch'
        }
    } else {
        $script:skipped++
        Write-Output 'SKIP Test-ShaFileHasThreeEntries，需要本机已加载产物'
    }
    Test-Case 'Test-NoSecretInLogs' {
        $destination = Join-Path $fixture 'secret'
        $original = $env:JEV_API_KEY
        $canary = 'w03-fake-key-' + [Guid]::NewGuid().ToString('N')
        try {
            $env:JEV_API_KEY = $canary
            $result = Invoke-BadArchive $destination
        } finally { [Environment]::SetEnvironmentVariable('JEV_API_KEY', $original, 'Process') }
        $json = Get-Content -LiteralPath (Join-Path $destination 'build-result.json') -Raw -Encoding UTF8
        Assert-That ($result.code -eq 20 -and -not ($result.text + $json).Contains($canary)) 'secret appeared in failed run output'
    }
} finally {
    $resolved = (Resolve-Path -LiteralPath $fixture).Path
    if ($resolved.StartsWith($fixtureRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
Write-Output "$passed passed; $failed failed; $skipped skipped"
if ($failed) { exit 1 }
exit 0

<#
.SYNOPSIS
将同一次 Windows 原生验收的人工复核证据汇入 reviewed-acceptance.json。
.DESCRIPTION
RunDir 指向一次验收的子目录，其中应有 acceptance.json 和 manual-review.json。
原始报告保持原样。证据路径相对于 RunDir，禁止引用目录外的文件。
#>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$RunDir)

$ErrorActionPreference = 'Stop'

function Get-RunFile {
    param([string]$RelativePath)

    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [IO.Path]::IsPathRooted($RelativePath)) {
        throw '证据需要使用本次验收目录内的相对路径。'
    }
    $path = $root
    foreach ($part in ($RelativePath -split '[\\/]')) {
        if ($part -in @('', '.', '..') -or $part.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
            $part.EndsWith('.') -or $part.EndsWith(' ')) {
            throw "证据路径无效：$RelativePath。"
        }
        $path = Join-Path $path $part
        $file = Get-Item -LiteralPath $path -Force
        if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "证据路径包含重解析点：$RelativePath。"
        }
    }
    if ($file.PSIsContainer -or $file.Length -le 0) {
        throw "证据文件不存在或为空：$RelativePath。"
    }
    return $file
}

function Read-RunJson {
    param([string]$Name)
    Get-Content -LiteralPath (Get-RunFile $Name).FullName -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Get-Sha256 {
    param([string]$Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try { [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose() }
    }
    finally { $sha.Dispose() }
}

function Get-Artifact {
    param([string]$Path, [string[]]$Extensions)

    $file = Get-RunFile $Path
    if ($file.Extension -notin $Extensions) { throw "证据文件类型无效：$Path。" }
    $header = [byte[]]::new(12)
    $stream = [IO.File]::OpenRead($file.FullName)
    try { $length = $stream.Read($header, 0, $header.Length) }
    finally { $stream.Dispose() }
    $magic = [BitConverter]::ToString($header, 0, $length)
    $valid = switch ($file.Extension.ToLowerInvariant()) {
        '.png' { $magic.StartsWith('89-50-4E-47-0D-0A-1A-0A') }
        { $_ -in '.jpg', '.jpeg' } { $magic.StartsWith('FF-D8-FF') }
        '.mp4' { $length -ge 12 -and [Text.Encoding]::ASCII.GetString($header, 4, 4) -ceq 'ftyp' }
        '.webm' { $magic.StartsWith('1A-45-DF-A3') }
    }
    if (-not $valid) { throw "证据文件头与扩展名不符：$Path。" }
    return [ordered]@{
        path = $file.FullName.Substring($root.Length + 1)
        bytes = $file.Length
        sha256 = Get-Sha256 $file.FullName
    }
}

function Test-Number {
    param($Value)
    ($Value -is [int] -or $Value -is [long] -or $Value -is [double]) -and
        -not [double]::IsNaN($Value) -and -not [double]::IsInfinity($Value)
}

function Get-ReviewStatus {
    param([int]$Required, [object[]]$Statuses)
    if ('fail' -cin $Statuses) { return 'fail' }
    if ($Statuses.Count -ne $Required) { return 'not_run' }
    return 'pass'
}

function Set-ReviewedCheck {
    param([string]$Name, [string]$Status, [bool]$AutomaticGate)

    $check = $report.checks.PSObject.Properties[$Name].Value
    if (-not $AutomaticGate -or $check.status -ceq 'fail' -or $Status -ceq 'not_run') { return }
    $check.status = $Status
    $check.reason = if ($Status -ceq 'pass') { '同次原生验收及人工证据通过。' } else { '人工证据记录了验收失败。' }
    $check.evidence = $manualPath
    $check.exitCode = if ($Status -ceq 'pass') { 0 } else { 1 }
}

try {
    $directory = Get-Item -LiteralPath $RunDir -Force
    if (-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'RunDir 必须是实际的单次验收目录。'
    }
    $root = $directory.FullName.TrimEnd('\', '/')
    $rawPath = (Get-RunFile 'acceptance.json').FullName
    $manualFile = Get-RunFile 'manual-review.json'
    $manualPath = $manualFile.FullName
    $report = Read-RunJson 'acceptance.json'
    $manual = Read-RunJson 'manual-review.json'
    $states = @('pass', 'fail', 'not_run')
    $checks = 1..5 | ForEach-Object { "WM-$_" }
    if ($report.schema -cne 'windows-acceptance/1' -or $report.platform -cne 'windows' -or
        @($checks | Where-Object { $report.checks.PSObject.Properties[$_].Value.status -cnotin $states }).Count -ne 0) {
        throw '原始 Windows 验收报告无效。'
    }
    $rawHash = Get-Sha256 $rawPath
    if ($manual.schema -cne 'windows-manual-review/1' -or $manual.acceptanceSha256 -ne $rawHash -or
        $manual.reviewedBy -isnot [string] -or [string]::IsNullOrWhiteSpace($manual.reviewedBy)) {
        throw '人工复核的格式、复核人或同次 acceptance.json 哈希无效。'
    }
    $review = [ordered]@{
        reviewedBy = $manual.reviewedBy
        acceptanceSha256 = $rawHash
        source = [ordered]@{
            path = 'manual-review.json'
            bytes = $manualFile.Length
            sha256 = Get-Sha256 $manualPath
        }
    }

    $windowPath = Join-Path $root 'native-window.json'
    $exitPath = Join-Path $root 'native-exit.json'
    $windowPass = $false
    $exitPass = $false
    if ($report.noLaunch -eq $false -and $report.prerequisites.disposableProfileConfirmed -eq $true -and
        $report.checks.'WM-2'.evidence -eq $windowPath) {
        $window = Read-RunJson 'native-window.json'
        $windowPass = $window.schema -ceq 'windows-native-window/1' -and $window.scope.kind -ceq 'launch' -and
            $window.repoPath -eq $report.repoPath -and $window.window.title -ceq '投资逻辑哨兵' -and
            $window.window.nativeCaption -is [bool] -and $window.window.nativeCaption -and
            $window.window.pid -in $window.processes.pid
        if ($windowPass -and $report.desktop.status -ceq 'pass' -and $report.desktop.exitEvidence -eq $exitPath) {
            $exitEvidence = Read-RunJson 'native-exit.json'
            $exitPass = $exitEvidence.schema -ceq 'windows-native-exit/1' -and
                $exitEvidence.baselinePath -eq $windowPath -and $exitEvidence.observedCount -gt 0 -and
                $exitEvidence.allObservedExited -is [bool] -and $exitEvidence.allObservedExited -and
                @($exitEvidence.remaining).Count -eq 0
        }
    }

    $pictures = @('.png', '.jpg', '.jpeg')
    if ($null -ne $manual.layout) {
        $routes = @('today', 'holdings', 'trading', 'risk', 'scan', 'settings')
        $seen = @{}
        $pages = @(
            foreach ($page in $manual.layout.pages) {
                if ($page.route -cnotin $routes -or $seen.ContainsKey($page.route) -or $page.status -cnotin $states) {
                    throw '布局复核的路由或状态无效或重复。'
                }
                $seen[$page.route] = $true
                if ($page.status -ceq 'not_run') {
                    if ($null -ne $page.screenshot) { [void](Get-Artifact $page.screenshot $pictures) }
                    continue
                }
                [ordered]@{ route = $page.route; status = $page.status; screenshot = Get-Artifact $page.screenshot $pictures }
            }
        )
        $width = $manual.layout.viewportWidth
        $height = $manual.layout.viewportHeight
        $sizeRecorded = $null -ne $width -and $null -ne $height
        if (($null -ne $width -and ((-not (Test-Number $width)) -or $width -ne 1024)) -or
            ($null -ne $height -and ((-not (Test-Number $height)) -or $height -ne 700))) {
            throw '原生 WebView2 的复核尺寸必须为 1024×700。'
        }
        if (@($pages.screenshot.path | Sort-Object -Unique).Count -ne $pages.Count) { throw '六页需要分别截图。' }
        $status = Get-ReviewStatus $routes.Count @($pages.status)
        $review.layout = [ordered]@{ pages = $pages; viewportWidth = $width; viewportHeight = $height }
        Set-ReviewedCheck 'WM-2' $status ($windowPass -and $sizeRecorded)
    }

    if ($null -ne $manual.stories) {
        $storyIds = 1..15 | ForEach-Object { 'US-{0:D2}' -f $_ }
        $seen = @{}
        $intervals = @{}
        $duration = $manual.stories.durationSeconds
        $recording = if ($null -ne $manual.stories.recording) { Get-Artifact $manual.stories.recording @('.mp4', '.webm') }
        if ($null -ne $duration -and (-not (Test-Number $duration) -or $duration -le 0)) { throw '录屏时长无效。' }
        $stories = @(
            foreach ($story in $manual.stories.items) {
                if ($story.id -cnotin $storyIds -or $seen.ContainsKey($story.id) -or $story.status -cnotin $states) {
                    throw '用户故事的编号或状态无效或重复。'
                }
                $seen[$story.id] = $true
                if ($story.status -ceq 'not_run') { continue }
                $start = $story.startSeconds
                $end = $story.endSeconds
                if (-not (Test-Number $start) -or -not (Test-Number $end) -or $start -lt 0 -or $end -le $start -or
                    ($null -ne $duration -and $end -gt $duration)) {
                    throw "用户故事录屏区间无效：$($story.id)。"
                }
                $interval = "$start/$end"
                if ($intervals.ContainsKey($interval)) { throw "用户故事录屏区间重复：$($story.id)。" }
                $intervals[$interval] = $true
                [ordered]@{ id = $story.id; status = $story.status; startSeconds = $start; endSeconds = $end }
            }
        )
        $status = Get-ReviewStatus $storyIds.Count @($stories.status)
        $review.stories = [ordered]@{ recording = $recording; durationSeconds = $duration; items = $stories }
        Set-ReviewedCheck 'WM-3' $status ($exitPass -and $null -ne $recording -and $null -ne $duration -and
            $report.realBridge.status -ceq 'pass' -and $report.integration.status -ceq 'pass')
    }

    if ($null -ne $manual.credentials) {
        $credentials = $manual.credentials
        $captures = [ordered]@{}
        foreach ($phase in 'before', 'saved', 'deleted') {
            if ($null -ne $credentials.$phase) { $captures[$phase] = Get-Artifact $credentials.$phase $pictures }
        }
        if (@($captures.Values | ForEach-Object { $_.path } | Sort-Object -Unique).Count -ne $captures.Count -or
            ($null -ne $credentials.status -and $credentials.status -cnotin $states) -or
            ($null -ne $credentials.leakCheck -and $credentials.leakCheck -isnot [bool])) {
            throw '凭据复核需要独立截图、合法状态和布尔型泄漏检查结果。'
        }
        $probe = $report.credentials.probe
        $probePass = $report.credentials.status -ceq 'pass' -and $probe.status -ceq 'pass' -and
            $probe.result.backend -ceq 'Windows Credential Locker' -and
            @($probe.result.write_ok, $probe.result.read_ok, $probe.result.delete_ok | Where-Object {
                $_ -isnot [bool] -or -not $_
            }).Count -eq 0
        $review.credentials = [ordered]@{ captures = $captures; status = $credentials.status; leakCheck = $credentials.leakCheck }
        $status = if (($credentials.status -ceq 'fail' -and $captures.Count -gt 0) -or
            ($credentials.leakCheck -is [bool] -and -not $credentials.leakCheck)) { 'fail' }
            elseif ($captures.Count -eq 3 -and $credentials.status -ceq 'pass' -and $credentials.leakCheck) { 'pass' }
            else { 'not_run' }
        Set-ReviewedCheck 'WM-4' $status ($windowPass -and $probePass)
    }

    $report | Add-Member -NotePropertyName manualReview -NotePropertyValue $review
    $outcomes = @($checks | ForEach-Object { $report.checks.PSObject.Properties[$_].Value }) +
        @($report.bridge, $report.realBridge, $report.integration, $report.demo, $report.browser, $report.credentials, $report.desktop)
    if ($report.exitCode -ne 2) {
        $report.exitCode = if ($outcomes.status -ccontains 'fail') { 1 }
            elseif (@($outcomes | Where-Object { $_.status -cne 'pass' }).Count -gt 0) { 3 }
            else { 0 }
    }
    $report.overall = if ($report.exitCode -eq 0) { 'pass' } else { 'fail' }
    $target = Join-Path $root 'reviewed-acceptance.json'
    if (Test-Path -LiteralPath $target) {
        $existing = Get-Item -LiteralPath $target -Force
        if ($existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw '复核报告的目标必须是普通文件。'
        }
    }
    $temporary = Join-Path $root ('.review-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($temporary, ($report | ConvertTo-Json -Depth 14) + [Environment]::NewLine,
            [Text.UTF8Encoding]::new($false))
        if ([IO.File]::Exists($target)) { [IO.File]::Replace($temporary, $target, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $target) }
    }
    finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
    Write-Output "Reviewed report: $target"
    exit $report.exitCode
}
catch {
    Write-Output "Windows evidence review error: $($_.Exception.Message)"
    exit 2
}

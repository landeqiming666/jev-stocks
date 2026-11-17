<#
.SYNOPSIS
记录指定 Sentinel 桌面进程或启动进程的本机窗口和进程树。
.DESCRIPTION
窗口和退出记录分别写入 native-window.json 和 native-exit.json。退出检查使用
窗口记录中已经观察到的 PID 与进程启动时间。WindowCloseTimeoutSeconds 大于零时，
持续记录本次启动树的后续进程，检测到原生窗口销毁后开始退出核验。ScreenshotPath 可登记已采集的截图。
.EXAMPLE
.\collect-evidence.ps1 -LaunchPid $launch.Id -ReportDir $runDir -WaitSeconds 180
.EXAMPLE
.\collect-evidence.ps1 -BaselinePath "$runDir\native-window.json" -ReportDir $runDir -WaitSeconds 5
.EXAMPLE
.\collect-evidence.ps1 -BaselinePath "$runDir\native-window.json" -ReportDir $runDir -WaitSeconds 5 -WindowCloseTimeoutSeconds 900
.EXAMPLE
.\collect-evidence.ps1 -CleanupPath "$runDir\native-window.json" -ReportDir $runDir -WaitSeconds 5
.EXAMPLE
.\collect-evidence.ps1 -CleanupPath "$runDir\native-window-error.json" -ReportDir $runDir -WaitSeconds 5
#>
[CmdletBinding(DefaultParameterSetName = 'Launch')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Launch')]
    [ValidateRange(1, 2147483647)][int]$LaunchPid,

    [Parameter(Mandatory, ParameterSetName = 'Desktop')]
    [ValidateRange(1, 2147483647)][int]$DesktopPid,

    [Parameter(Mandatory, ParameterSetName = 'Exit')]
    [string]$BaselinePath,

    [Parameter(Mandatory, ParameterSetName = 'Cleanup')]
    [string]$CleanupPath,

    [Parameter(Mandatory)]
    [string]$ReportDir,

    [ValidateRange(0, 180)][int]$WaitSeconds = 0,

    [Parameter(ParameterSetName = 'Exit')]
    [ValidateRange(0, 86400)][int]$WindowCloseTimeoutSeconds = 0,

    [Parameter(ParameterSetName = 'Launch')]
    [Parameter(ParameterSetName = 'Desktop')]
    [string[]]$ScreenshotPath = @()
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw '窗口证据收集需要 Windows。' }

$reportRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ReportDir)
[IO.Directory]::CreateDirectory($reportRoot) | Out-Null

function Write-NativeEvidence {
    param([string]$Name, [System.Collections.IDictionary]$Data)

    $target = Join-Path $reportRoot $Name
    $Data['evidencePath'] = $target
    $temporary = Join-Path $reportRoot ('.native-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $json = ConvertTo-Json -InputObject $Data -Depth 8
        [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        if ([IO.File]::Exists($target)) { [IO.File]::Replace($temporary, $target, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $target) }
    }
    finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
    return [pscustomobject]$Data
}

function Get-NativeProcessTree {
    param([hashtable]$Seeds, [datetime]$SampledAtUtc)

    $parents = [Sentinel.Acceptance.NativeEvidence]::Parents()
    $tree = @{}
    $queue = [Collections.Generic.Queue[int]]::new()
    foreach ($seed in $Seeds.Values) {
        $tree[$seed.Pid] = [pscustomobject]@{ identity = $seed; parentPid = $null }
        $queue.Enqueue($seed.Pid)
    }
    $children = @{}
    foreach ($pair in $parents.GetEnumerator()) {
        if (-not $children.ContainsKey($pair.Value)) {
            $children[$pair.Value] = [Collections.Generic.List[int]]::new()
        }
        $children[$pair.Value].Add($pair.Key)
    }
    while ($queue.Count -gt 0) {
        $parentId = $queue.Dequeue()
        foreach ($childId in $children[$parentId]) {
            if ($childId -le 0 -or $tree.ContainsKey($childId)) { continue }
            $child = [Sentinel.Acceptance.NativeEvidence]::ReadIdentity($childId)
            # A PID created after this sample could belong to a replacement process.
            if ($child -and $child.StartedAtUtc -le $SampledAtUtc -and
                $child.StartedAtUtc -ge $tree[$parentId].identity.StartedAtUtc) {
                $tree[$childId] = [pscustomobject]@{ identity = $child; parentPid = $parentId }
                $queue.Enqueue($childId)
            }
        }
    }
    return $tree
}

function Read-NativeCleanupIdentity {
    param($Entry)

    $processId = 0
    $started = [DateTimeOffset]::MinValue
    if ($Entry.startedAtUtc -is [datetime] -or $Entry.startedAtUtc -is [DateTimeOffset]) {
        $started = [DateTimeOffset]$Entry.startedAtUtc
    }
    elseif (-not [DateTimeOffset]::TryParse([string]$Entry.startedAtUtc, [ref]$started)) {
        throw '清理基线包含无效的启动时间。'
    }
    if (-not [int]::TryParse([string]$Entry.pid, [ref]$processId) -or $processId -le 0 -or
        [string]::IsNullOrWhiteSpace([string]$Entry.name)) {
        throw '清理基线包含无效的进程身份。'
    }
    [pscustomobject]@{
        pid = $processId; name = [string]$Entry.name
        startedAtUtc = $started.UtcDateTime; parentPid = $Entry.parentPid
    }
}

function Add-NativeCleanupChildren {
    param([hashtable]$Records, [object[]]$Entries)

    $pending = [Collections.Generic.List[object]]::new()
    foreach ($entry in $Entries) { $pending.Add((Read-NativeCleanupIdentity $entry)) }
    do {
        $added = $false
        foreach ($entry in @($pending.ToArray())) {
            $key = "$($entry.pid):$($entry.startedAtUtc.Ticks)"
            $parent = @($Records.Values | Where-Object {
                $_.pid -eq $entry.parentPid -and $_.startedAtUtc -le $entry.startedAtUtc
            })
            if ($Records.ContainsKey($key) -or $parent.Count -gt 0) {
                $Records[$key] = $entry
                [void]$pending.Remove($entry)
                $added = $true
            }
        }
    } while ($added -and $pending.Count -gt 0)
    if ($pending.Count -gt 0) { throw '清理身份包含不属于本次启动树的进程。' }
}

$mode = $PSCmdlet.ParameterSetName
$lateObserved = @{}
$windowClosedAtUtc = $null
$desktopClosedAtUtc = $null
$scopeEvidence = $null
$observed = @{}
try {
    if (-not ('Sentinel.Acceptance.NativeEvidence' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace Sentinel.Acceptance {
    public static class NativeEvidence {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct ProcessEntry {
            public uint Size, Usage, Id;
            public UIntPtr Heap;
            public uint Module, Threads, ParentId;
            public int Priority;
            public uint Flags;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
            public string Image;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct Rect {
            public int Left, Top, Right, Bottom;
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint id);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
        private static extern bool Process32FirstW(IntPtr snapshot, ref ProcessEntry entry);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
        private static extern bool Process32NextW(IntPtr snapshot, ref ProcessEntry entry);
        [DllImport("kernel32.dll")]
        private static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenProcess(uint access, bool inherit, int id);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool GetProcessTimes(IntPtr process, out long created, out long exited,
            out long kernel, out long user);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool TerminateProcess(IntPtr process, uint code);
        [DllImport("kernel32.dll")]
        private static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr window, out uint id);
        [DllImport("user32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
        private static extern int GetWindowTextW(IntPtr window, StringBuilder text, int capacity);
        [DllImport("user32.dll")]
        private static extern int GetWindowLongW(IntPtr window, int index);
        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool GetClientRect(IntPtr window, out Rect rect);

        public sealed class Identity {
            public int Pid { get; set; }
            public string Name { get; set; }
            public DateTime StartedAtUtc { get; set; }
        }

        public sealed class Window {
            public int Pid { get; set; }
            public string Hwnd { get; set; }
            public uint ThreadId { get; set; }
            public string ExecutablePath { get; set; }
            public string Title { get; set; }
            public bool NativeCaption { get; set; }
            public int ClientWidth { get; set; }
            public int ClientHeight { get; set; }
        }

        public static Dictionary<int, int> Parents() {
            IntPtr snapshot = CreateToolhelp32Snapshot(2, 0);
            if (snapshot == new IntPtr(-1)) throw new Win32Exception();
            try {
                var result = new Dictionary<int, int>();
                var entry = new ProcessEntry { Size = (uint)Marshal.SizeOf(typeof(ProcessEntry)) };
                if (!Process32FirstW(snapshot, ref entry)) throw new Win32Exception();
                do {
                    result[(int)entry.Id] = (int)entry.ParentId;
                } while (Process32NextW(snapshot, ref entry));
                // ERROR_NO_MORE_FILES is the normal end of the snapshot.
                if (Marshal.GetLastWin32Error() != 18) throw new Win32Exception();
                return result;
            } finally { CloseHandle(snapshot); }
        }

        public static Identity ReadIdentity(int id) {
            try {
                using (Process p = Process.GetProcessById(id)) {
                    DateTime start = p.StartTime.ToUniversalTime();
                    if (p.HasExited) return null;
                    return new Identity { Pid = id, Name = p.ProcessName, StartedAtUtc = start };
                }
            } catch (ArgumentException) { return null; }
              catch (InvalidOperationException) { return null; }
        }

        public static Window ReadWindow(Identity identity) {
            try {
                using (Process p = Process.GetProcessById(identity.Pid)) {
                    if (p.StartTime.ToUniversalTime() != identity.StartedAtUtc) return null;
                    IntPtr hwnd = p.MainWindowHandle;
                    if (hwnd == IntPtr.Zero || !IsWindowVisible(hwnd)) return null;
                    uint windowPid;
                    uint threadId = GetWindowThreadProcessId(hwnd, out windowPid);
                    Rect rect;
                    if (threadId == 0 || windowPid != identity.Pid || !GetClientRect(hwnd, out rect)) return null;
                    var title = new StringBuilder(512);
                    GetWindowTextW(hwnd, title, title.Capacity);
                    return new Window {
                        Pid = identity.Pid, ExecutablePath = p.MainModule.FileName,
                        Hwnd = "0x" + hwnd.ToInt64().ToString("X"), ThreadId = threadId,
                        Title = title.ToString(), NativeCaption = (GetWindowLongW(hwnd, -16) & 0x00C00000) == 0x00C00000,
                        ClientWidth = rect.Right - rect.Left, ClientHeight = rect.Bottom - rect.Top
                    };
                }
            } catch (ArgumentException) { return null; }
              catch (InvalidOperationException) { return null; }
        }

        public static bool WindowMatches(long handle, int desktopPid, uint threadId) {
            uint owner;
            return GetWindowThreadProcessId(new IntPtr(handle), out owner) == threadId &&
                owner == desktopPid;
        }

        public static string TerminateExact(int id, DateTime startedAtUtc) {
            // Query and termination share the same handle, so PID reuse cannot redirect the kill.
            IntPtr process = OpenProcess(0x00100000 | 0x1000 | 0x0001, false, id);
            if (process == IntPtr.Zero) {
                int error = Marshal.GetLastWin32Error();
                return error == 87 ? "already_exited" : "error:" + error;
            }
            try {
                long created, exited, kernel, user;
                if (!GetProcessTimes(process, out created, out exited, out kernel, out user)) {
                    return "error:" + Marshal.GetLastWin32Error();
                }
                if (created != startedAtUtc.ToFileTimeUtc()) return "identity_mismatch";
                if (WaitForSingleObject(process, 0) == 0) return "already_exited";
                if (!TerminateProcess(process, 1)) {
                    return WaitForSingleObject(process, 0) == 0 ? "already_exited" :
                        "error:" + Marshal.GetLastWin32Error();
                }
                return "terminated";
            } finally { CloseHandle(process); }
        }
    }
}
'@
    }

    $timer = [Diagnostics.Stopwatch]::StartNew()
    if ($mode -eq 'Cleanup') {
        $cleanupBaseline = (Resolve-Path -LiteralPath $CleanupPath).Path
        $baseline = Get-Content -LiteralPath $cleanupBaseline -Raw -Encoding UTF8 | ConvertFrom-Json
        $hasWindowBaseline = $cleanupBaseline -eq (Join-Path $reportRoot 'native-window.json') -and
            $baseline.schema -ceq 'windows-native-window/1'
        $hasLaunchError = $cleanupBaseline -eq (Join-Path $reportRoot 'native-window-error.json') -and
            $baseline.schema -ceq 'windows-native-evidence-error/1' -and
            $baseline.mode -cin @('launch', 'desktop') -and $baseline.mode -ceq $baseline.scope.kind
        if ((-not $hasWindowBaseline -and -not $hasLaunchError) -or
            $baseline.scope.kind -cnotin @('launch', 'desktop')) {
            throw '清理需要有效的 Sentinel 原生窗口基线。'
        }
        $records = @{}
        $rootEntry = @($baseline.processes | Where-Object { $_.pid -eq $baseline.scope.pid })
        $desktopEntry = @($baseline.processes | Where-Object {
            $_.pid -eq $baseline.window.pid -and $_.name -ceq 'sentinel-desktop'
        })
        if ($rootEntry.Count -ne 1 -or ($hasWindowBaseline -and $desktopEntry.Count -ne 1) -or
            ($baseline.scope.kind -ceq 'desktop' -and $rootEntry[0].name -cne 'sentinel-desktop') -or
            ([datetimeoffset]$rootEntry[0].startedAtUtc).UtcDateTime -ne
                ([datetimeoffset]$baseline.scope.startedAtUtc).UtcDateTime) {
            throw '清理基线缺少匹配的启动进程或 Sentinel 进程。'
        }
        $rootRecord = Read-NativeCleanupIdentity $rootEntry[0]
        $records["$($rootRecord.pid):$($rootRecord.startedAtUtc.Ticks)"] = $rootRecord
        Add-NativeCleanupChildren $records @($baseline.processes)
        $supplements = if ($hasWindowBaseline) { @('native-exit.json', 'native-exit-error.json') } else { @() }
        foreach ($name in $supplements) {
            $source = Join-Path $reportRoot $name
            if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { continue }
            $extra = Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($extra.baselinePath -eq $cleanupBaseline -and
                ($extra.schema -ceq 'windows-native-exit/1' -or
                 ($extra.schema -ceq 'windows-native-evidence-error/1' -and $extra.mode -ceq 'exit'))) {
                Add-NativeCleanupChildren $records @($extra.lateObservedProcesses | Where-Object { $null -ne $_ })
            }
        }
        $actions = @{}
        do {
            $live = @{}
            foreach ($entry in $records.Values) {
                $identity = [Sentinel.Acceptance.NativeEvidence]::ReadIdentity($entry.pid)
                if ($identity -and $identity.StartedAtUtc -eq $entry.startedAtUtc -and
                    $identity.Name -ceq $entry.name) { $live[$identity.Pid] = $identity }
            }
            if ($live.Count -eq 0) { break }
            $tree = Get-NativeProcessTree $live ([datetime]::UtcNow)
            foreach ($member in $tree.Values) {
                $identity = $member.identity
                $key = "$($identity.Pid):$($identity.StartedAtUtc.Ticks)"
                if (-not $records.ContainsKey($key)) {
                    $records[$key] = [pscustomobject]@{
                        pid = $identity.Pid; name = $identity.Name
                        startedAtUtc = $identity.StartedAtUtc; parentPid = $member.parentPid
                    }
                }
                $actions[$key] = [pscustomobject]@{
                    pid = $identity.Pid; name = $identity.Name
                    startedAtUtc = $identity.StartedAtUtc.ToString('o')
                    result = [Sentinel.Acceptance.NativeEvidence]::TerminateExact($identity.Pid, $identity.StartedAtUtc)
                }
            }
            if ($timer.Elapsed.TotalSeconds -ge $WaitSeconds) { break }
            Start-Sleep -Milliseconds 100
        } while ($true)
        $remaining = @(
            foreach ($entry in $records.Values) {
                $identity = [Sentinel.Acceptance.NativeEvidence]::ReadIdentity($entry.pid)
                if ($identity -and $identity.StartedAtUtc -eq $entry.startedAtUtc) {
                    [pscustomobject]@{ pid = $identity.Pid; name = $identity.Name; startedAtUtc = $identity.StartedAtUtc.ToString('o') }
                }
            }
        )
        Write-NativeEvidence 'native-cleanup.json' ([ordered]@{
            schema = 'windows-native-cleanup/1'; capturedAtUtc = [datetime]::UtcNow.ToString('o')
            baselinePath = $cleanupBaseline
            status = if ($remaining.Count -eq 0) { 'pass' } else { 'fail' }
            allObservedExited = $remaining.Count -eq 0; observedCount = $records.Count
            actions = @($actions.Values | Sort-Object pid); remaining = $remaining
        })
        return
    }
    if ($mode -eq 'Exit') {
        $baseline = Get-Content -LiteralPath $BaselinePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($baseline.schema -ne 'windows-native-window/1' -or -not $baseline.window -or
            -not $baseline.processes -or $baseline.window.pid -notin $baseline.processes.pid) {
            throw '退出核验需要有效的 native-window.json 基线。'
        }
        $identities = @{}
        foreach ($entry in $baseline.processes) {
            $processId = [int]$entry.pid
            if ($processId -le 0 -or $identities.ContainsKey($processId) -or -not $entry.startedAtUtc) {
                throw '进程基线包含缺失或重复的身份。'
            }
            $identities[$processId] = ([datetimeoffset]$entry.startedAtUtc).UtcDateTime
        }
        $baselineCount = $identities.Count
        $desktopId = [int]$baseline.window.pid
        $desktopStartedAtUtc = $identities[$desktopId]
        $watchWindow = $WindowCloseTimeoutSeconds -gt 0
        if ($watchWindow) {
            $threadId = [uint32]0
            $windowProperties = $baseline.window.PSObject.Properties
            if ($null -eq $windowProperties['hwnd'] -or $null -eq $windowProperties['threadId'] -or
                $baseline.window.hwnd -cnotmatch '\A0x[0-9A-Fa-f]{1,16}\z' -or
                -not [uint32]::TryParse([string]$baseline.window.threadId, [ref]$threadId) -or $threadId -eq 0) {
                throw '窗口关闭监控需要包含有效 HWND 和窗口线程的 native-window.json 基线。'
            }
            $windowHandle = [Convert]::ToInt64($baseline.window.hwnd, 16)
            if ($windowHandle -eq 0) { throw '窗口基线包含无效 HWND。' }
        }
        do {
            $sampledAtUtc = [datetime]::UtcNow
            $live = @{}
            foreach ($processId in @($identities.Keys)) {
                $identity = [Sentinel.Acceptance.NativeEvidence]::ReadIdentity($processId)
                if ($identity -and $identity.StartedAtUtc -eq $identities[$processId]) {
                    $live[$processId] = $identity
                }
                else { $identities.Remove($processId) }
            }
            if ($watchWindow) {
                $desktopAlive = $live.ContainsKey($desktopId) -and
                    $live[$desktopId].StartedAtUtc -eq $desktopStartedAtUtc
                if (-not $windowClosedAtUtc -and (-not $desktopAlive -or
                    -not [Sentinel.Acceptance.NativeEvidence]::WindowMatches($windowHandle, $desktopId, $threadId))) {
                    $windowClosedAtUtc = [datetime]::UtcNow.ToString('o')
                    $timer.Restart()
                }
                if (-not $desktopClosedAtUtc -and -not $desktopAlive) {
                    $desktopClosedAtUtc = [datetime]::UtcNow.ToString('o')
                }
            }
            if ($watchWindow -and $live.Count -gt 0) {
                # Keep already verified descendants as anchors if their parent has exited.
                $tree = Get-NativeProcessTree $live $sampledAtUtc
                foreach ($member in $tree.Values) {
                    $child = $member.identity
                    if ($live.ContainsKey($child.Pid)) { continue }
                    $live[$child.Pid] = $child
                    $identities[$child.Pid] = $child.StartedAtUtc
                    $lateObserved["$($child.Pid):$($child.StartedAtUtc.Ticks)"] = [pscustomobject]@{
                        pid = $child.Pid; parentPid = $member.parentPid; name = $child.Name
                        startedAtUtc = $child.StartedAtUtc.ToString('o')
                    }
                }
            }
            if ($watchWindow -and -not $windowClosedAtUtc) {
                if ($timer.Elapsed.TotalSeconds -ge $WindowCloseTimeoutSeconds) {
                    throw "在 $WindowCloseTimeoutSeconds 秒内未检测到桌面进程 $desktopId 的原生窗口销毁。"
                }
            }
            elseif ($live.Count -eq 0 -or $timer.Elapsed.TotalSeconds -ge $WaitSeconds) { break }
            Start-Sleep -Milliseconds 150
        } while ($true)
        $remaining = @(
            foreach ($identity in $live.Values) {
                [pscustomobject]@{
                    pid = $identity.Pid; name = $identity.Name
                    startedAtUtc = $identity.StartedAtUtc.ToString('o')
                }
            }
        )
        Write-NativeEvidence 'native-exit.json' ([ordered]@{
            schema = 'windows-native-exit/1'
            capturedAtUtc = [datetime]::UtcNow.ToString('o')
            baselinePath = (Resolve-Path -LiteralPath $BaselinePath).Path
            observedCount = $baselineCount + $lateObserved.Count
            windowClosedAtUtc = $windowClosedAtUtc
            desktopClosedAtUtc = $desktopClosedAtUtc
            lateObservedProcesses = @($lateObserved.Values | Sort-Object pid, startedAtUtc)
            allObservedExited = $remaining.Count -eq 0
            remaining = @($remaining | Sort-Object pid)
        })
        return
    }

    $rootId = if ($mode -eq 'Launch') { $LaunchPid } else { $DesktopPid }
    $root = [Sentinel.Acceptance.NativeEvidence]::ReadIdentity($rootId)
    if (-not $root) { throw "指定进程 $rootId 已退出或不存在。" }
    if ($mode -eq 'Desktop' -and $root.Name -ne 'sentinel-desktop') {
        throw "指定桌面 PID $rootId 对应的进程不是 Sentinel。"
    }

    $scopeEvidence = [ordered]@{
        kind = $mode.ToLowerInvariant(); pid = $rootId
        startedAtUtc = $root.StartedAtUtc.ToString('o')
    }
    $observed[$rootId] = [pscustomobject]@{
        pid = $rootId; parentPid = $null; name = $root.Name
        startedAtUtc = $root.StartedAtUtc.ToString('o')
    }
    $window = $null
    do {
        $sampledAtUtc = [datetime]::UtcNow
        $identity = [Sentinel.Acceptance.NativeEvidence]::ReadIdentity($rootId)
        if (-not $identity -or $identity.StartedAtUtc -ne $root.StartedAtUtc) {
            throw "指定进程 $rootId 在窗口就绪前退出。"
        }
        $tree = Get-NativeProcessTree @{ $rootId = $root } $sampledAtUtc

        foreach ($member in $tree.Values) {
            $observed[$member.identity.Pid] = [pscustomobject]@{
                pid = $member.identity.Pid
                parentPid = $member.parentPid
                name = $member.identity.Name
                startedAtUtc = $member.identity.StartedAtUtc.ToString('o')
            }
        }
        $candidates = $tree.Values.identity | Where-Object {
            $_.Name -eq 'sentinel-desktop' -and ($mode -eq 'Launch' -or $_.Pid -eq $rootId)
        } | Sort-Object StartedAtUtc
        foreach ($candidate in $candidates) {
            $window = [Sentinel.Acceptance.NativeEvidence]::ReadWindow($candidate)
            if ($window) { break }
        }
        if ($window -or $timer.Elapsed.TotalSeconds -ge $WaitSeconds) { break }
        Start-Sleep -Milliseconds 250
    } while ($true)
    if (-not $window) { throw "在 $WaitSeconds 秒内未发现指定进程范围的 Sentinel 可见窗口。" }

    $screenshots = @(
        foreach ($path in $ScreenshotPath) {
            $file = Get-Item -LiteralPath $path
            if ($file.PSIsContainer -or $file.Extension -notin @('.png', '.jpg', '.jpeg')) {
                throw "截图证据必须是 PNG 或 JPEG 文件：$path"
            }
            [pscustomobject]@{
                path = $file.FullName; bytes = $file.Length
                sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    )
    Write-NativeEvidence 'native-window.json' ([ordered]@{
        schema = 'windows-native-window/1'
        capturedAtUtc = [datetime]::UtcNow.ToString('o')
        elapsedSeconds = [Math]::Round($timer.Elapsed.TotalSeconds, 3)
        repoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../..')).Path
        osVersion = [Environment]::OSVersion.Version.ToString()
        architecture = [string][Runtime.InteropServices.RuntimeInformation]::OSArchitecture
        powerShellVersion = $PSVersionTable.PSVersion.ToString()
        scope = $scopeEvidence
        window = [ordered]@{
            pid = $window.Pid; hwnd = $window.Hwnd; threadId = $window.ThreadId
            executablePath = $window.ExecutablePath; title = $window.Title
            executableVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($window.ExecutablePath).FileVersion
            nativeCaption = $window.NativeCaption
            clientWidth = $window.ClientWidth; clientHeight = $window.ClientHeight
        }
        processes = @($observed.Values | Sort-Object pid)
        screenshots = $screenshots
    })
}
catch {
    $failure = $_
    $errorFile = if ($mode -eq 'Exit') { 'native-exit-error.json' }
        elseif ($mode -eq 'Cleanup') { 'native-cleanup-error.json' }
        else { 'native-window-error.json' }
    $errorEvidence = [ordered]@{
        schema = 'windows-native-evidence-error/1'
        capturedAtUtc = [datetime]::UtcNow.ToString('o')
        mode = $mode.ToLowerInvariant()
        message = $failure.Exception.Message
    }
    if ($WindowCloseTimeoutSeconds -gt 0) {
        $errorEvidence['windowCloseTimeoutSeconds'] = $WindowCloseTimeoutSeconds
        $errorEvidence['windowClosedAtUtc'] = $windowClosedAtUtc
        $errorEvidence['desktopClosedAtUtc'] = $desktopClosedAtUtc
        $errorEvidence['lateObservedProcesses'] = @($lateObserved.Values | Sort-Object pid, startedAtUtc)
    }
    if ($mode -eq 'Exit') {
        $errorEvidence['baselinePath'] = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($BaselinePath)
    }
    if ($mode -in @('Launch', 'Desktop')) {
        $errorEvidence['scope'] = $scopeEvidence
        $errorEvidence['processes'] = @($observed.Values | Sort-Object pid)
    }
    Write-NativeEvidence $errorFile $errorEvidence | Out-Null
    throw $failure
}

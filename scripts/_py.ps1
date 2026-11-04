$ErrorActionPreference = "Stop"
# 由同目录的 PowerShell 包装器点入。

function Get-SentinelPython {
    $PSNativeCommandUseErrorActionPreference = $false
    $versionProbe = 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'
    foreach ($name in @('py.exe', 'python.exe', 'python3.exe')) {
        $prefix = @()
        if ($name -eq 'py.exe') {
            $prefix = @('-3')
        }
        foreach ($command in Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue) {
            # Skip app execution aliases that can open the Microsoft Store.
            if ($command.Path -like '*\Microsoft\WindowsApps\*') {
                continue
            }
            try {
                & $command.Path @prefix -c $versionProbe 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    return @($command.Path) + $prefix
                }
            }
            catch {
                continue
            }
        }
    }
    throw "找不到 Python >= 3.9。请安装 Python 并确保 py 或 python 在 PATH 中。"
}

function Invoke-SentinelPython {
    param(
        [string]$Script,
        [string[]]$Arguments = @()
    )

    $PSNativeCommandUseErrorActionPreference = $false
    $python = @(Get-SentinelPython)
    $target = Join-Path $PSScriptRoot $Script
    $prefix = @($python | Select-Object -Skip 1)
    $nativeArguments = @($target) + $Arguments
    if ($PSVersionTable.PSVersion -ge [version]'7.3') {
        $PSNativeCommandArgumentPassing = 'Standard'
    }
    else {
        # Legacy binding passes prequoted strings through. Double embedded
        # quotes and the backslashes before them or before the closing quote.
        $nativeArguments = @(
            foreach ($argument in $nativeArguments) {
                '"' + ($argument -creplace '(\\*)"', '$1$1""' -creplace '(\\+)\z', '$1$1') + '"'
            }
        )
    }
    & $python[0] @prefix @nativeArguments
    exit $LASTEXITCODE
}

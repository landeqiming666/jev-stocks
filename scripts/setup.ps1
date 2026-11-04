$ErrorActionPreference = "Stop"
# 从仓库根目录运行 .\scripts\setup.ps1 并附上所需参数。
# RemoteSigned 下可直接运行本地脚本。若被拦截，用 Get-ExecutionPolicy -List 查看策略。
# 也可通过 python .\scripts\setup.py 调用同一入口。
. "$PSScriptRoot\_py.ps1"
Invoke-SentinelPython -Script "setup.py" -Arguments $args

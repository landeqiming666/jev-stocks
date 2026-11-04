# Windows 预检与原生验收

在 Windows 11 x64 上，从含中文和空格的仓库路径运行。默认使用离线依赖缓存。

```powershell
scripts\windows_smoke.ps1 -NoLaunch
scripts\windows_smoke.ps1 -NoLaunch -SkipInstall
scripts\windows_smoke.ps1 -NoLaunch -SelfTest
```

只有已经按锁文件安装依赖时才使用 `-SkipInstall`。如果需要复用已有工具环境，先加载本机的开发环境脚本，再运行预检。独立工作树应使用自己的 Cargo 产物目录，避免正在使用的可执行文件阻塞构建。

预检记录 `doctor.ps1`、`setup.ps1`、`check.ps1`、桥接、WinVault 和 Edge 测试。工程门禁与离线集成测试分开执行。E-01 加载器可用时，预检在 `demo-cli/` 加载演示数据并核对六项计数。W-02 真实核心测试和 I-01 离线联调需要各自的入口和专用 Windows 测试账户。桥接必须执行指定用例，I-01 会保存 JUnit 报告及通过、失败和跳过数。WinVault 自动探针使用隔离的临时凭据。

报告写入 `results/acceptance.json`。每次运行的原始报告和日志保留在独立子目录。可用 `-ReportDir` 指定其他本地目录。报告记录实际运行的提交、五项 Windows 验收状态和依赖缺口。

| 退出码 | 结果 |
|---|---|
| 0 | 验收项全部通过 |
| 1 | 已执行的检查有失败 |
| 2 | 前置环境或离线安装未通过 |
| 3 | 已执行的检查通过，仍有待验收项 |

## 原生 WebView2 验收

在禁用联网、没有 Sentinel 凭据的专用 Windows 测试账户中运行。接入 C-07、E-01、I-01 和六个业务页后，脚本会先执行自动检查，再启动原生窗口。

```powershell
$env:SENTINEL_WINDOWS_DISPOSABLE_PROFILE = '1'
scripts\windows_smoke.ps1 -SkipInstall -WindowCloseTimeoutSeconds 900
```

原生应用从独立的空 `desktop-data/` 启动。脚本打印本次证据目录和窗口 PID，并保存 `native-window.json`。完成[实机联调清单](manual-checklist.md)后关闭窗口。脚本在检测到原生窗口销毁时开始五秒计时，检查本次已观察到的进程是否退出，并在 `native-exit.json` 中分别记录窗口关闭时间和桌面进程退出时间。六页截图、业务录屏和凭据管理器人工检查由验收人员采集。W-03 产物存在时，预检核对报告与扩展哈希，并记录实际构建或降级结果。Windows 最终 JEVDB 门槛由 ADR 确认。

## 复核本次证据

关窗并生成 `acceptance.json` 后，把证据文件和 `manual-review.json` 放到脚本打印的单次验收目录。用 `Get-FileHash <验收目录>\acceptance.json -Algorithm SHA256` 获取原始报告哈希。以下是记录格式，示例各列一条布局和业务结果。

```json
{
  "schema": "windows-manual-review/1",
  "acceptanceSha256": "原始报告的 SHA-256",
  "reviewedBy": "验收人员",
  "layout": {
    "viewportWidth": 1024,
    "viewportHeight": 700,
    "pages": [{ "route": "today", "status": "pass", "screenshot": "screenshots/today.png" }]
  },
  "stories": {
    "recording": "session.mp4",
    "durationSeconds": 900,
    "items": [{ "id": "US-01", "status": "pass", "startSeconds": 12, "endSeconds": 29 }]
  },
  "credentials": {
    "before": "screenshots/vault-before.png",
    "saved": "screenshots/vault-saved.png",
    "deleted": "screenshots/vault-deleted.png",
    "status": "pass",
    "leakCheck": true
  }
}
```

布局通过需要六条路由记录。业务通过需要 US-01 至 US-15 的录屏区间。凭据通过需要保存前、保存后、删除后的三张截图，并确认本次测试凭据未出现在日志、数据库或错误信息中。路径相对于同次验收目录。按观察填写 `pass`、`fail` 或 `not_run`。

```powershell
apps\desktop\e2e\windows\complete-review.ps1 -RunDir $runDir
```

复核命令生成 `reviewed-acceptance.json` 并登记原始报告和证据的哈希，原始报告单独保留。WM-5 继续采用原始报告的结论。复核输入无效时退出 2。

## Edge 应用外壳预检

复用本机 Microsoft Edge 和项目已安装的 Playwright。Vite 只监听 `127.0.0.1:1476`，由 Playwright 在测试结束后关闭。

```powershell
pnpm --dir apps/desktop exec playwright test --config e2e/windows/playwright.config.ts
```

在 1440×900 和 1024×700 下检查六个导航路由、Windows 样式变量和横向溢出，保存每个路由的截图与 trace。路由证据逐项记录业务占位提示是否可见。另验证浏览器离线提示、恢复联网，以及 U-08 错误边界触发后导航仍能使用。

独立运行的截图与 trace 位于 `results/playwright/`。由 `windows_smoke.ps1` 运行时，证据写入对应验收子目录的 `playwright/`。

# Windows 无窗口预检

在 Windows 11 x64 上，从含中文和空格的仓库路径运行。默认使用离线依赖缓存。

```powershell
scripts\windows_smoke.ps1 -NoLaunch
scripts\windows_smoke.ps1 -NoLaunch -SkipInstall
scripts\windows_smoke.ps1 -NoLaunch -SelfTest
```

只有已经按锁文件安装依赖时才使用 `-SkipInstall`。如果需要复用已有工具环境，先加载本机的开发环境脚本，再运行预检。独立工作树应使用自己的 Cargo 产物目录，避免正在使用的可执行文件阻塞构建。

预检记录 `doctor.ps1`、`setup.ps1`、`check.ps1` 和当前工作树已具备的桥接与 WinVault 测试。仅在 I-01、C-07 和 E-01 入口均存在时尝试离线核心联调。WinVault 自动探针使用隔离的临时凭据。

报告写入 `results/acceptance.json`。每次运行的原始报告和日志保留在独立子目录。可用 `-ReportDir` 指定其他本地目录。报告记录实际运行的提交、五项 Windows 验收状态和依赖缺口。

| 退出码 | 结果 |
|---|---|
| 1 | 已执行的检查有失败 |
| 2 | 前置环境或离线安装未通过 |
| 3 | 已执行的检查通过，仍有待验收项 |

原生 WebView2 窗口、六页截图和用户故事录屏在交互式验收时采集。凭据管理器人工检查和 Windows 最终 JEVDB 门槛也需单独完成。W-03 产物存在时，预检核对报告与扩展哈希并记录实际构建或降级结果。

## Edge 应用外壳预检

复用本机 Microsoft Edge 和项目已安装的 Playwright。Vite 只监听 `127.0.0.1:1476`，由 Playwright 在测试结束后关闭。

```powershell
pnpm --dir apps/desktop exec playwright test --config e2e/windows/playwright.config.ts
```

在 1440×900 和 1024×700 下检查六个导航路由、Windows 样式变量和横向溢出，保存每个路由的截图与 trace。路由证据逐项记录业务占位提示是否可见。另验证浏览器离线提示、恢复联网，以及 U-08 错误边界触发后导航仍能使用。

截图与 trace 位于 `results/playwright/`。原生 WebView2 和业务流程按[实机联调记录](manual-checklist.md)验收。

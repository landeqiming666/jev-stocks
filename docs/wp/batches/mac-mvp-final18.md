# Mac MVP 最后一批：业务闭环与验收

- 用户授权：2026-11-03 继续完成剩余 Mac MVP。
- 基线：`codex/mac-mvp-next10 @ 7c80aee`；分支 `codex/mac-mvp-final18`。
- worker：`agentrouter/gpt-6.1-sol/high`，独立 worktree，只本地提交；主审逐包复验后推送。
- 不自动合并 main；真实模型与 SEC 未配置不能记作通过。批准澄清见 F18-01。
- 主审：2026-11-04 独立复核全部实现、补 C-07/I-01/I-02、修正 E-01 演示账本并统一发布。

| 包 | 状态 | 主审与发布证据 |
|---|---|---|
| S-04 | 已发布 | wp/S-04 @ 4f1026a6fc81；原生本地 141；16/0/1；真实语义等价 NOT_RUN |
| S-05 | 已发布 | wp/S-05 @ 6faed7837061；专项 91；16/0/1 |
| P-02 | 已发布 | wp/P-02 @ 9311294d641f；扫描 227 定向；16/0/1 |
| P-03 | 已发布 | wp/P-03 @ 7e9bc90a1768；清单/持仓组合 366；核心 2579；16/0/1 |
| P-05 | 已发布 | wp/P-05 @ b2b501795629；公共备份互斥；16/0/1 |
| P-06 | 已发布 | wp/P-06 @ a9f1062ef35e；数值/服务 78；16/0/1 |
| U-02 | 已发布 | wp/U-02 @ 8face73ef…；今日页 48 定向；16/0/1 |
| U-03 | 已发布 | wp/U-03 @ 30949f6…；持仓页测试通过；16/0/1 |
| U-04 | 已发布 | wp/U-04 @ 27c9ce6…；扫描页测试通过；16/0/1 |
| U-05 | 已发布 | wp/U-05 @ 79dd89e55c28；交易页 46 单测 + 3 浏览器；16/0/1 |
| U-06 | 已发布 | wp/U-06 @ 608403d…；风险页测试通过；16/0/1 |
| U-07 | 已发布 | wp/U-07 @ 98cd6f3…；设置页测试通过；16/0/1 |
| U-08 | 已发布 | wp/U-08 @ 5447acd0493c；54 定向、5 浏览器；16/0/1 |
| E-01 | 已发布 | wp/E-01 @ 191749ca94bb；定向 14；联调修正演示账本（refId/日期/fee 行） |
| E-02 | 已发布 | wp/E-02 @ ea793d6…；92 定向；synthetic 回放 30 样本、F1 0.80；真实标注 NOT_RUN |
| C-07 | 已发布 | wp/C-07 @ 95461d186d47；20 单测；真实进程冒烟；16/0/1 |
| I-01 | 已发布 | wp/I-01 @ 051b4bc81ee2；集成 20 passed/1 skipped；真实核心 e2e 10 passed |
| I-02 | 已发布，复审修复已推送 | wp/I-02 @ 73156a67e7d4；2026-11-05 修复后整条离线 7/8（M-1～M-7 pass、M-8 not_run），真实 M-8 BLOCKED，人工 0/6；详见状态文件 |

## 验收结论

- 全量门禁：`scripts/check.sh --e2e` **17 通过 / 0 失败 / 0 跳过**（e2e 10 个真实核心用例）。
- 真实进程联调：`core/tests/integration` 20 passed、1 skipped；`pnpm e2e` 10 passed。
- 验收脚本：2026-11-05 最终源码整条复跑 M-1～M-7 pass、M-8 not_run（7/8），报告在 `.dev-data/validation/manual-acceptance-20261105/round4/`；9 个证据引用全部可解析。真实 M-8 因缺 `SENTINEL_JEVDB_PATH`、`JEV_API_KEY`、`SENTINEL_SEC_CONTACT` 且未授权模型费用而 BLOCKED；六项人工验收 0/6，自动化不代勾。
- 桌面应用：`pnpm tauri dev` 编译并启动 `sentinel-desktop`，Rust 桥按契约注入
  `--data-dir ~/Library/Application Support/org.thesissentinel.desktop --parent-pid … --resource-dir …/resources`，
  核心创建 `sentinel.duckdb` 后随应用退出被回收；本会话无法截屏（黑屏），GUI 点击流程改由
  Chrome + 真实核心的 10 个 e2e 用例覆盖。
- 外部闸门：真实 JEVDB 推理、SEC 网络、正式人工标注、真实 cassette 均 NOT_RUN/BLOCKED。

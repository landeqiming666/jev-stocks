# CR-20261104-windows-jevdb-acceptance

W-05 草案，待协调者决策。

[W-03 的本机记录](../status/W-03.md)确认 MSVC 产物能在 DuckDB 1.4.3 CLI 和项目 Python 中加载。键重叠和 NULL 短路已有本地证据，模型请求计数为零。[ADR-021](../../decisions.md)将 Windows 最终门槛留给后续 ADR。

| 选项 | Windows 验收证据 | 对交付的影响 |
|---|---|---|
| Windows 完整交付要求真实 JEVDB | Windows 产物校验、真实应用查询、统计记录与页面结果 | W-03 通过构建层，W-05 在真实查询前保持待验收 |
| Windows 先交付开发预览 | 固定扩展可加载，或者按证据登记 `jev_direct` 降级，验证 Windows 平台和本地业务链路 | 可先内部联调，Windows 真实 JEVDB 仍有单独验收项 |

决定后更新 WM-5 的判定条件，并把 Windows 的构建、真实调用和 macOS M-8 证据分别登记。

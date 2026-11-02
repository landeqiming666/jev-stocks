# CR-20261102-vite-target-watch

- 提出者（工作包 ID）：W-00
- 类型：平台问题
- 基线：`5b79539708557884c925138daa4776d1b2321c7c`
- 状态：待协调者定位并评审

## 现象与复现

在含中文及空格的仓库路径，运行 `pnpm tauri dev`。首次开发构建期间，日志多次出现：

```text
file watcher error: EBUSY: resource busy or locked, watch '...\target\debug\deps\sentinel_lib.dll'
file watcher error: EBUSY: resource busy or locked, watch '...\target\debug\deps\sentinel_desktop.exe'
```

另有编译生成的 PDB 文件被监听时报同类警告。构建随后正常结束：

```text
Finished `dev` profile [unoptimized + debuginfo] target(s) in 45.15s
Running `target\debug\sentinel-desktop.exe`
```

系统窗口清单已登记标题“投资逻辑哨兵”。因此这项是开发期监听警告，未在本轮造成启动失败。

当前 [vite.config.ts](../../../apps/desktop/vite.config.ts) 未显式排除 `src-tauri`。推测某个开发监听器覆盖了 Rust 产物目录；具体来源仍需协调者定位，W-00 不将推测当作定论。

## 依据

- [W-00](../mvp0/W-00-windows-survey.md)：桌面启动产生的问题应记录并分类。
- [Windows 车道协议](../../10-协作与工作包规范.md#9-windows-车道协议)。

## 方案与影响

1. 若确认来自 Vite，在前端监听配置中排除 `src-tauri/target` 或整个 `src-tauri`，由 Tauri 负责 Rust 源码变化。影响开发服务器配置；需验证前端热更新仍正常。
2. 若来自 Tauri 监听配置，则在该监听器排除构建输出目录。影响桌面开发配置；不得将真正的 Rust 源码一并屏蔽。

验收建议：Windows 清理本次项目构建缓存后进行首次开发构建，确认无同类产物监听警告，并分别验证前端与 Rust 源码变化仍会触发预期更新。W-00 未删除缓存或应用修复。

- 阻塞的工作包：无当前硬阻塞；建议在 Windows 开发体验收尾时处理。
- 决定：待协调者填写。


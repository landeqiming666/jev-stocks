---
id: U-00
title: 前端应用外壳、令牌、路由、状态骨架
phase: mvp0
platform: shared
lane: ui
deps: [C-05, C-06, WP-00]
size: M
owns: [apps/desktop/src/main.tsx, apps/desktop/src/Hello.tsx, apps/desktop/src/Hello.test.tsx, apps/desktop/src/shell/, apps/desktop/src/router/, apps/desktop/src/styles/tokens.css, apps/desktop/src/styles/base.css, apps/desktop/src/styles/layout.css, apps/desktop/src/app/, apps/desktop/src/i18n/]
appends: []
stubs: []
---

# U-00 前端应用外壳、令牌、路由、状态骨架

## 0. 一眼看懂

- **目标**：把 `Hello` 占位页替换成可运行的应用外壳：设计令牌、全局样式、hash 路由、启动握手、顶栏、导航、状态栏和页面插槽。
- **完成后解锁**：U-01 可以按令牌实现组件；U-02 可以在 `PageFrame` 内实现今日页。
- **预计规模**：约 18 个文件、代码加测试 750 行以内。`i18n/` 由本包建立（C-00 交接指定 U-00 负责），页面包只消费键，避免文案散落。

## 1. 背景与边界

### 1.1 为什么需要它
所有页面必须共享同一套尺寸、颜色、路由和启动状态；否则六个页面会各写一套间距，像素比对无法通过。外壳还负责把 `app.bootstrap` 的配置、引擎和离线状态变成用户可见的全局信息。

### 1.2 范围内
1. 删除 WP-00 的 `Hello` 占位组件与测试，建立 `main.tsx` 入口。
2. 逐字复制 [03](../../03-界面设计规范.md) §2.1–§2.4 的令牌到 `tokens.css`，实现 `base.css` 与 `layout.css`。
3. 实现 `AppShell`、`TopBar`、`NavRail`、`StatusBar`、`PageFrame` 和启动失败页。
4. 实现 hash 路由：`#/today`、`#/holdings`、`#/trading`、`#/risk`、`#/scan`、`#/settings`。
5. 建立 `Bootstrap` 拉取、协议版本校验、全局状态切片和事件总线。
6. 建立 `i18n/zh-CN/` 的 `common`、`today`、`holdings`、`trading`、`risk`、`scan`、`settings` 键目录；本包只写全局与框架键，页面键可先留空对象。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 组件库（Button、Drawer、Heatmap 等） | U-01 |
| 今日页、证据抽屉和业务卡片 | U-02 |
| 任何一个业务 RPC 的调用与状态机 | U-02～U-07 |
| 原生窗口装饰、标题栏拖拽权限 | C-02 与 W-01；本包只使用 `data-platform` 变量 |
| 托盘、自动扫描、通知 | v1，不在 MVP-0 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [03-界面设计规范.md](../../03-界面设计规范.md) | §2 设计令牌、§3 布局、§4.1 外壳、§8 可访问性、§9.2 对应关系 | 令牌、尺寸、键盘行为 |
| [05-接口契约.md](../../05-接口契约.md) | §4 `Bootstrap`、`DataStatus`；§5.1 生命周期；§6 通知 | 启动与全局状态字段 |
| [09-测试与评测.md](../../09-测试与评测.md) | §2 确定性、§7 像素比对 | 测试时钟与截图规则 |
| [00-术语与约定.md](../../00-术语与约定.md) | §3.2 命名、§4 时间 | 类名、时间和时区 |
| [decisions.md](../../decisions.md) | ADR-010、ADR-016 | 全局 CSS 与平台隔离 |

## 3. 前置条件

- WP-00 已交付可运行的 Vite + React 工程、`platform-macos.css` 与 `platform-windows.css` 占位。
- C-05 已交付 `RpcClient`、`call`、`subscribe` 与 `VITE_RPC=mock` 切换；C-06 已交付 `contracts/` 示例与 mock 数据。
- 不在本包修改 `package.json`、`vite.config.ts`、`platform-*.css`、`design/`。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `apps/desktop/src/main.tsx` | 替换 | 挂载 React、导入样式、设置 `data-platform`、启动 `bootstrap`；删除 `Hello.tsx`/测试 |
| `apps/desktop/src/shell/AppShell.tsx` | 新建 | 顶栏 + 导航 + 页面区 + 状态栏的组合 |
| `apps/desktop/src/shell/TopBar.tsx` | 新建 | 产品名、市场状态、引擎徽标、离线标签 |
| `apps/desktop/src/shell/NavRail.tsx` | 新建 | 5 个主导航与底部设置；`aria-current` |
| `apps/desktop/src/shell/StatusBar.tsx` | 新建 | 数据截至、最近成功扫描、token、扫描进度、固定声明 |
| `apps/desktop/src/shell/PageFrame.tsx` | 新建 | 主内容 + 可选 400px 证据列的布局容器 |
| `apps/desktop/src/router/routes.ts` | 新建 | 路由枚举、默认路由、导航元数据 |
| `apps/desktop/src/router/hash.ts` | 新建 | 解析与生成 `#/route?state=…&drawer=…` |
| `apps/desktop/src/router/useRoute.ts` | 新建 | 监听 `hashchange`，返回 `{route, params}` |
| `apps/desktop/src/app/store.ts` | 新建 | Zustand 切片：bootstrap、ui、dataStatus、budget、scanProgress |
| `apps/desktop/src/app/bootstrap.ts` | 新建 | 调用 `app.bootstrap`、校验协议、订阅通知 |
| `apps/desktop/src/app/format.ts` | 新建 | 金额、百分比、日期、相对时间的纯函数（`Intl`）；启动失败页由 `AppShell` 兜底 |
| `apps/desktop/src/app/events.ts` | 新建 | `notifyToast(tone,text)`、`navigate`、`refresh` 事件总线，供 U-08 监听 |
| `apps/desktop/src/styles/tokens.css` | 新建 | 唯一颜色来源；完整复制 §2 令牌 |
| `apps/desktop/src/styles/base.css` | 新建 | reset、字体、焦点环、滚动条、reduced-motion |
| `apps/desktop/src/styles/layout.css` | 新建 | `l-*` 外壳布局与响应式规则 |
| `apps/desktop/src/i18n/zh-CN/{common,today,holdings,trading,risk,scan,settings}.ts` | 新建 | 中文文案键；本包至少写 `common` 全部键 |
| `apps/desktop/src/{router,shell,app}/*.test.ts(x)` | 新建 | §8.1 的 7 个测试 |

## 5. 接口规格

### 5.1 公开接口
```ts
type Route = "today" | "holdings" | "trading" | "risk" | "scan" | "settings";
interface RouteState { route: Route; params: URLSearchParams; }
function parseHash(hash: string): RouteState;
function buildHash(route: Route, params?: Record<string, string>): string;
function useRoute(): RouteState;
function navigate(route: Route, params?: Record<string, string>, opts?: { replace?: boolean }): void;

function AppShell(props: { children: React.ReactNode }): JSX.Element;
function PageFrame(props: {
  children: React.ReactNode;
  aside?: React.ReactNode;
  asideOpen?: boolean;
  asideLabel?: string;
}): JSX.Element;
function bootstrapApp(client: RpcClient): Promise<Bootstrap>;
function useAppStore(): AppState;
```
- `parseHash` 对未知路由返回 `today`；空 hash 返回 `today`；保留未知 query 参数但不解释。
- `navigate` 默认 `pushState`，`replace` 为真时替换当前历史；切换路由后滚动到顶部。
- `bootstrapApp` 在 30 秒后抛 `TIMEOUT`；`protocolVersion` 不以 `1.` 开头时抛前端本地错误，映射为 `INTERNAL` 且 `data.reason="PROTOCOL_MISMATCH"`。
- `PageFrame` 在 `asideOpen` 为真时渲染 `<aside class="l-drawer" aria-label={asideLabel}>`；否则不渲染该元素。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `Bootstrap.protocolVersion` | string | 是 | 以 `1.` 开头 | 前后端协议主版本 |
| `Bootstrap.platform` | `"macos" \| "windows"` | 是 | 写入 `data-platform` | 平台样式选择 |
| `Bootstrap.engine.active` | `Engine \| null` | 是 | `jevdb`/`jev_direct`/null | 顶栏徽标 |
| `DataStatus.marketState` | enum | 是 | 5 个取值 | 市场状态文案 |
| `AppState.ui.drawerOpen` | boolean | 是 | 默认 false | 证据列是否展开 |
| `AppState.budget` | `{usedTokens,limitTokens,resetAt}` | 否 | 来自通知 | 状态栏 token |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `DEFAULT_ROUTE` | `"today"` | `router/routes.ts` | 空 hash 的落点 |
| `BOOTSTRAP_TIMEOUT_MS` | `30000` | `app/bootstrap.ts` | 启动握手超时 |
| `TOPBAR_H` / `NAV_W` / `STATUS_H` | `56px` / `68px` / `28px` | `layout.css` | 外壳尺寸 |
| `MAIN_MAX_W` / `MAIN_PAD` | `1120px` / `32px` | `layout.css` | 内容区 |
| `DRAWER_W` | `400px` | `layout.css` | 证据列 |
| `NAV_ICON_ONLY_BP` / `DRAWER_PUSH_BP` | `1080px` / `1200px` | `layout.css` | 响应式断点 |
| `WINDOW_DEFAULT` / `WINDOW_MIN` | `1280×820` / `1024×700` | `layout.css` | 验收视口 |

## 6. 实现步骤

1. 删除 `Hello.tsx`、`Hello.test.tsx`；`main.tsx` 用 `createRoot` 挂载 `<AppShell><RouterView/></AppShell>`，并把 `document.documentElement.dataset.platform` 设为 `bootstrap.platform`（启动前按平台预置 `macos` 或 `windows`）。
2. 把 §2.1–§2.4 的颜色、字体、字号、间距、圆角、阴影、层级、动效逐项抄入 `tokens.css` 的第一个 `:root`。不得改值：`--accent:#C4472D`、`--accent-text:#A93A22`、`--radius-card:10px`、`--radius-input:6px`、`--dur-in:180ms`；末尾写 `[data-market="us"]{--up:#1E7A5A;--down:#C0392B}` 与 `[data-market="cn"],[data-market="hk"]{--up:#C0392B;--down:#1E7A5A}`。
3. `base.css` 设置 `box-sizing:border-box`、`html,body,#root{height:100%}`、`body{background:var(--paper);color:var(--ink);font:var(--text-body) var(--font-sans)}`；焦点统一 `outline:2px solid var(--focus-ring);outline-offset:1px`；在 `prefers-reduced-motion:reduce` 下禁用动画与过渡。
4. `layout.css` 用 grid：`.l-app{display:grid;grid-template-rows:56px minmax(0,1fr) 28px;height:100vh}`；`.l-body{display:grid;grid-template-columns:68px minmax(0,1fr)}`；`.l-content{display:grid;grid-template-columns:minmax(0,1fr)}`，`asideOpen` 且宽度 ≥1200 时加 `400px` 第二列。
5. `AppShell` 把 `dataStatus.market` 写入 `document.documentElement.dataset.market`；`TopBar` 左留 `padding-left:var(--titlebar-inset-left)`，中段显示市场状态，右段显示 `EngineBadge` 与离线标签；市场状态由 `DataStatus` 计算：`open`→“开盘中”，`closed`→“已收盘 · 下次开盘 …”，`holiday`→“休市”。
6. `NavRail` 渲染 `今天/持仓/交易/风险/扫描`，底部 `设置`；当前项加 `aria-current="page"`、`is-active`、左缘 2px `--accent`；宽度 <1080 时只显示图标，并保留 `title` 与 `aria-label`。
7. `StatusBar` 左侧依次显示 `数据截至 {日期}`、`最近扫描 {时间}`、`今日 {used} / {limit} tokens`；右侧在扫描时显示 `扫描中 {done} / {total}`，否则显示固定声明“仅记录与提醒，不构成投资建议。”
8. `RouterView` 用 `import.meta.glob("../pages/*/index.tsx", { eager: true })` 建立页面表；没有页面模块时渲染 `PageFrame` + 空状态“页面正在搭建”，不得让路由崩溃。页面模块必须默认导出 `Page` 组件。
9. 路由切换后把焦点移到 `main` 内第一个 `h1`（`tabIndex=-1`）；`Esc` 由页面处理，外壳只提供 `useEscape` 工具，不越权关闭业务抽屉。
10. `bootstrapApp` 成功后写入 store，并订阅 `engine.changed`、`source.degraded`、`budget.updated`；未知通知忽略。失败时由 `AppShell` 渲染启动失败页，提供“重试启动”和“复制错误详情”，不显示堆栈给普通用户。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（i18n 键） |
|---|---|---|---|
| 核心进程 30 秒未响应 | 显示全屏启动失败 | `TIMEOUT` | `common.startTimeout`：“核心进程没有响应，请重试启动。” |
| `protocolVersion` 不是 `1.` 开头 | 停止业务调用 | `INTERNAL`，`reason=PROTOCOL_MISMATCH` | `common.protocolMismatch`：“请更新应用后再使用。” |
| 未知 hash | 落到今日页 | — | 不提示 |
| 缺少页面模块 | 显示占位，不白屏 | — | `common.pageMissing`：“页面正在搭建。” |
| `app.bootstrap` 返回 401/5xx | 交给 U-08 的错误映射；外壳显示启动失败 | `UNAUTHENTICATED`/`INTERNAL` | `common.startFailed` |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `parseHash_reads_route_and_params` | `router/hash.test.ts` | `#/today?state=pending&drawer=overturn` | route=`today`；`state=pending`；`drawer=overturn` |
| `parseHash_unknown_route_falls_back_to_today` | 同上 | `#/nope` | route=`today` |
| `buildHash_encodes_params_without_question_mark_loss` | 同上 | `navigate("today",{state:"scan_failed"})` | `#/today?state=scan_failed` |
| `nav_marks_only_current_route` | `shell/NavRail.test.tsx` | route=`holdings` | 1 个 `aria-current=page`，文本“持仓” |
| `shell_renders_disclaimer_and_engine_badge` | `shell/AppShell.test.tsx` | active=`jev_direct`，modelId=`jev-1.14.0` | 文本含“Jev 直连 · jev-1.14.0”与固定声明 |
| `bootstrap_rejects_protocol_mismatch` | `app/bootstrap.test.ts` | `protocolVersion="2.0"` | `reason=PROTOCOL_MISMATCH`，文案键 `common.protocolMismatch` |
| `tokens_match_contract_values` | `styles/tokens.test.ts` | 读取 `tokens.css?raw` | 含 `#C4472D`、`10px`、`180ms`，且 `:root` 只有一个 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `apps/desktop/src/app/__fixtures__/{bootstrap,bootstrap-unconfigured}.json` | `app.bootstrap/ready` 与 `unconfigured` 示例 | 从 `contracts/methods/app.bootstrap.json` 复制；不得手改时间 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd apps/desktop && pnpm vitest run src/router src/shell src/app src/styles
# 期望：7 passed，0 failed
cd apps/desktop && pnpm tsc --noEmit
# 期望：exit=0，无错误
```
### 9.2 完成清单
- [ ] `Hello` 文件已删除，`main.tsx` 不再包含“投资逻辑哨兵”大字占位
- [ ] 令牌、布局、焦点环与 reduced-motion 与 §5.3、§6 完全一致
- [ ] 1280×820 与 1024×700 截图已存到 `docs/wp/status/U-00-1280.png`、`U-00-1024.png`；本包不做像素比对，U-02 起执行
- [ ] 未修改 `owns` 之外文件；未新增依赖；未执行 git
- [ ] 已写 `docs/wp/status/U-00.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| U-01 | `tokens.css`、`base.css`、`PageFrame`、`Icon` 插槽 | 组件不得新增颜色；所有尺寸取令牌 |
| U-02 | `PageFrame`、`navigate`、`useEscape`、`notifyToast` | 证据抽屉用 `aside` 插槽；关闭后焦点回到触发元素 |
| U-03～U-08 | 路由、`PageFrame`、`app/format.ts`、i18n 键、`sentinel:toast`、`#feedback-root` | 页面默认导出 `Page`；反馈层由 U-08 监听 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 平台 CSS 未加载导致标题栏遮挡 | macOS 红绿灯压住产品名 | 在 `main.tsx` 启动前写 `data-platform`；仍失败则由 C-02 提供窗口内边距 |
| `import.meta.glob` 在 Vitest 下为空 | 页面表为空 | 测试环境注入 `__PAGE_TEST__`；生产构建以 Vite glob 为准 |

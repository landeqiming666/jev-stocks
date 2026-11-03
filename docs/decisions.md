# 架构决策记录（ADR）

> 版本：v2.0 · 2026-11-02 · 状态：已定稿
> 只记录“做了且不容易反悔”的决定。**只增不改**：推翻旧决定要新增一条 ADR，并把旧条目的状态改为“已被 ADR-xxx 取代”，正文保留作为历史。
> 本文是文档优先级最高的一份（见 [README](README.md) 第 3 节）。

| ADR | 标题 | 状态 |
|---|---|---|
| 001 | 桌面外壳选 Tauri 2 | 现行 |
| 002 | 业务核心使用 Python sidecar | 现行 |
| 003 | 进程间使用 stdio JSON-RPC | 现行 |
| 004 | 语义层双引擎（JEVDB + 兼容 LLM） | 已被 ADR-008 取代 |
| 005 | 单文件 DuckDB 作为唯一存储 | 现行 |
| 006 | MVP 不常驻后台 | 已被 ADR-007 取代 |
| 007 | v1 起托盘常驻与定时扫描 | 现行 |
| 008 | 两个引擎共用同一个固定的 Jev 模型 | 现行 |
| 009 | 美股先行，接口按多市场设计 | 现行 |
| 010 | 全局 CSS 加前缀类名，原型是实现基线 | 现行 |
| 011 | 自写调度器，不引入 APScheduler | 现行 |
| 012 | 扫描窗口按水位线推进 | 现行 |
| 013 | 模拟订单以单笔为原子单位，用回放时钟防止未来数据 | 现行 |
| 014 | 判定用五个独立的 Noul，不用 Choice | 现行 |
| 015 | 固定模型 ID，禁用别名 | 现行 |
| 016 | Mac 与 Windows 分车道并行开发，平台差异隔离在平台层 | 现行 |
| 017 | MVP-0 只交付 macOS，Windows 车道暂缓 | 已被 ADR-021 修订 |
| 018 | JEVDB 是最终验收硬门槛，SDK 仅开发降级 | 现行 |
| 019 | 风险计算固定 252 年化、逐只收益对齐、保留零方差资产 | 现行 |
| 020 | 一次 advance 一个事务；下单幂等键按意图复用 | 现行 |
| 021 | 恢复 Windows 环境摸底，正式实现逐门推进 | 现行 |

---

## ADR-001 · 桌面外壳选 Tauri 2

- 日期：2026-11-02 · 状态：现行
- 背景：需要桌面应用、安装包小、界面可控。
- 决策：Tauri 2 + 系统 WebView。
- 后果：需要 Rust 工具链构建；WKWebView 与 WebView2 存在差异，Windows 阶段需要双平台截图回归。
- 否决：Electron（体积与内存过高）。

## ADR-002 · 业务核心使用 Python sidecar

- 日期：2026-11-02 · 状态：现行
- 背景：JEVDB 是 DuckDB C++ 扩展，Jev 官方 SDK 与数值计算生态在 Python。
- 决策：Python 3.12 独立进程。开发模式直接运行；v1 用 PyInstaller onedir 打包，随安装包分发。
- 后果：安装包增加约 40–70 MB；需管理进程生命周期与打包遗漏依赖。
- 否决：Rust 全量重写（无法复用 JEVDB）；纯 Web 后端（违背本地优先）。

## ADR-003 · 进程间使用 stdio JSON-RPC

- 日期：2026-11-02 · 状态：现行
- 背景：本地 HTTP 会触发防火墙提示、端口冲突，且可能被其他本机进程访问。
- 决策：NDJSON over stdin/stdout，消息上限 1 MB。
- 后果：无法用普通 HTTP 调试；需自建请求追踪与取消机制。

## ADR-004 · 语义层双引擎（JEVDB + 兼容 LLM）

- 日期：2026-11-02 · 状态：**已被 ADR-008 取代**
- 背景：JEVDB 0.1.0 仅有 Linux x86-64 预编译包，跨平台需自行编译。
- 决策（历史）：定义 `SemanticEngine` 接口；首选 JEVDB 原生扩展，失败时降级为 OpenAI 兼容的批量判定引擎；界面必须显示当前引擎。
- 取代原因：课程唯一的硬性要求是必须使用 Jev 模型，兼容 LLM 引擎不满足。降级路径改为同一模型的官方 SDK 直连。

## ADR-005 · 单文件 DuckDB 作为唯一存储

- 日期：2026-11-02 · 状态：现行
- 背景：需要分析查询（行情、判定）与事务账本，且不想引入数据库服务。
- 决策：全部数据存于 `sentinel.duckdb`，Python 进程为唯一写入者。
- 后果：不支持多进程并发写；应用必须单实例；升级前自动备份。

## ADR-006 · MVP 不常驻后台

- 日期：2026-11-02 · 状态：**已被 ADR-007 取代**（MVP-0 的行为不变：不常驻，只手动扫描）
- 背景：常驻代理涉及系统权限、卸载残留与签名问题。
- 决策（历史）：调度仅在应用运行时生效；启动时补跑最近 72 小时。
- 取代原因：产品的核心承诺是“早上收到提醒”，应用关闭就收不到。v1 改为托盘常驻。

---

## ADR-007 · v1 起托盘常驻与定时扫描

- 日期：2026-11-02 · 状态：现行 · 取代 ADR-006
- 背景：用户多数不会在 08:30 打开桌面应用，也不会让笔记本一直开着窗口。
- 决策：
  1. MVP-0 仍是手动扫描，不常驻。
  2. v1 起，关闭窗口只销毁 WebView，Tauri 主进程与 Python 核心进程继续运行，在 macOS 菜单栏显示托盘图标；托盘菜单提供“打开”“立即扫描”“退出”。
  3. 开机自启可选，**默认关闭**，由用户在设置页打开；使用 Tauri 官方 autostart 插件。
  4. 定时扫描默认 08:30 与 20:30（用户时区）。电脑睡眠错过的扫描，在唤醒后 6 小时内补跑一次。
- 后果：
  - 关闭自启开关时必须清除自启项；卸载说明必须写明手动清理方法。macOS 上用户直接把应用拖进废纸篓不会触发清理。具体采用 LaunchAgent 还是登录项，`TODO-VERIFY(V-tray)`。
  - 关窗销毁 WebView，常驻内存预算比窗口打开时低（预算见 [02-技术架构.md](02-技术架构.md)）。
  - Windows 的托盘与自启清理由 Windows 车道的 v1 工作包完成，卸载时用 Tauri NSIS 安装器的 `NSIS_HOOK_PREUNINSTALL` 卸载钩子（来源：Tauri 官方文档，访问于 2026-11-02）。
- 否决：独立的系统级后台代理（LaunchAgent 守护进程）。需要额外权限和签名，卸载残留更难处理。

## ADR-008 · 两个引擎共用同一个固定的 Jev 模型

- 日期：2026-11-02 · 状态：现行 · 取代 ADR-004
- 背景：必须使用 Jev 模型。JEVDB 是研究代码，PyPI 0.1.0 只有 Linux x86-64 wheel；TypeSafe 提供官方 Python SDK，所有 Jev 模型走同一个 `POST /v1/systemone` 接口。
- 决策：
  1. 定义 `SemanticEngine` 接口，两个实现：`jevdb`（DuckDB 扩展，语义连接 + 键剪枝）、`jev_direct`（官方 SDK 直连）。
  2. 两者使用同一个固定的模型 ID，共用同一个问题集和同一个 `classify` 函数。
  3. 设置里可选 `auto` / `jevdb` / `jev_direct`。`auto` 优先 `jevdb`，加载失败自动切到 `jev_direct`，并发出 `engine.changed` 通知和一次可见提示。
  4. 产品里没有 LLM 引擎。若课程报告需要“逐对调用通用大模型”的对比基线，由评测脚本独立实现，不进入产品代码。
- 后果：评测必须按引擎分别报告，不得混报性能；G0-JEVDB 失败不阻塞开发，但**阻塞最终验收**（ADR-018）。
- 否决：用 JEVDB 自带的 OpenAI 兼容后端做产品引擎（不满足“必须使用 Jev”，且该后端要生成答案，更慢更贵）。

## ADR-009 · 美股先行，接口按多市场设计

- 日期：2026-11-02 · 状态：现行
- 背景：A 股、港股的公告以 PDF 为主，规则差异大（整手、涨跌停、T+1、汇率口径），数据源条款不同；美股有官方 SEC EDGAR 接口，正文是 HTML。
- 决策：MVP-0 与 v1 只实现美股。`market` 字段、`instrument_id = <market>:<symbol>`、`MarketAdapter` 协议从第一天保留，A 股、港股作为 v2 加入。
- 后果：模拟交易与风险文档只覆盖美股和美元；旧版 v1.0 的三市场设计保存在 `.kiro/backup/`，v2 开始时重新设计。

## ADR-010 · 全局 CSS 加前缀类名，原型是实现基线

- 日期：2026-11-02 · 状态：现行
- 背景：UI 原型用纯 HTML / CSS 先画出来，开发要在原型上进行。CSS Modules 会把类名哈希，无法与原型一一对应。
- 决策：样式用全局 CSS 和设计令牌（CSS 变量）；类名按 [00-术语与约定.md](00-术语与约定.md) 的前缀规则（`c-` `l-` `p-` `u-` `is-`）；原型的 CSS 原样搬进 React 应用；React 页面输出与原型相同的 DOM 结构和类名，用截图比对验收。
- 后果：需要类名纪律；禁止组件内联颜色值；禁止引入第二套设计体系。
- 否决：CSS Modules（类名无法对应）；Tailwind、组件库（体积与风格同质化）。

## ADR-011 · 自写调度器，不引入 APScheduler

- 日期：2026-11-02 · 状态：现行
- 背景：需求只有“每天两个固定时刻 + 睡眠后补跑一次”。APScheduler 是额外依赖，它的错过任务语义仍要自己再包一层才能满足“6 小时内补跑一次”。
- 决策：v1 自写约 100 行的调度器：每 60 秒检查一次“下一个应触发时刻”，支持时区和夏令时切换，记录每个计划时刻是否已执行。
- 后果：必须用单元测试覆盖夏令时切换日、睡眠唤醒、重复触发。

## ADR-012 · 扫描窗口按水位线推进

- 日期：2026-11-02 · 状态：现行
- 背景：按 `(market, trade_date)` 防重复扫描，会让“一天扫描两次”“盘后发布的 8-K 属于哪个交易日”变得含糊。
- 决策：每个市场保存一个水位线，表示“这个时间点之前的披露都已成功列出”。扫描窗口是（水位线，现在]；首次扫描默认取最近 7 天。披露按 `event_id` 去重，判定按缓存键去重，所以重复扫描天然幂等。只有同一市场已有运行中的扫描时才返回 `CONFLICT`。水位线只在所有标的的披露列表都获取成功时才推进；判定失败不阻止推进，失败的批次单独记录并在下次扫描自动重试。
- 后果：`scan_run` 不再需要 `trade_date` 列；“补扫”不再是特殊概念。

## ADR-013 · 模拟订单以单笔为原子单位，用回放时钟防止未来数据

- 日期：2026-11-02 · 状态：现行
- 背景：旧设计要求“批次中任一订单失败则整批回滚”，但一只股票涨停被拒不该让别的订单作废；另外订单要到下一交易日才撮合，“下单”和“成交”不可能在同一个事务里。
- 决策：
  1. 下单（校验、冻结资金）与撮合（成交、更新持仓与现金）是两个独立事务；每笔订单各自一个事务。
  2. 同一模拟日内先处理卖单，再处理买单。
  3. 账户带回放时钟 `clock_date`；撮合与估值只读取 `trade_date ≤ clock_date` 的行情，用查询条件而不是约定来保证不使用未来数据。
- 后果：5 分钟演示可以通过“下一交易日”按钮看到成交；规则细节见 [08-模拟交易与风险.md](08-模拟交易与风险.md)。

## ADR-014 · 判定用五个独立的 Noul，不用 Choice

- 日期：2026-11-02 · 状态：现行
- 背景：Jev 官方文档（jev-1.13 已知问题，访问于 2026-11-02）指出：Choice 的结果会偏向排在前面的选项；一个问题里藏多个条件会降低可靠性；Choice / Score 的 `confidence` 与 Noul 的概率含义不同。
- 决策：对每对（逻辑版本，段落）在同一个请求里问五个独立的 Noul（`relevant`、`against`、`contradicts`、`kill_met`、`supports`），再由确定性的纯函数 `classify` 按阈值（YES = 0.7，NO = 0.3）组合成关系。阈值与问题文本集中在 `questions.py`。
- 后果：问题多但同一请求内并行评估，不增加往返；评测必须同时覆盖问题集和 `classify`；改问题文本或阈值要升 `question_set_version`。细节见 [06-语义判定与Jev.md](06-语义判定与Jev.md)。

## ADR-015 · 固定模型 ID，禁用别名

- 日期：2026-11-02 · 状态：现行
- 背景：别名 `jev-latest` 会随新版本发布而指向新模型，答案可能随之改变；阈值是针对具体版本标定的。
- 决策：配置里保存完整模型 ID（暂定 `jev-1.14.0`，G0-JEV 后在附录确认）；每条判定记录响应里返回的 `model` 字段；升级模型必须重跑评测并在附录记录。
- 后果：升级模型是一次显式操作，不会悄悄发生。

## ADR-016 · Mac 与 Windows 分车道并行开发，平台差异隔离在平台层

- 日期：2026-11-02 · 状态：现行
- 背景：团队里一个人专职做 Windows，其余人做 macOS。两边如果改同一批文件，会频繁冲突，Windows 的问题也会拖慢 Mac 的交付。
- 决策：
  1. 工作包按 `platform` 分三类：`shared`（跨平台共享代码，两个系统都必须通过测试）、`macos`、`windows`。Windows 车道的工作包 ID 以 `W-` 开头，macOS 专属的以 `M-` 开头。
  2. `shared` 和 `macos` 工作包**不得依赖** `windows` 工作包（`scripts/check_docs.py` 强制检查）。Windows 工作包可以依赖 shared。Mac 的交付不等 Windows。
  3. 平台差异只允许出现在“平台层”：
     - `core/sentinel/platform/`：`__init__.py` 定义接口，`posix.py` 与 `windows.py` 实现
     - `apps/desktop/src-tauri/src/platform/`：`mod.rs`、`macos.rs`、`windows.rs`
     - `apps/desktop/src-tauri/tauri.macos.conf.json` 与 `tauri.windows.conf.json`（Tauri 按 JSON Merge Patch 合并进主配置，来源：Tauri 官方文档，访问于 2026-11-02）
     - `apps/desktop/src/styles/platform-macos.css` 与 `platform-windows.css`
     - `packaging/macos/`、`packaging/windows/`
     - `scripts/*.sh` 与成对的 `scripts/*.ps1`
     - `.github/workflows/ci-macos.yml`、`ci-windows.yml`
  4. 平台层之外的源码里**禁止**出现平台判断（Python 的 `sys.platform`、`os.name`、`platform.system`；Rust 的 `cfg(target_os`、`cfg(windows)`、`cfg(unix)`；TypeScript 的 `process.platform`、`navigator.platform`），由 `scripts/check_platform_isolation.py` 检查。前端需要知道平台时，读 Rust 在首次绘制前注入的 `<html data-platform>`，React 代码自己不分支。
  5. Windows 车道发现共享代码在 Windows 上有问题：能在平台层解决的在平台层解决；必须改共享代码的，提交最小修复加一个能复现问题的测试，交给该共享代码所属车道评审；**不得为 Windows 修改共享接口**，需要改接口走变更申请。
  6. 阶段目标：MVP-0 的 Windows 目标是“开发模式对等”（`scripts/check.ps1` 全绿，应用能启动，主流程可跑）；v1 的目标是 NSIS 安装包、托盘与自启清理。Windows 的验收单独记录，不影响 Mac 的 MVP-0 验收。
- 后果：
  - 像素比对在同一台机器的 Playwright Chromium 里同时渲染原型与 React 页面，不存放跨平台基线图，所以与平台无关。
  - 每个车道在自己的机器上运行 `scripts/check.sh` 或 `scripts/check.ps1`；双平台 CI 是可选项。
  - Intel Mac 仍不支持。
- 否决：在同一批工作包里用 `if windows` 分支处理差异（冲突多、责任不清）。

---

## ADR-017 · MVP-0 只交付 macOS，Windows 车道暂缓

- 日期：2026-11-02 · 状态：已被 ADR-021 修订
- 背景：团队决定先集中完成 macOS 版本；Windows 需要独立的机器、工具链与真机验收，当前不投入。
- 决策：MVP-0 与 I-02 验收只以 macOS arm64 为准；`W-00`～`W-05` 文档保留，但**不派发**，看板状态视为“暂缓”。Windows 安装包与联调推迟到 macOS 版本稳定之后。
- 后果：`platform: windows` 的工作包不再阻塞任何 macOS 交付；共享代码仍需保持平台隔离，未来重启 Windows 车道时不需要重构。

## ADR-018 · JEVDB 是最终验收硬门槛，SDK 仅开发降级

- 日期：2026-11-02 · 状态：现行 · 补充 ADR-008
- 背景：课程题目要求“基于 JEVDB”；只用 Jev SDK 不能证明完成 JEVDB 集成。
- 决策：开发期允许 `jev_direct` 保证界面与规则推进；最终验收必须展示至少一条真实 JEVDB 查询贯穿产品流程，并保存扩展版本、DuckDB 版本、SQL、`jevdb_stats()` 与界面结果。G0-JEVDB 失败时不得以 SDK 直连替代最终验收。
- 后果：JEVDB 的 macOS 源码构建成为关键路径；失败时必须修复构建，或先通过 ADR 改变交付环境，不能静默降级。

## ADR-019 · 风险计算固定年化、逐只对齐、保留零方差资产

- 日期：2026-11-02 · 状态：现行
- 背景：按窗口年数缩放年化系数会低估风险；先删缺价日会把多日收益压成日收益；删除零方差资产会改变真实组合。
- 决策：日收益统一用 252 年化；逐只按相邻交易日计算收益，再取有效日期交集；零方差资产保留在权重与协方差中，相关性与标准化 SVD 单独处理。
- 后果：窗口标签只控制数据区间，不改变年化口径；所有反例进入 P-06 回归测试。

## ADR-020 · 一次 advance 一个事务；下单幂等键按意图复用

- 日期：2026-11-02 · 状态：现行 · 补充 ADR-013
- 背景：逐单提交会造成“D+1 已成交、时钟仍为 D”；前端超时重试换新键会造成重复下单。
- 决策：`paper.advance` 的成交、正常拒单、资金、持仓、时钟与权益快照在一个事务提交；程序错误整次回滚。前端在一次下单意图开始时生成幂等键，超时或重试复用同一键；服务端支持按键查询已提交结果。
- 后果：单次推进的锁时间变长，但状态一致；ADR-013 的“单笔订单原子”仍然适用于 `paper.order.place`，`advance` 以整次推进为原子单位。

## ADR-021 · 恢复 Windows 环境摸底，正式实现逐门推进

- 日期：2026-11-02 · 状态：现行 · 修订 ADR-017
- 背景：WP-00 已完成、通过全量检查并合入 `main`；Windows 合作者具备 Windows 11 x64 机器。继续禁止 Windows 车道会让 WP-00 的 Windows 占位文件长期无人验证，但也不能据此假定 Windows MVP 已可交付。
- 决策：立即恢复并只派发 `W-00`。`W-00` 只做环境安装、运行 WP-00、记录失败和建立对等矩阵，不修产品代码。`W-01`～`W-05` 继续保持不派发，只有协调者审阅 `docs/wp/status/W-00.md` 后才能逐包恢复。macOS MVP-0、M-8 与最终验收口径不变；Windows 的任何检查结果都不能替代 macOS 验收证据。
- 后果：Windows 可以开始事实摸底；W-00 的高风险依赖缺失（例如 DuckDB、JEVDB、Tauri 工具链）先被记录，不再阻塞 Mac 主线。JEVDB 是否作为 Windows 最终门槛仍由后续 ADR 决定。

## 附录 · 闸门记录

各闸门由对应工作包填写结论。**结论为空表示尚未验证，不得在其他文档里假定结果。**

### G0-JEVDB（工作包 G0-JEVDB，macOS arm64）

| 项 | 结果 |
|---|---|
| 从源码构建 JEVDB 扩展（DuckDB 1.4.3、OpenSSL 静态链接） | 2026-11-03 真机构建通过；使用同版本 DuckDB 静态扩展，原 Python wheel 未变 |
| 以 `allow_unsigned_extensions` 加载 | 主 agent 从主集成宿主独立 LOAD 通过 |
| `jev_holds`、`jev_probability`、`jev_keys_overlap` 各调用一次 | keys overlap 三项通过；holds/probability 仅 NULL 短路核实，非 NULL 真实语义调用待有效密钥 |
| 加载耗时、扩展 SHA256 | 主审 CLI 1101 ms；`d9f3f1d613847900436af87422f0cc7c3e8e9268934559f207433e6e6d3ffd9a` |

结论：构建、加载与本地函数通过，真实语义调用未验证（缺有效密钥），G0 与 M-8 按 ADR-018 保持 BLOCKED。证据见 [G0-JEVDB 状态](wp/status/G0-JEVDB.md)，不能以 NULL 短路或 SDK 直连替代最终验收。

### G0-JEV（工作包 G0-JEV）

| 项 | 结果 |
|---|---|
| `GET /v1/models` 是否列出并接受 `jev-1.14.0` | 待测 |
| 单请求 5 个 Noul 的延迟（p50 / p95，20 次） | 待测 |
| `usage.input_tokens` 与“字符数 ÷ 3.5”估算的偏差 | 待测 |
| 429 与 `retry-after` 的行为 | 待测 |
| 中文逻辑 × 英文段落的 5 个样例 | 待测 |

结论：待测。默认模型 ID 暂定 `jev-1.14.0`。

### G1-US（工作包 G1-US）

| 项 | 结果 |
|---|---|
| SEC 可达性 | **可用**（2026-11-02）：带“名称 + 联系邮箱”的 `User-Agent` 时，`submissions`、`company_tickers_exchange.json`、`browse-edgar` 均返回 200；此前 403 系请求头不合规 |
| SEC submissions 字段 | **已验证**：`accessionNumber`、`filingDate`、`acceptanceDateTime`（ISO 8601 UTC，带 `Z`）、`form`、`items`（逗号分隔）、`primaryDocument`、`primaryDocDescription` |
| `company_tickers_exchange.json` | **已验证**：字段 `cik/name/ticker/exchange`，10,423 行 |
| 行情源 | **腾讯 `web.ifzq.gtimg.cn` 可用**（美股 1.4 s、港股 11.0 s、A 股 5.4 s）；**纳斯达克 `api.nasdaq.com` 可用**（美股 2.5 s，作备源） |
| 被否决的行情源 | Yahoo `query1/query2` 返回 403；Stooq 返回 JS 验证页；东方财富 `push2his` 返回 `rc:102` 空数据 |
| 仍待验证 | SEC 限速压测、`-index.htm` 页面结构、250 日连续性与复权语义、各源使用条款 |

结论：SEC 与行情源均可用。主源选腾讯，美股备源选纳斯达克；G1-US 仍需补齐 fixture 与上述“仍待验证”项。

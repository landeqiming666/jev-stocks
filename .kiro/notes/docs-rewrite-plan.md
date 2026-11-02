# 文档重写：计划与进度（断点续做用）

> 本文件是给执行者（人或 agent）的续做锚点，不属于产品文档，不被 `check_docs.py` 扫描。
> 旧版 v1.0 文档已备份：`.kiro/backup/docs-v1-20261102/`（工程目录没有任何 git 提交，改名用 `mv`）。

## 已确认的需求

1. 唯一硬性要求：必须使用 Jev 模型。
2. 先做美股；A 股、港股在 v2。
3. 从 v1 起关窗驻留托盘（macOS 菜单栏），开机自启可选，默认关。
4. 投资逻辑允许中文；中英文分开评测。
5. 先做 MVP-0 保底版（可演示、可交作业）。
6. 文档细到 agent 可"无脑开发"：每个工作包写明文件路径、签名、测试用例、验收命令。
7. 工作拆成小工作包，多 agent 并行。
8. 先画 UI 原型，开发在原型上进行。
9. 美观、轻量、稳定。
10. 文档可任意增删改。

## 用户已认可的假设

- A1 MVP-0 只在 macOS arm64 开发模式运行，不做安装包，目标一周左右。
- A2 Windows 推到 v1.1，Intel Mac 不再是目标平台。
- A3 优先 JEVDB 扩展；macOS 编不出来就用 Jev 直连（官方 Python SDK）。
- A4 原型用纯 HTML/CSS/JS，CSS 原样搬进 React。

## 本机环境（2026-11-02 实测）

- 系统 Python 3.9.6（`scripts/*.py` 必须仅用标准库并兼容 3.9）；`uv`、`node`、`rustc`、`cargo`、`cmake`、`ninja` 已安装；`pnpm`、`duckdb` CLI 未安装。
- 不执行 git commit；不安装依赖（需要时先问用户）。

## 新文档结构

```text
docs/  README.md  00-术语与约定  01-产品需求  02-技术架构  03-界面设计规范  04-数据模型
       05-接口契约  06-语义判定与Jev  07-美股数据源  08-模拟交易与风险  09-测试与评测
       10-协作与工作包规范  decisions.md  wp/{README.md,mvp0/,v1/,later.md,status/,cr/}
contracts/  types.schema.json  methods/<方法名>.json
design/prototype/  index.html gallery.html css/ js/ data/mock.js README.md
scripts/  check_docs.py  check_contrast.py  gen_proto_mock.py  tests/
```

文档冲突优先级：`decisions.md` 现行 ADR > `contracts/` > 05 > 04 > 06～08 > 03 > 02 > 01。工作包不能推翻文档。

## 关键设计决定（详见各文档，这里只留要点）

- D1 判定：每个"逻辑版本 × 段落"问 5 个 Noul（relevant / against / contradicts / kill_met / supports），英文问题集中在 `questions.py`。YES=0.7，NO=0.3。分类顺序：relevant<NO→none；kill_met≥YES 或 contradicts≥YES→overturn；against≥YES→weaken；上述任一落在[NO,YES)→uncertain；supports≥YES 且 against<NO→support；其余 none。关系枚举 `none|support|weaken|overturn|uncertain`。界面叫"概率"，不叫"置信度"。证据 = 只对待处理条目逐句问 Noul 取最高句（≤40 句），最高仍<NO 则用整段并标注。
- D1 引擎：`jevdb`（DuckDB 扩展）与 `jev_direct`（官方 SDK）用同一固定模型 ID（默认 `jev-1.14.0`，G0 后定）；`auto` 优先 jevdb，失败切 jev_direct 并发 `engine.changed`。产品里没有 LLM 引擎。禁止 `jevdb_on_error='reject'`；禁止 PERSISTENT secret；按"标的×文件"分批，一批失败不影响其他批。
- D1 费用：按 token 计费（单价 `pricing.toml` 带生效日期），每日预算默认 200 万 token，超出返回 `BUDGET_EXCEEDED`。jev_direct 用响应 usage；jevdb 用 字符数/3.5 估算。
- D2 美股：SEC `company_tickers.json` 每周刷新 + 内置约 100 只中文别名；MVP-0 只抓 8-K / 8-K/A / 6-K，读主文档和 EX-99.* 附件；`event_id = us:<accession>`；SEC 请求必带含联系邮箱的 User-Agent，全局 ≤5 req/s；行情直接 HTTP，不用 yfinance/pandas，源由 G1 探针定；汇率 Frankfurter；交易日历静态 `us.json`（2025–2027）；扫描按水位线推进，首次默认近 7 天，同市场已有运行才 `CONFLICT`。
- D3 今日页 = "待处理清单"：未处理的推翻/削弱条目，前 5 条展开，"待确认"折叠成一组；处理完显示"今天没有需要处理的变化"+ 上次扫描统计。
- D4 模拟交易（MVP-0 仅美股）：账户带 `clock_date` 回放时钟，"下一交易日"按钮推进；撮合/估值只读 `trade_date ≤ clock_date`；仅开盘市价单；下单按最近收盘价×(1+滑点)+费用预估并冻结资金；连续 5 个交易日无价拒单；每笔订单独立事务，先卖后买；删除"整批回滚"；表名 `paper_order`；SEC 费 / TAF 费率标 `TODO-VERIFY`；佣金默认 0，滑点默认 5 bps。
- D5 风险：持仓市值权重；共同交易日；收益在相邻共同交易日之间；Σ=XᵀX/(T−1)；收缩 α=0.1 并报告条件数；标准化收益做 SVD；年化=每年观测数=T÷窗口年数；最大回撤按当前权重回看；有效持仓数 1/Σw²；样本<60 → `DATA_INSUFFICIENT`；MVP-0 只做美元口径；测试用解析解已知矩阵。
- D6 架构：开发模式 Rust 启动 `SENTINEL_CORE_CMD`（默认 `uv run --project core python -m sentinel`）；v1 打包用 PyInstaller onedir 放 `bundle.resources`；sidecar 线程模型：stdin 读线程直接处理 ping/取消，4 线程池处理请求，扫描专用线程，DuckDB 每线程 cursor，取消用 `con.interrupt()`。依赖白名单——Python：duckdb==1.4.3、typesafe-sdk、httpx、selectolax、numpy、keyring、pydantic；前端：react、zustand、lucide-react（v1 加 lightweight-charts）；禁用：pandas、scipy、yfinance、akshare、APScheduler、lxml、PyMuPDF(AGPL)、UI 组件库、CSS 框架、路由库。v1 自写 60 秒调度器，唤醒后 6 小时内补跑一次。
- D7 新错误码：`CONFIG_REQUIRED`、`BUDGET_EXCEEDED`；`UNAUTHENTICATED` 只表示 Jev 返回 401。
- D8 钥匙串只由 Python 访问；用户数据一律软删除（`holdings.remove`→`holdings.archive`），例外：重置模拟账户、清空全部数据（需输入确认文字并先自动备份）；每只股票最多 5 条有效逻辑，正文 1–500 字；只关注不持有 = 持仓数量 0。
- D9 UI：保留"静默账簿"；主按钮改墨色，朱红只用于当前导航项/焦点环/选中行；`--muted` 与 `--verdict-none` 改 `#64676F`（旧值 `#6B6E76` 在 `--surface-2` 上仅约 4.48:1）；导航=今日、持仓、交易、风险、扫描，设置在底部，复盘 v1 加；样式用全局 CSS + 前缀类名（`c-` 组件、`l-` 布局、`p-` 页面、`is-` 状态）；React 输出与原型相同的 DOM/类名，Playwright 截图差异 ≤1%（1280×820），1024×700 无横向滚动。

## 【2026-11-02 追加】用户新要求（优先于上面与之冲突的内容）

1. **Mac 与 Windows 的开发任务要分开**：Windows 交给一个人并行做，其余人做 Mac。→ 取消"Windows 推到 v1.1"；改为独立车道 `W-xx`，MVP-0 阶段要求 Windows 开发模式与 Mac 对等，v1 阶段各自出安装包。Intel Mac 仍不做。
   - 工作包头部新增 `platform: shared|macos|windows` 与 `lane`；规则：`shared`/`macos` 不得依赖 `windows`（Windows 不能阻塞 Mac）。
   - 平台差异必须隔离在：`core/sentinel/platform/`、`apps/desktop/src-tauri/src/platform/`、`tauri.<平台>.conf.json`、`packaging/<平台>/`、`scripts/*.ps1`、`apps/desktop/src/styles/platform-<平台>.css`、`.github/workflows/ci-<平台>.yml`。
   - 截图像素比对在同一台机器的 Playwright Chromium 里同时渲染原型与 React 页面，不存基线图，因此与平台无关。
2. **工作包要写得足够详细**（用户反馈上一版概要表太粗）。每个工作包必须含：目的与边界、必读文档小节、前置条件、要创建/修改的每个文件（路径 + 职责）、公开接口完整签名、数据结构字段表、算法步骤、错误与边界情况、先写的测试（测试名 + 输入 + 期望）、要录制的 fixture、验收命令与期望输出、完成清单、明确不做、给下游的交接。
3. `check_docs.py` 增加：`platform`/`lane` 校验、`owns` 互不重叠、`appends` 必须被某个工作包 `owns` 覆盖且追加方传递依赖拥有方。
4. 工作进度：已完成 T1、T2；T3（02 技术架构）进行中。随后：ADR-016（平台分离）、10 协作规范与工作包模板、样板工作包 WP-00 / W-00，请用户确认详细程度后再批量写其余工作包。

## 阶段范围

- MVP-0：美股标的搜索；持仓与逻辑；手动扫描 8-K/6-K；Jev 判定与证据；待处理清单 + 证据抽屉；扫描统计；回放模式模拟交易；美元口径风险；设置页；演示数据脚本；≥60 对标注集 + 评测脚本。验收分"必须"（主流程全通 + 断网可看已有数据）与"应该"（JEVDB 引擎可用；页面与原型像素差 ≤1%）。
- v1：托盘常驻/自启/调度补跑/通知+飞书/首次引导/复盘页/命令面板/CSV 导入/10-Q 10-K 20-F/Form 4/人民币口径/限价单/诊断备份/macOS 安装包/≥200 对评测 + G2/7 天稳定性。
- v1.1：Windows。v2：A 股、港股。

## MVP-0 的 33 个工作包

WP-00；G0-JEVDB、G0-JEV、G1-US；C-01 RPC 服务端、C-02 Rust 桥接+前端 RPC 客户端、C-03 存储与迁移、C-04 设置与钥匙串；D-01 HTTP 基础设施、D-02 标的与搜索、D-03 SEC 文件抓取、D-04 行情/汇率/交易日历；S-01 分句分段、S-02 引擎接口+Jev 直连、S-03 JEVDB 引擎、S-04 判定流水线；P-01 持仓与逻辑、P-02 扫描编排、P-03 待处理清单、P-04 模拟交易、P-05 风险；U-00 前端骨架、U-01 组件库、U-02 今日页、U-03 持仓页、U-04 扫描页、U-05 交易页、U-06 风险页、U-07 设置页；E-01 演示数据、E-02 标注与评测；I-01 联调、I-02 验收与演示。

WP 文件名用 ASCII：`docs/wp/mvp0/C-03-storage.md`；分支 `wp/<ID>`；头部 YAML 子集（单行 `key: value` 或 `key: [a, b]`）含 `id/title/phase/deps/size/owns`。规模 S<300 行、M 300–800 行，MVP-0 不允许更大。

## 任务清单

- [x] T1 文档骨架 + 00 + README + `scripts/check_docs.py`（32 个单测通过；06～09 与 wp/README 是"待重写"占位）
- [x] T2 01 产品需求（15 条用户故事 US-01～US-15）+ decisions.md（ADR-004/006 标已取代；新增 ADR-007～015，比计划多 014 五个 Noul、015 固定模型 ID）
- [x] T3 02 技术架构
- [ ] T4 06 语义判定与 Jev（含手工走通的虚构 8-K 样例）
- [ ] T5 07 美股数据源 + 08 模拟交易与风险（数值样例用标准库复算）
- [ ] T6 04 数据模型（全部 DDL，标注阶段；有 DuckDB 1.4.3 时实跑，需安装先问）
- [ ] T7 05 接口契约 + `contracts/`（37 个 MVP-0 方法）+ `gen_proto_mock.py`
- [ ] T8 03 界面设计规范 + 原型基础（tokens/base/layout/components/gallery）+ `check_contrast.py`
- [ ] T9 原型页面（MVP-0 全状态；v1 只画草图）
- [~] T10 10 协作规范（已完成）+ 看板 wp/README.md（已完成，44 个工作包）+ 样板 WP-00 / W-00 / W-01（已完成）；09 与其余 41 个工作包待写
- [ ] T11 全量一致性检查（旧口径残留：0.45/0.65、`llm` 引擎、APScheduler、CSS Modules、`trade_date` 幂等、整批回滚、`macos-13`、右键打开）+ TODO-VERIFY 归属 + 人工审阅清单

## 写作标准

- 用"必须 / 应该 / 可以"区分强弱；每条要求可测试；写确切数值；不写"等""适当"。
- 未核实的外部事实写 `TODO-VERIFY(<工作包ID>)`；引用写 URL 和访问日期（2026-11-02）。
- 代码注释和文档字符串用中文；标识符、日志、提交信息、测试名用英文。
- 文档头部：H1 之后第一段引用块含 `版本：vX.Y · 日期 · 状态：已定稿|待重写`。

## 外部来源（访问日期 2026-11-02）

- JEVDB：https://github.com/PDAIS/JEVDB （README、docs/settings.md、cascade.md、pruning.md、functions.md、building.md）；PyPI https://pypi.org/project/jevdb/
- TypeSafe/Jev：https://docs.typesafe.ai/ （models、api/system-one、api/errors、primitives/noul、confidence、model-jaggedness/jev-1.13、sdk/python、agent-skill）
- Tauri：https://v2.tauri.app/develop/sidecar/ 、https://v2.tauri.app/distribute/windows-installer/ 、https://v2.tauri.app/plugin/autostart/
- GitHub macos-13 退役：https://github.blog/changelog/2025-09-19-github-actions-macos-13-runner-image-is-closing-down/
- Apple Gatekeeper：https://developer.apple.com/news/?id=saqachfa
- NYSE 休市日：https://www.nyse.com/markets/hours-calendars
- Frankfurter 汇率：https://api.frankfurter.dev/v1/latest?base=USD&symbols=CNY,HKD

## 其他文档里已经"承诺"、需要后续工作包落实的东西

- `scripts/check.sh`（WP-00）、`scripts/load_demo.sh`（E-01）、`scripts/eval.sh`（E-02）：01 的验收引用了它们。
- 动作枚举新增 `reopen`（US-09 的"重新打开"）：04、05、contracts 要同步。
- 设置页"载入演示数据"按钮 + 清除演示数据：05 需要 `demo.load` / `demo.clear` 方法。
- 每日 token 预算默认 2,000,000，设置页可改；需要 `settings` 字段。
- G0-JEVDB 只验证三个函数：`jev_holds`、`jev_probability`、`jev_keys_overlap`（产品不用 `jev_choose`/`jev_score`）。
- 兜底：01 §10 的对比实验基线若要"逐对调用通用大模型"，由评测脚本独立实现（09 写明，可选）。

## 【进度快照】

- 已定稿：README、00、01、02、10、decisions（ADR-001～016）。
- 占位（待重写）：03、04、05、06、07、08、09。
- 工作包：看板 `docs/wp/README.md` 由 `.kiro/notes/wp-list.json` 生成（44 个，波次 0–9，Mac 关键路径 10 步）。已写完整文档：WP-00、W-00、W-01。（**已过期**：见文末【进度快照 · 交接前】，现为 45 个，看板由 `scripts/gen_wp_board.py` 从 `docs/wp/backlog.json` 与工作包头部生成。）
- `scripts/check_docs.py`：51 个单测；已支持 platform/lane/owns 互斥/appends/stubs 校验。
- 下一步顺序（工作包依赖各文档小节，所以先写文档）：
  1. 04 数据模型（预分配迁移编号给具体工作包）→ 05 接口契约 + `contracts/` → 06 → 07 → 08
  2. 03 界面规范 + 原型（token → gallery → 页面）
  3. 09 测试与评测
  4. 其余 41 个工作包（按波次，每个都要达到 10 的 4.2 节 D1–D10）
  5. T11 全量一致性检查
- 待办备忘：
  - 看板重新生成脚本：当前内联在对话里；工作包全部写完后，把生成逻辑存成 `scripts/gen_wp_board.py`（含 `--check`）以免手工漂移。
  - `check_docs.py` 还缺：用户故事 / RPC 方法 / 原型页面被工作包覆盖的检查（T10 末尾加）。
  - 00 里的 ADR 锚点链接我改成了不带锚点的 `decisions.md`，避免中文标题锚点变动。

## 【夜间自主工作，用户已睡，无法审批】

约束：只写工作区文件；只跑标准库/本地脚本；不安装依赖；不 git commit；不删除；不起长驻进程。
用户明确要求：UI 用 HTML 做原型；其余自己写完，明早用户来审阅。

顺序（每完成一步就更新本节，防止中断后接不上）：
1. [ ] 示例数据创作脚本 `.kiro/notes/author/`（Python）：同一份数据同时产出 `design/prototype/data/mock.js` 和 `contracts/`。
2. [ ] HTML 原型 `design/prototype/`：css/（tokens base layout components pages platform-*）、js/（经典脚本，非 module，file:// 双击可开）、index.html、gallery.html、README.md。页面 = 今日(多状态)/证据抽屉/持仓/交易/风险/扫描/设置 + v1 草图。
3. [ ] `scripts/check_contrast.py`、`scripts/check_proto.py`（+ 单测）；用 `node` 渲染并校验 HTML。
4. [ ] 05 接口契约 + `contracts/`（约 40 个方法）+ `scripts/gen_proto_mock.py --check`。
5. [ ] 04 数据模型（迁移编号预分配给工作包）。
6. [ ] 06 语义判定与 Jev → 07 美股数据源 → 08 模拟交易与风险。
7. [ ] 03 界面设计规范（以原型为准）。
8. [ ] 09 测试与评测。
9. [ ] 其余 41 个工作包（按波次，达到 10 的 4.2 节 D1–D10）。
10. [ ] T11 一致性检查、README 进度表、去掉"待重写"。

关键设计（原型 / 契约共用的命名，别改）：
- 关系 `none|support|weaken|overturn|uncertain`；headline = max(against, contradicts, killMet||0)。
- 动作 `still_valid|revise|exit_intent|ignore|reopen`。
- 卡片可见按钮：查看原文 / 仍然成立 / 修正逻辑 + "更多"（准备卖出、忽略）。
- 虚构公司 ZZAR ZZFD ZZCL ZZBK ZZEN ZZMD；原型“当前时间” 2026-11-02 08:31 (UTC+8)；美股状态=已收盘（上个交易日 2026-10-30，周五；美东 11-01 已转冬令时）。
- 模拟账户回放日期 2026-10-14；起始 2026-09-01。
- 金额/价格在 JSON 里是十进制字符串；比例/概率是 number。

- 【发现】S-01 分句器必须处理缩写（Inc. Ltd. Corp. Co. U.S. No. 等）与 "Item 8.01" 这类小标题，否则证据句会被截断。示例数据里 E1/E2 的证据句序号是按"简化切分器"数的（Inc. 被当成句号）；S-01 的规格里要给出缩写表和测试用例，并在 06 的手工走通样例里用真实切分结果。

## 【用户新指令：先把 03～09 七份文档写完】

顺序：04 → 05 → 06 → 07 → 08 → 03 → 09。原型（HTML）和 contracts/ JSON 在七份文档之后做；03 里按"原型待建"如实写。
注意：执行命令现在可能需要用户批准（上一条 python 测试被取消）。尽量少跑命令，攒到最后一起跑：
  python3 -m unittest discover -s scripts/tests   |   python3 scripts/check_docs.py

示例数据（.kiro/notes/author/）与约定不一致，之后重新生成 mock/contracts 前要改：
  1. 金额字符串必须 4 位小数（"100000.0000"），成交价/限价 6 位；`dec()` 默认位数应为 4。
  2. `lastClose` 是行情价格 → JSON number（不是字符串）；`Position.lastClose` 同理。
  3. DecisionSummary 要加 `thesisCurrentVersion:int`（用来显示"逻辑已更新"）。
  4. check_contrast.py 的 PAIRS：把 ("--accent","--accent-soft") 换成 ("--accent-text","--accent-soft")；
     原因：#C4472D 在 #FBEDE9 上只有约 4.29:1，需要单独的文字色 --accent-text:#A93A22（约 5.5:1）。
  5. 迁移执行规则：应用"所有未记录的迁移"，不是"编号大于当前最大值"（并行开发时低编号迁移可能后合并）。
方法清单共 40 个，通知 7 个，错误码 15 个（见 05）。迁移编号：001 C-03 setting；002 D-02 instrument；003 P-01 portfolio；
004 D-03 filings；005 D-04 prices；006 S-05 decision；007 P-03 actions；008 P-02 scan；009 S-02 usage；010 P-05 paper；011 P-06 risk_run；012 E-01 demo_row。


## 【进度快照 · 03～09 全部完成】

- 已定稿：README、00～10、decisions。`check_docs.py --strict` 应为 0 错误（见本节末尾的命令）。
- 对比度：03 的令牌经 `check_contrast.py` 实测 32 对全部达标（实测值已写回 03）。
- 单测：`python3 -m unittest discover -s scripts/tests` 通过（check_docs 51 个 + check_contrast 10 个）。
- 仍待做（按优先级）：
  1. **HTML 原型** `design/prototype/`：用户明确要求。mock 数据的创作脚本在 `.kiro/notes/author/`（先按"待修正项"改：金额 4 位小数、lastClose 是 number、DecisionSummary 加 thesisCurrentVersion），再 `python3 build_mock.py` 生成 mock.js。
  2. `contracts/` JSON（40 方法 + types + errors + notifications）+ `scripts/gen_proto_mock.py`、`scripts/check_proto.py`、`check_contracts.py`（带最小 JSON Schema 校验器）。
  3. 其余 41 个工作包（按波次；每个达到 10 的 D1–D10）。
  4. T11 一致性检查；README 去掉"重写进度"一节。
- 07 里 06 对 S-01 的引用：S-01 工作包要写明"缩写表（Inc. Ltd. Corp. Co. No. U.S. …）+ 'Item 8.01' 小标题 + 引号/括号内句号"的分句规则。
- 08 的账本/费用样例已用标准库复算；其中"测试专用费率"不是真实费率，不得写入 us.toml。


## 【进度快照 · 交接前（2026-11-02）】

文档作者阶段结束，后续工作交给其他 agent；入口是 `docs/wp/HANDOFF.md`。

- 已完成：
  - 文档：`docs/` 下 00～10、`decisions.md`（ADR-001～016）、`README.md`，全部“已定稿”。
  - 原型：`design/prototype/`，7 个页面、43 个页面状态 + 今日页 6 种证据抽屉（共 49 个画面）、陈列页；`check_proto.py` 通过；Chrome 实测 1024 与 1280 宽度下 49 个画面都没有横向溢出。
  - 工作包：看板 + `backlog.json` 共 45 个（Mac 与共享 39 个，Windows 6 个）；已写完整文档的 3 个：WP-00、W-00、W-01。新增 C-06（契约 JSON、`gen_proto_mock.py`、`check_contracts.py`）。
  - 脚本：`check_docs.py`、`check_proto.py`（+ `proto_render.js`）、`check_contrast.py`（32 对）、`gen_wp_board.py`；单元测试共 105 个。
  - `docs/wp/HANDOFF.md`：现状、缺口、顺序、禁区、没验证过的清单。
- 还没做：
  1. 其余 42 个工作包文档（批次见 HANDOFF 第 2 节）。
  2. `contracts/` 与 `gen_proto_mock.py`、`check_contracts.py`（工作包 C-06；验收是生成结果与现有 `mock.js` 逐字节一致）。
  3. 全部产品代码（从 WP-00 开始）。
- 示例数据的创作来源仍是 `.kiro/notes/author/`；C-06 完成后归档。
- 用户的指令：不自行提交 git；不删除 `.kiro/backup/` 与 `.kiro/notes/`。
- 已把 03 的“原型状态”、第 9.1 节、README 第 9 节、原型 README 的过渡期说明同步为“原型已建成”。

# N10-01 下一批执行澄清

- 状态：已批准。
- 日期：2026-11-03。
- 类型：所有权补全、验收口径与离线开发边界。
- 决定：主协调 agent 采用以下最小澄清，不改变产品范围或最终 M-8 门槛。

## 1. 代码交付不冒充外部闸门

G0-JEV、G0-JEVDB、G1-US 可先实现探针和确定性测试，但缺少有效凭据、联系邮箱或实测响应时，报告必须为未验证或阻塞。合成 HTTP 响应只用于单元测试，不得写成已录制的真实 cassette。`core/tests/fixtures/jev/` 的成功 cassette 保持缺失直到真实录制；不得照文档中的示例概率伪造通过。

G0-JEV 第 11 节已经允许保留全 mock 开发；S-02/S-03 在闸门未过时可以实现基于已安装 SDK 源码核实的接口和离线测试，但不得冻结实测参数、标记真实调用已通过或解除 `TODO-VERIFY(G0-JEV)`。D-03/D-04 只能消费有来源的实际录制或明确标注为合成的单元测试数据，外部验收保持待测。

## 2. C-05 所有权与语义

补全 `scripts/tests/test_gen_ts_types.py` 的所有权，允许生成器回归测试。用户可见的传输层兜底文案集中在 C-05 自有 `rpc/errors.ts` 的目录中；传输层不得反向依赖尚未交付的 U-00 文案模块。

已知方法在某个 mock 场景没有映射时使用第一个成功示例；不属于 `MethodMap` 的未知方法才返回 `INVALID_ARGUMENT`。未知 wire 错误统一为 `INTERNAL`，原始未知值最多保留在安全诊断字段，不作为公共 `ErrorCode`。

生成器遇到不支持或非法 schema 时退出 2；先完整构造全部输出，再原子发布，失败不覆盖既有生成物。支持本仓库实际使用的 `anyOf`、nullable 和附加属性约束；不得用 `any` 隐藏无法映射的 schema。

## 3. JEVDB 构建路径与记录

仓库路径包含普通空格，构建计划和探针必须支持；拒绝单引号、NUL 与换行的 LOAD 路径。构建源码、扩展和运行 lock 写入被忽略的 `.dev-data/jevdb/`，仅提交来源 pin、说明、脚本和不含本机秘密的状态报告。`vendors/jevdb/build.lock.json` 不作为提交的机器运行产物。

构建脚本不自动安装工具、不改变 DuckDB 版本、不修改系统签名策略。上游实际命令与文档不一致时先报告证据，由主 agent 更正文档后再实现。

## 4. 评测口径

以 01 第 8 节 M-5 和 09 第 9.1 节为准：MVP-0 要求完整报告，不设 F1 通过线；F1 0.80 与中文差异门槛属于 v1。E-02 可以保留显式 `--gate` 供后续使用，I-02 的 MVP-0 最终验收不得默认调用该质量门槛或因 F1 低于 0.80 判失败。

## 5. 脚本测试使用已有锁定运行时

G0 探针使用已锁定的 `httpx` 与核心公共模块，且规定测试含 pytest 函数；宿主 Python 的 unittest discover 既可能缺少依赖，也不会收集 pytest 函数。主 agent 在 `scripts/check.py` 将 scripts-test 改为 `uv run --project core python -m pytest -q scripts/tests`，继续收集所有既有 unittest 与新增 pytest，不跳过任何探针测试，不增加依赖。先失败证据保存在 `/tmp/jev-next10-runner-red.log`；对应回归由主 agent 追加于原 `test_check_runner.py`。

## 6. 晚注册前端的核心就绪竞态

Rust 的 `core://status` 事件不缓存，核心就绪事件可能早于前端监听。主 agent 为 C-02 增加只读本地 Tauri 命令 `core_status`，返回当前 `{state,attempt}`；它不是业务 JSON-RPC 方法，不改变 40 个方法、协议版本或外联权限。C-05 在两个监听建立后只查询一次，用状态事件继续更新；查询期间收到更新事件时不得用旧快照覆盖它。不轮询、不允许未就绪业务调用。

对应主审 Rust helper `core_status_snapshot(&BridgeState)` 与真实子进程回归验证晚读取仍得 Ready、状态字段不含请求或配置。I-01 的仅测试 IPC 桥增加这个只读命令的映射。

## 7. UI 所有权与接口补全

U-00 补全 `styles/tokens.test.ts` 所有权，状态目录下的两张规定截图可随状态报告交付。原型没有 IBM Plex 字体文件时，本批 React 与原型使用同一系统回退；不偷偷下载字体、修改其他包的资产或许可证文件。U-00 的 common 文案包含 U-01 所需的标签、引擎、市场、关闭提示和 `chartInvalid`，U-01 不反向修改其 i18n。

U-01 的 Menu 必须提供 `onClose`；React 19 触发按钮 ref 允许 null。补全 Modal 和非有限条形值两项测试，使文档规定的 12 项有对应清单。组件 CSS 与仅开发用的陈列入口可位于 U-01 自有 `components/ui/`；不得修改原型来凑像素结果。主 agent 独立检查键盘、两种抽屉模式、图表和两个规定视口。

## 8. 数据源与模型错误的消费者一致性

D-01 不替调用方补 SEC User-Agent。D-03 的 `SecFilingsClient` 追加与 D-02 相同的可选 keyword-only `email_provider`；每次请求动态校验，缺配置不发请求。C-07 同时为 ticker 与 filing 两个客户端注入 provider。D-03 使用当前 selectolax Lexbor，不新增依赖。

C-00 的 EngineError 扩充允许 RATE_LIMITED/TIMEOUT，与 S-03 和 06 的已定错误映射一致，既有 15 个公开错误码与 retryable 不变。S-03 的 `map_sdk_exception` 返回共同基类 SentinelError，对实现错误使用 InternalError；不放宽 EngineError 接受 INTERNAL。主 agent 先增回归再修正基础错误族。

## 9. 探针 CR、规模与构建路线

已批准 G0-JEV、G0-JEVDB、G1-US 的 MVP-0 规模为 L：分别约 1600、1500、1200 行实现加测试，最终报告实际计数；安全、来源、超时和失败回归不得通过删测试压缩。生成数据单列；继续保持独立所有权与完整主审。

G0-JEVDB 的固定 MIT 文件没有 SPDX 行，上游脚本硬编码并行 4；批准验证标准 MIT 文本、固定源哈希并执行等价 CMake 配置且并行 2。DuckDB 1.4.3 CMake 明确将 `EXTENSION_STATIC_BUILD=ON` 列为可分发加载扩展的常规路线，用于宿主未导出 C++ 符号的情形。批准在 ignored 开发目录构建同版本静态 DuckDB 扩展（`BUILD_EXTENSIONS_ONLY=OFF`），不替换 Python wheel、版本、锁文件或系统策略；是否实际可加载仍必须实测，不能先宣称修复。

隔离检查只排除已 ignored 的 `.dev-data` 开发源码，并采用目录剪枝避免扫描巨量构建缓存；新增回归保证真实应用源码仍被检查。`vendors/jevdb/build.py` 是自有平台构建包装，批准仅该精确文件读取平台，不允许其他 vendor 源码绕过。前置红色证据为 `/tmp/jev-next10-isolation-red.log`。

G1-US 历史 SEC 表不存在重复或空白 ticker，不伪造真实行；独立 synthetic 边界 fixture 必须显式标注。当前腾讯港股实际行可带第七个公司行动对象；批准仅在核实该对象形状时解析前六列并保存原始来源，不接受未知额外列。成交量精度与单位不猜测，低行数、陈旧数据和 250 日不足都不能判为通过。06 的问题集声明统一为已经批准的 `.2`，探针局部问题快照在 S-02 接管之前仅为可核对 bootstrap 数据。

## 10. C-05 生命周期、超时与规模

已批准 C-05 规模 L，约 1800 行手写实现与测试（生成的 TypeScript 数据另列），保留全部 70 项首轮测试和主审新增回归。采用 whenReady/dispose 的最小生命周期接口，不增加业务 RPC。默认超时以机器契约 METHOD_TIMEOUTS 为准，尤其 scan.retryBatch 的 60 秒不能被默认 30 秒覆盖。

生成器必须校验 index 方法、通知的非空数组与唯一性以及非空错误码和布尔 retryable，不输出重复或不完整的 TypeScript。多文件生成是单文件原子替换加异常回滚；进程中断的跨文件一致性由 --check 阻断，不宣称批次崩溃原子性。

U-00 按真实 Bootstrap 契约装配，不伪造尚未返回的 DataStatus/预算/扫描数。就绪等待与 bootstrap 调用共享 30 秒预算；mock 标识始终可见。S-02 的证据模板统一为 06 的无反引号文本，版本仍是已经批准的 `.2`，不在同版本保留两套文字。

## 11. G0-JEV 开发交付的时限限制

主审复现并要求修复公开 run_probe 的 not-live/offline 网络开关以及 bool 超时输入。修复回归必须证明函数入口和运行中转离线均不会继续请求。当前 httpx 配置只验证网络操作超时，不等于流式响应的端到端总时限或体积上限；批准保留该限制的开发交付，报告显式 `timeout_semantics=per_operation`、`total_request_timeout_verified=false`，不能改写成已验证。

这不放宽生产 D-01 的每次网络尝试总时限或 S-03 的批次取消要求。G0-JEV 真实模型、人工复核、定价及成功录制仍待有效凭据；本批总账不得把代码测试通过计为外部闸门通过。

## 12. 本轮真实数据与隔离配置的补充

G1-US 主审追加安全回归后实际规模约 1600 行（首轮加补丁 1515 行），已批准保留 95 项测试；来源九份 payload 哈希保持不变。只有观察/解析自动化验收通过，SEC 和完整来源闸门不因此通过。

主 agent 另测腾讯 `usAAPL.O` 后缀候选仍为 0 行，不能猜映射；Nasdaq AAPL 的 `limit=250`、`fromdate=2025-01-01` 真实返回 250 行（2025-11-04 至 2026-11-02）。D-04 在过滤无效和超窗口数据后，对不完整的主源尝试备源，选择覆盖更完整者；不足历史必须可见，不引入新行情源。原始完整价格仅保留在临时开发目录，公开仓库仍只用裁剪样本和统计。

G0-JEVDB 主审独立实测静态扩展 LOAD、本地 overlap、NULL 短路、32 个 stats 且请求数 0；原 wheel 未变。探针隔离进程必须应用显式 env，而不是误用父进程另一枚 key。JEVDB 的 endpoint 是 `/v1/` 前缀，会自动拼 systemone；批准消费完整 JEV_ENDPOINT 并使用绑定 SET，主审已经确认 SET 参数可绑定。该补充不增加外部权限或泄露 URL 中的凭据。

## 13. S-02 的集中降级文案与规模

已批准 S-02 规模 L，约 1300 行实现、typed fake 与测试，SQL/TOML 另列；保留 85 项首轮回归。主 agent 在既有 `messages/app.py` 注册精确 `engine.changed` 文案，独立测试真实公共目录，不让单测临时注入掩盖生产缺键。

semantic 的模型适配层可以静态调用 security.redact 注册和清理密钥，禁止 raw SDK 响应、异常或 request ID 回显秘密；domain 层仍不依赖 security 或任何 I/O。主 agent 对这两个原先失败的边界追加测试后修正分层与文案，不动态导入绕过检查。真实模型与价格仍保留 G0 未验证标识。

## 14. U-00 的原型一致性与规模

已批准 U-00 规模 L，约 1500 行实现加测试，契约样例与两张截图另列；保留 42 项首轮定向和 3 项浏览器检查。正文与原型字体回退次序不一致时采用已建成的原型 `IBM Plex Sans, system-ui, CJK`，03 同步该顺序，不下载额外字体或改原型。

应用外壳保留原型 top/nav/body/status 四个 grid-area，PageFrame 在 body 中管理正文/aside，尺寸和 1199/1200 断点不变；U-00 的文字示例同步实际结构。日期格式化消费契约合法 UTC 小数秒（共享时钟实际六位），只截断到 JavaScript 毫秒、不跨秒舍入；尚无 DataStatus 时仅用真实 Bootstrap 已提供的 engine 信息标明 auto 降级。配置提示准确列出实际缺少项，不能把只缺邮箱说成密钥也没配置。

## 15. D-03/D-04 集成前置与来源引用

主 agent 复现 P-01 单元 fixture 默认跑全部迁移后又自行建下游表的冲突。批准只在其单元 fixture 用临时目录精确复制 001–003，再执行已有下游缺表/损坏表测试；不改权威 DDL、不跳过测试、不阻止生产或集成执行全迁移。新增回归固定 schema_version=3，先失败证据 `/tmp/jev-next10-portfolio-fixture-red.log`。全迁移互操作另由跨包测试覆盖。

已批准 D-03 与 D-04 规模 L，各约 2000 行实现加测试，保留 193/147 项首轮回归，fixture/DDL另列。D-03 保留披露、文件、段落和判定永久身份，不删除重建已有 event_file；同身份只更新未被段落引用的非键内容，身份变化或已引用正文变化明确 CONFLICT 且整事件回滚。D-03 的部分失败缓存问题必须修复后主审通过，不能把有正文但失败的 EX-99 永久缓存为完整。

批准 D-03 最小补齐策略：索引网络失败/身份冲突或选中文件 failed 时事件 content_status=fetch_failed，成功正文仍保存；该状态阻止消费者误认完整并保留重试机会。再次抓取重新获取索引，只重试缺失/失败文件，复用同身份且 extracted/empty 的成功文件。已存在的旧 full_text 带 failed 行也不能跳过。失败文件恢复后可新增段落，但不能改变已有段落引用的正文或文件身份；失败/取消不推进消费者水位线。无需新增数据库列或修改既有 004 DDL。

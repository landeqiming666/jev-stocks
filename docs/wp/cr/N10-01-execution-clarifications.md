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

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

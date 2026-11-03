# G0-JEV 实现与真实闸门状态

> 版本：v1.0 · 2026-11-03 · 状态：已定稿

- 代码交付：PASS（离线实现及自动测试）；真实模型闸门：BLOCKED。
- 原基线：`7b366dc7ae1a48863d8375fcc9a1a4179faf3452`。
- 用户授权 cherry-pick 的门禁前置：`78673adf3f3a7407fa216292b0fe61ff8b2cf5a3`；本地对应提交：`4c6fc4e99092b152af45088865e2b2a654b967de`。
- 自有修改：`scripts/probe_jev.py`、`scripts/tests/test_probe_jev.py`、本文。
- 无有效 `JEV_API_KEY` / 自定义 `JEV_ENDPOINT`；没有发出真实模型请求。
- `fixtures_written=[]`；`core/tests/fixtures/jev/` 的四份成功 cassette 和 manifest 均保持缺失。

## 可执行路径

```sh
# 使用已有锁文件，不调整依赖。
(cd core && uv sync --frozen --offline)
(cd core && uv run --offline pytest ../scripts/tests/test_probe_jev.py -q)
scripts/check.sh --only scripts-test

# 未配置密钥也写安全报告：exit=2、BLOCKED、AUTH_INVALID、所有检查 NOT_RUN。
(cd core && uv run --offline python ../scripts/probe_jev.py --output ../.dev-data/g0-jev)

# 只在用户提供有效配置之后执行：由当前进程环境传入，命令不包含密钥值。
(cd core && uv run --offline python ../scripts/probe_jev.py --live --output ../.dev-data/g0-jev)

# 全部真实检查通过后，显式发布四份录制及 manifest；拒绝覆盖已有录制目录。
(cd core && uv run --offline python ../scripts/probe_jev.py --live --record-fixtures --output ../.dev-data/g0-jev)
```

`--live` 是联网的必要条件；`SENTINEL_OFFLINE=1` 优先禁止真实路径。HTTP 与 SDK 复用配置端点和同一密钥，不读取其他项目配置、历史聊天或钥匙串。普通 pytest 只用 MockTransport；MockTransport 或其挂载即使带 `live=True` 也不会得到 PASS 或发布录制。

完整探针依次执行 models、9 个问题的 E1、20 次独立五题小请求、10 组打包与逐条对比、5 个中文逻辑样例、10 个句子定位样例及 SDK 直连。默认共 68 次 HTTP 请求（models 1、E1 1、延迟 20、打包/逐条 30、中文 5、证据 10、SDK 1），429 的第二次尝试另计。没有并发或额外压测。

延迟用注入的 `clock` 计算，p50/p95 使用最近秩；不足 20 次记 INCOMPLETE。token 样本记录 JSON UTF-8 解码后的 Unicode 字符数、`ceil(chars / 3.5)`、实际 input_tokens、绝对和相对偏差。打包保留原 t1/t2 编号并比较全部 8/9 个概率，差值超过 0.20 写 pack_review=REQUIRED，交 S-02 人工复核。

中文结果和证据结果明确保留人工复核 PENDING。证据用 S-01 的 `split_sentences`、Unicode 码点偏移、并列取首句及低于 NO 时整段回退，报告 10 个独立样例的命中率及 0.80 门槛。这些标签是本探针的虚构样例人工参考标签，不是外部评测金标准。额外检查 E1 已完成减持、计划/撤销未发生和对抗段落低 relevant；不使用文档中的示例概率构造模型结果。

## SDK 0.7.5 的本机证据

已通过锁定安装源码和离线 wire 测试核实以下接口，真实账号行为仍未验证：

- `typesafe_sdk.TypeSafeClient` 的实际构造参数包括 api_key、model、retry、timeout、headers、transport、http_client、base_url、compression；transport/http_client 使用 **httpx2**，不能把 httpx.Client 直接传入。
- `base_url` 使用 origin，SDK 在 transport 中拼接 `/v1/systemone`；model 可由构造默认，也可在 `system_one(model=...)` 覆盖。测试实际断言 URL、请求授权和序列化模型，不从博客推断。
- 使用导出的 `Noul` / `NoulCriteria`；响应读 `answers[name].noul`、`usage.input_tokens`、`model`；raw_http_response 可读取实际响应。探针再校验键完整、有限概率、正整数 input_tokens、非负整数 output_tokens 和模型严格相等，丢弃自由文本及额外字段。
- 异常均从 `typesafe_sdk` 导出，定义在 `_core/errors.py`。离线测试核实 401 AuthenticationError、403 PermissionDeniedError、429 RateLimitError、5xx InternalServerError 的 status、headers、body、request_id。坏响应及模型不符同样失败。
- SDK request_id 的实际头是 `x-typesafe-request-id`。探针还支持 x-request-id、request-id、cf-ray、body request_id/id；缺失时通过 sharedclock 或注入 clock 生成 local-ULID。
- SDK `max_retries=2` 是首次以外再试两次；`backoff_max=5` 不会限制 Retry-After。探针使用 `RetryPolicy(max_retries=0)`，自己只对 429 做总共两次尝试，Retry-After 夹到 0..5 秒，sleep 可注入；401/403 不重试。
- SDK 原始正文 debug 日志可能包含回显；探针执行期间禁用传输日志并在结束后恢复原 logging 设置。输出仅保留白名单诊断。HTTP 客户端的服务端 cookie 在下一次请求前清空。

源码位置（安装后可重查）：`core/.venv/lib/python3.12/site-packages/typesafe_sdk/__init__.py`、`_core/client/sync/client.py`、`_core/retry.py`、`_core/errors.py`、`_core/endpoints.py`、`_core/transport.py`、`_core/response_types.py`、`_core/logging.py`。后续路径均相对于同一个 typesafe_sdk 包目录。

## 安全与失败交付

报告含原 HTTP status、来源 request-id、规范 Content-Type、重试等待及最多 200 字的响应类型/长度/分类摘要；不保存错误原文或请求正文。响应模型、日期及 request-id 有格式约束，避免自由文字回显。结构化报告和 cassette 清除敏感字段、递归替换已加载密钥及敏感文字；写前拒绝残余敏感内容和非有限 JSON 值。目录 0700、文件 0600，拒绝目标文件符号链接。

录制请求只来自脚本内虚构公司；响应只保存已验证的 Noul/model/usage。录制在所有真实检查完成后，先在临时目录完整序列化，再一次发布整个目录；错误、中途失败、缺配置或离线成功均不发布。manifest 保留真实请求 SHA256、模型、注入时钟的录制时间和问题集版本。serializer 单元测试产生的人工数据只位于 pytest 临时目录，不能当成模型录制。

缺配置实跑已得到 exit=2、status=BLOCKED、reason=AUTH_INVALID、http_status=null、attempts=[]、fixtures_written=[]。临时报告位于 `/tmp/g0-jev-n10-20261103/g0-jev.json`，不是仓库成功 fixture。

## 验证结果

- 先失败：实现文件不存在时，初始 26 个探针测试全部失败；随后实现并补充接口、安全和原子发布回归。
- 探针：34 项离线 pytest 测试，包含规格 §8.1 七项及缺 key、伪成功、模型不符、密钥注入回显、部分中途失败、样例数量、SDK 异常与实际 wire。
- ruff check/format 与探针严格 mypy：通过。
- 新 scripts-test 门禁使用 uv core pytest，正常顶层导入，不跳过、不动态导入规避依赖；230 个测试通过（196 个既有测试 + 34 个探针测试），另有 4282 个 subtests 通过。
- 最终 `scripts/check.sh`：15 个步骤通过、0 失败、2 个既定跳过；core 1264 测试、web 1 测试通过，Python/core 和前端 lint/type、Rust fmt/clippy、文档及平台隔离检查通过。原门禁的宿主 Python 导入问题已由用户授权前置改为锁定 runtime。
- 两个既定跳过分别是尚未存在的 generated-ts 脚本、需要显式 `--e2e` 的 E2E；没有跳过任何探针测试。Windows 真机、GUI E2E 和真实模型网络调用未执行。

## 交给主 agent 的同步点与未验证项

1. 用户指定探针问题集为 `qs-2026-11-02.2`，但本基线 docs/06 §3.1 仍声明 `.1`，S-02 的 questions.py 尚不存在。探针逐字保留 §3.3 五个独立问题并按用户指令标 `.2`；建议主 agent 同步规范或提供 `.2` 的权威模板差异。此包没有修改总规范或自行冻结问题集。
2. G0 规格 §6.4 的探针问题快照与 docs/00 的“问题文本只在 questions.py”存在启动期所有权矛盾；本包按用户授权的探针写集实现局部快照，后续 S-02 接管权威定义，不改他人文件。
3. 真实端点、账号支持模型、真实 HTTP/SDK 行为、实际 20 次延迟/token 偏差、打包选择、中文结果、证据命中率及 pricing effective_from 均未验证。models 响应可报告 release_date，但 release_date 不能被冒充为计费生效日；pricing 保留 TODO-VERIFY(G0-JEV)。
4. S-02/S-03 只可消费已核实的 SDK 源码接口和离线行为；真实闸门 BLOCKED，不解除 TODO-VERIFY、不冻结实测定价/阈值、不解锁真实调用验收。人工复核和闸门结论由主 agent 更新 decisions.md。
5. 本包没有 push、merge、切 main、创建 worktree、修改依赖、自动知识库写入或个人日志写入。

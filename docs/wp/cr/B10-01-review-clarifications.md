# B10-01 主 agent 审核与接口澄清

- 状态：主 agent 已批准，适用于 Mac 10 包批次。
- 依据：用户要求每包由主 agent 检查后推送；既有 R08 已获采纳。
- 范围：保持协议字段与任务边界，修复实现前可复现的不一致。

## C-00

严格文案渲染不得猜 `retryAfterSec`、`missing`、`requestId`。码表测试提供模板所需参数，新增缺参数回归测试。对象脱敏也处理字典键。日志层可以静态依赖脱敏器，依赖规则显式覆盖，不能以动态导入规避检查。

## C-01

输入是 `BinaryIO`，直接使用 `readline`；超限行丢弃剩余内容后才能继续读下一行。内部错误编号在 `to_wire(request_id)` 注入，而非传给不存在的构造参数。验收以全部实际基线测试及关键边界为准，不以不同小节中矛盾的测试计数为准。

父进程看门狗可使用平台层；基础日志的导入不应被错误归类成业务层。线程池允许固定四个 daemon worker，shutdown 与 ping/cancel 一样由 reader 直通，保证 worker 卡住时仍能关闭。入参验证失败是 `INVALID_ARGUMENT`，handler 返回结果验证失败是 `INTERNAL`。

Pydantic 模型为 Python 内部调用允许 snake_case，但 Dispatcher 验证线上入参必须显式 `by_alias=True, by_name=False`。只有 contracts 定义的 camelCase 字段才能触发业务；非法字段必须在 handler 前拒绝，测试检查实际返回 `INVALID_ARGUMENT` 且数据库不变。结果验证与 Python 服务调用仍允许内部字段名。

## C-04

密钥先 strip 后校验，拒绝内部空白；测试不能将仅含首尾空白的有效密钥判为非法。此规则以 05 §5.2 与工作包 §6 为准。

`settings/rpc.py` 可以依赖 RPC 注册接口，反向依赖仍禁止。C-00 文案所有权缩小到公共三文件，`messages/settings.py` 归 C-04，`messages/trading.py` 归 P-04；公共初始化器由主 agent 集成，不让 worker 争用。清除密钥不清空进程内脱敏登记，避免仍在运行的旧请求泄漏；从钥匙串读取旧密钥也登记脱敏。

公共初始化器必须同时注册 settings 和 trading 的模板。验收使用真实 Dispatcher 错误响应检查邮箱、密钥、钥匙串不可用和设置损坏的文案，不只在模块内对模板调用 format；这些已知错误不得退回缺失文案兜底。

锁定 keyring 的 Mac provider 确实先 delete 后 add，异常补偿不能保证旧值安全。批准主 agent 单独实现 C-04 所属平台文件 `keyring_store.py` / `macos_keychain.py` 及其两个平台测试，worker 仅接协议和业务层，不并行编辑这些文件。默认 Mac provider 使用原子 `SecItemUpdate` / 缺失时 add；原子失败标记不得触发补偿重写。CFData、查询、属性引用全部显式释放；不使用带密钥的 CLI argv，不写用户真实钥匙串做测试。W-01 的测试所有权缩小到其两个实际 Windows 文件。

## C-03

真实 DuckDB 验证表明 cursor 事务独立，不共享未提交数据。写事务内需要读自身写入时传原 `tx`；`WriteTx.execute()` 返回受保护的自身，而非可绕过上下文 commit 的原始连接。备份必须 checkpoint，临时正文 flush/fsync 后原子且不覆盖地发布；迁移恢复也先同步再 replace。排序只按备份 UTC 时间戳，忽略版本和 label。

## C-02

WP-00 的 Mac 平台树清理只调用 `child.kill()`，会留下 uv/Python 的后代。主 agent 负责在 `platform/macos.rs` 设置独立进程组并通过 `/bin/kill` 终止该组，Rust 监督器仍只调用平台接口并负责 wait/reap。新增真实 shell + sleep 后代测试；此基础修复不计为额外工作包。平台检查只放行 C-02 测试文件单独的 `#[cfg(unix)]` fixture guard，不扩张生产代码权限。

原锁定 Tauri 2 未提供外链 opener，批准 C-02 在 WP-00 所有的 `platform/mod.rs` 与 `macos.rs` 追加方法、错误类型与 Mac `/usr/bin/open` 实现；不修改已有进程接口，不新增 crate。生产命令实际调用平台接缝，不能以占位错误通过验收。平台命令参数和注入 opener 路径都需测试。

## 本批规模例外

本批固定为十个功能包，不为满足行数而削减安全/边界/实际进程测试或增加任务计数。主审批准超过原 800 行限制的包按文件逐项检查与专项验证；C-02、C-04 标为 L。此为 B10 批次例外，不取消后续工作包默认规模限制，也不声称这些包仍可在 15 分钟内审完。

## C-06

前次审核改了 R08 的文档示例，但演示创作源仍使用“计划减持”作为已发生正例。本批批准在 `.kiro/notes/author/data.py` 修正 E1 为已完成减持，问题集升至 `.2`，在契约中保留相同 ID、模拟概率、示例名与计数，再通过生成器生成 `design/prototype/data/mock.js`。句子偏移必须随实际文本重算；额外回归检查计划与执行的区别。

主审另发现既有创作源缺少必填的分页游标和拒单 ID。批准 `.kiro/notes/author/examples.py` 补齐 `nextCursor=null` 和虚构拒单 `orderId`，并统一方法插入顺序为 `index.methods`。校验器不得用豁免表跳过结果必填字段；生成器不得硬编码交换索引中的方法。

输入 schema 必须匹配服务端“先 strip 再校验”：邮箱/失效条件空白可清除，密钥允许首尾但拒绝内部空白，长度按规范化后的 Unicode 码点计算。使用 Python 29 个空白字符的显式集合与 UTF-16/码点可兼容模式；输出 schema 仍只接受严格、已规范化的值。

标量正则的 `$` 在 Python/JavaScript 中也能匹配末尾换行之前，不能表达严格字符串结束。所有标量结束锚点改为 `(?![\s\S])`，保持金额、日期与 URL 的完整匹配意图。`check_contracts` 使用标准 JSON Schema `pattern` 搜索语义，不额外改变 `$` 的含义；回归直接验证 Python 与 Node 的结果。允许首尾空白的输入文本仍执行既定规范化规则。

## D-01

30 秒限定一次网络尝试；多次重试之间遵守最多 60 秒的 Retry-After，等待可取消。此前“总计 30 秒”与“重试等待 60 秒”的歧义在 07 §3 及 D-01 同步澄清。

保留 `max_attempts` 的 1–4 配置边界，默认仍为 3；JSON 拒绝 NaN/Infinity。缓存不可变正文配原子清单，成功发布后回收旧正文，不删正在执行的请求所持内存快照。half_open 的普通 4xx 探测失败也重新打开熔断器。

共享时钟写缓存时间，429 的 wire `retryAfterSec` 向上取整为整数；内部等待仍为浮点。标准 JSON 数字溢出也不得生成无限值。配置拒绝 bool/非有限数，并把可变退避/jitter 序列复制为 tuple，保证注册后的策略不会被调用方原地篡改。

## D-02

别名由公开行情/公司资料实际字段整理，记录来源并抽查；不得让模型凭空生成 100 条中文名。主 agent 已取得公开美股名单作为候选来源，最终候选须匹配标的与中文名，不引入真实持仓数据。

既有 `SecTickerSource(http)` 无法从通用 HttpClient 获得用户邮箱，也无法发送合规 UA。批准兼容的 keyword `email_provider`，由 C-07 注入当前设置；缺少有效邮箱时绝不请求 SEC。过滤与完整统计统一在 repository，source 保留原始行。后台刷新遇空网络列表保留旧表与旧水位，不把全市场软下线。

跨包复核发现邮箱规则不一致，且非 ASCII 邮箱无法编码进 HTTPX 的字符串 UA。批准 C-00 的纯 `domain/contact.py` 共用规则：常用 ASCII 邮箱总长 ≤120、local ≤64、dot-atom 与合法域名标签、字母 TLD 2–63；C-04 在存储前拒绝不支持的 EAI，D-02 不再另写验证器，C-06 的输入/输出 schema 同步。保持 Python 首尾空白处理和清除语义，投资文本的 Unicode 能力不变。

非空但全被过滤的网络快照同样不能把全市场下线。批准仓储 keyword `require_nonempty=False`，后台传 True，在事务前拒绝空有效集合并保留旧水位。来源 name 非空字符串，否则整批 TICKER_SCHEMA。

C-03 的五项旧测试默认执行生产目录全部迁移却固定期待 schema 1，002 使其失败。批准明确的 `DEFAULT_MIGRATIONS_DIR` 测试注入：C-03 单测使用自己的 001 副本，显式迁移目录及生产默认发现行为不变；业务/集成测试仍执行真实完整迁移集合，不能隐藏新迁移或跳过失败。

## P-01 联调契约

持仓备注按 `strip()` 后的 Unicode 码点计数，最多 200，空白可清除；`holdings.upsert.note` 的三个输入分支与这一规则一致，返回和存储备注仍限制规范化后的 200 字。

数量和成本受 `DECIMAL(18,4)` 范围约束，计算出的 `Holding.marketValue = quantity × lastClose` 不属于该存储列，可能超过 14 位整数。批准只移除计算市值的整数位上限，仍要求非负十进制字符串和精确四位小数；数量、成本与账本存储边界不变。回归覆盖最大合法数量按 1000 美元估值，以及非法精度/负数/科学计数法。

# B10-01 主 agent 审核与接口澄清

- 状态：主 agent 已批准，适用于 Mac 10 包批次。
- 依据：用户要求每包由主 agent 检查后推送；既有 R08 已获采纳。
- 范围：保持协议字段与任务边界，修复实现前可复现的不一致。

## C-00

严格文案渲染不得猜 `retryAfterSec`、`missing`、`requestId`。码表测试提供模板所需参数，新增缺参数回归测试。对象脱敏也处理字典键。日志层可以静态依赖脱敏器，依赖规则显式覆盖，不能以动态导入规避检查。

## C-01

输入是 `BinaryIO`，直接使用 `readline`；超限行丢弃剩余内容后才能继续读下一行。内部错误编号在 `to_wire(request_id)` 注入，而非传给不存在的构造参数。验收以全部实际基线测试及关键边界为准，不以不同小节中矛盾的测试计数为准。

父进程看门狗可使用平台层；基础日志的导入不应被错误归类成业务层。线程池允许固定四个 daemon worker，shutdown 与 ping/cancel 一样由 reader 直通，保证 worker 卡住时仍能关闭。入参验证失败是 `INVALID_ARGUMENT`，handler 返回结果验证失败是 `INTERNAL`。

## C-04

密钥先 strip 后校验，拒绝内部空白；测试不能将仅含首尾空白的有效密钥判为非法。此规则以 05 §5.2 与工作包 §6 为准。

`settings/rpc.py` 可以依赖 RPC 注册接口，反向依赖仍禁止。C-00 文案所有权缩小到公共三文件，`messages/settings.py` 归 C-04，`messages/trading.py` 归 P-04；公共初始化器由主 agent 集成，不让 worker 争用。清除密钥不清空进程内脱敏登记，避免仍在运行的旧请求泄漏；从钥匙串读取旧密钥也登记脱敏。

## C-03

真实 DuckDB 验证表明 cursor 事务独立，不共享未提交数据。写事务内需要读自身写入时传原 `tx`；`WriteTx.execute()` 返回受保护的自身，而非可绕过上下文 commit 的原始连接。备份必须 checkpoint，临时正文 flush/fsync 后原子且不覆盖地发布；迁移恢复也先同步再 replace。排序只按备份 UTC 时间戳，忽略版本和 label。

## C-02

WP-00 的 Mac 平台树清理只调用 `child.kill()`，会留下 uv/Python 的后代。主 agent 负责在 `platform/macos.rs` 设置独立进程组并通过 `/bin/kill` 终止该组，Rust 监督器仍只调用平台接口并负责 wait/reap。新增真实 shell + sleep 后代测试；此基础修复不计为额外工作包。平台检查只放行 C-02 测试文件单独的 `#[cfg(unix)]` fixture guard，不扩张生产代码权限。

## C-06

前次审核改了 R08 的文档示例，但演示创作源仍使用“计划减持”作为已发生正例。本批批准在 `.kiro/notes/author/data.py` 修正 E1 为已完成减持，问题集升至 `.2`，在契约中保留相同 ID、模拟概率、示例名与计数，再通过生成器生成 `design/prototype/data/mock.js`。句子偏移必须随实际文本重算；额外回归检查计划与执行的区别。

主审另发现既有创作源缺少必填的分页游标和拒单 ID。批准 `.kiro/notes/author/examples.py` 补齐 `nextCursor=null` 和虚构拒单 `orderId`，并统一方法插入顺序为 `index.methods`。校验器不得用豁免表跳过结果必填字段；生成器不得硬编码交换索引中的方法。

## D-01

30 秒限定一次网络尝试；多次重试之间遵守最多 60 秒的 Retry-After，等待可取消。此前“总计 30 秒”与“重试等待 60 秒”的歧义在 07 §3 及 D-01 同步澄清。

保留 `max_attempts` 的 1–4 配置边界，默认仍为 3；JSON 拒绝 NaN/Infinity。缓存不可变正文配原子清单，成功发布后回收旧正文，不删正在执行的请求所持内存快照。half_open 的普通 4xx 探测失败也重新打开熔断器。

## D-02

别名由公开行情/公司资料实际字段整理，记录来源并抽查；不得让模型凭空生成 100 条中文名。主 agent 已取得公开美股名单作为候选来源，最终候选须匹配标的与中文名，不引入真实持仓数据。

# F18-01 Mac MVP 闭环实施澄清

## 1. 范围与评审

2026-11-03 用户授权继续剩余 18 包：S-04、S-05、P-02、P-03、P-05、P-06、
U-02、U-03、U-04、U-05、U-06、U-07、U-08、E-01、E-02、C-07、I-01、I-02。基线为 `7c80aee`，执行分支
`codex/mac-mvp-final18`。独立 managed worktree，worker 使用用户指定
`agentrouter/gpt-6.1-sol/high`；本地提交，由主 agent 独立评审、复验后逐包发布。
不自动合并 main，不新增平台/券商/定时扫描范围，不替换依赖锁。

为保留真实边界回归，规模已批准 L：S-04 2200 行、S-05 2800、P-02 3200、P-03 2600、
P-05 4200、P-06 2800；U-02/U-05 2800、其余页面 2600、U-08 2200；
E-01 2600、E-02 2800、C-07/I-01/I-02 各 3200。实现、复制 CSS、测试均计数，
不得删测试或压缩格式掩盖超限；额外范围须提出具体 CR。只修改 owns，报告与截图另列。

## 2. 判定缓存绑定真实实体

旧键只含文本哈希，但 decision 是带永久引用的实体行且 UNIQUE(cache_key)。
两个不同逻辑、不同事件的文字相同，或逻辑内容改回旧版本时，会错误命中另一个实体的行，
使版本与证据归属失真。批准 ADR-022：在五个原成分后加入 thesis_id、thesis_version、
passage_id；本期不做跨实体语义分数共享。相同实体重复扫描仍零模型请求，文本/模型/问题集
变化仍失效。仅改未交付的 cache 算法与权威定义，不改问题文字/阈值或迁移表结构。
S-05 必须测试相同文字不同逻辑/段落以及版本改回原文不能共用 decision 行。

并发相同批的模型调用可能已消耗外部 token，不能将去重落库称为远端零计费；同实例
process_batch 串行避免重复调用，入库冲突读回已有行。缓存完整命中不调用模型；证据为空的
既存行须补合法整段/标题或受预算控制的证据，不能成功返回无证据代表。
预算按 06 的 used + reserve_tokens(raw) 与上限比较，没有另一个 90% 阈值。
已经提交判定后取消证据仍保留该第一事务，批不成功；重试补证据，不重新计算已有评分。

## 3. 原生引擎与外部闸门

前批真实静态 LOAD 与本地函数已通过；S-04 可加载这份经过哈希核对的扩展，不因未进行
真实模型推理而硬编码所有 load 失败。真实非 NULL 推理仍 BLOCKED，最终 M-8 不能通过。
扩展从 `SENTINEL_JEVDB_PATH`/明确配置路径注入；允许显式可选 HTTPS endpoint，沿用
G0 的安全完整地址转 `/v1/` 前缀规则，不将 gateway 密钥发往默认官方域名。
查询只计算 wanted pair：wanted 必须在概率调用之前约束实体组合，不先评分笛卡尔积再过滤。
上游全文不得拷入 public 仓库；单测响应与 UDF 替身明确 synthetic。

## 4. 服务与所有权补齐

P-05 可增加 trading 的 initializer/models/rpc，自有 ledger 中以受保护 tx 实现 D-04
未实际提供的价格查询 helper；不要伪造市场服务现有接口或修改 D-04。写后查询必须用原 tx，
整次 advance 同事务，备份成功才 reset。缺下一个交易日行情不能跳到未来日期成交。
P-06 本包创建 011，保留零方差与 Decimal/小数真实持仓数量；年化 252。
P-02 可增加 scan initializer/models/rpc/passages tests，构造函数显式注入设置/持仓 provider，
不反向依赖 app；同市场运行互斥，水位不掩盖失败/预算 pending 的重试。
风险、扫描、清单、语义中文 messages 分配给对应 worker；公共注册由主 agent 完成。

## 5. 前端与组合根

每页 owns 对应 i18n/zh-CN/<页面>.ts；不编辑 common/index。页面 default export 能被
现有 RouterView 自动加载，页面与 FeedbackHost 只消费 app.store 的 client/bootstrap，
不自行另建 RPC 客户端。U-08 可在 UI 基础已验收后独立开发，不等待 U-02 实现，事件合同
`sentinel:toast` 已存在；不修改 rpc/，生产挂载由主 agent/C-07 集成处理。
沿用 Quiet Ledger 原型，不重设计。提供真实 browser fixture 陈列与回归，生产路由禁止
仅因 hash state 参数就替换真实数据；模拟状态只在 VITE_RPC=mock/测试入口启用。
Unicode 偏移按码点，不按 UTF-16 code unit；focus、旧请求覆盖新请求、卸载清理必须测试。

组合根启动无有效 key 可浏览/配置，但扫描不可伪装可用；保存/清空 key、更改引擎/预算后
下一次调用必须消费当前配置，不要求用户重启。SDK/JEVDB 连接按配置版本关闭重建或通过
显式 provider 解析，任何后台扫描期间重配置须有可见冲突/取消规则。
无默认自动扫描。演示数据全部虚构、显式标记，与真实实体冲突时报错；清理只删除演示集合。

## 6. 验收诚实边界

I-01 真实核心进程 + 前端 RPC，I-02 离线演示/安全检查可推进；真实 JEVDB模型和 SEC
外部调用需要有效本地配置。缺配置输出 BLOCKED/NOT_RUN 与证据，不将 mock、NULL 或
未启用 GUI E2E 计为通过。最终报告同时给可演示开发闭环和正式 M-1 至 M-8 的真实状态。

## 7. 扫描发现、重试与日期

首次无水位线按完整配置回看 7 天，不被 72 小时上限缩短；72 小时仅针对已有陈旧水位线。
explicit_from 超过 30 天或晚于 now 是 INVALID_ARGUMENT，不静默 clamp。市场水位线在
所有本次可扫描标的的披露列表均完整获取后才推进，任一列表失败不推进；已提交批不撤销。
水位语义是列表覆盖，不能代表所有模型成功。下一次运行主动并入最近 30 天旧失败/预算 pending
事件，先恢复 fetch_failed 文件再判定；成功的缓存不重算。fetch_failed 不得作为零段 succeeded，
正常 title_only 则判定标题段落。旧批只是历史，新的重试批成功后不再让旧失败无限重发现。
recover_on_startup 同时恢复 queued/running，防止崩溃前 queued 永远挡住新扫描。

## 8. 演示日历与评测来源

本地已验收日历实算：2025-10-01 至 2026-10-30 有 273 个交易日，不是 260。
演示保持 6×260=1560 行，实际起点改为 2025-10-20、终点 2026-10-30；模拟账户初始
日期及订单必须使现场推进 2026-10-29 → 2026-10-30 有行情，不假设截止后 11-02 有价。
清除演示只删登记实体；模拟账户/逻辑用户操作生成的后续行须由可追溯演示根识别，否则清理
会残留引用，不能删除任意真实数据。载入前计数/hash/schema校验，事务内校验结果再提交。

E-02 可交付功能性人工编写 synthetic 标注/概率 fixture，必须在 manifest/report 明确其
不是真实模型录制，也不是双人独立人工标注。没有两名真实标注者时不得伪造 annotator 或
adjudicated/κ 证据；功能 replay 报告能计算指标，但不宣称泛化准确率、模型实测或省钱优势。
正式人工标注与真实 cassette 另列 NOT_RUN。F1 0.80/语言差 0.05 为 v1/G2 指标，MVP-0
M-5 只要求可重放评测报告；保留显式 --gate 可选实验，不作为默认 MVP-0 发布硬阈值。
评测直接消费已交付 engine/classify，不假定 S-05 存在 load_pipeline 等虚构接口。


E-02 可以在已验收 engine/问题集/分类基础上先行做数据校验与功能 replay；它不修改 S-05，真实流水线联测在 S-05 主审后补齐。

## 9. 当前配置与运行中更改护栏

主 agent 为 C-04 register 补充可选 EngineSnapshot provider 和 before_change callable，
保留原 snapshot 参数兼容。bootstrap/testConnection 每次使用实时引擎快照；设置/密钥更改
前执行注入护栏，扫描中返回 CONFLICT，不能改掉运行中凭据。组合根必须注入实际 ScanService
互斥检查及当前配置引擎 resolver，不能仅用启动时 snapshot。主审 3 个先失败回归验证动态
切换、清空 key、连接测试及护栏拒绝后 settings/key 不变；修补不新增 RPC 方法或 wire 字段。

SettingsService 可选 allowed_domains provider 用于披露实际 gateway 域名，默认仍是原 5 项。
组合根在显式 endpoint 配置时将第一项模型域名替换为经过安全解析的当前 hostname，不增加
可编辑域名权限，不修改默认常量；用户在设置页看到的发送目标必须与真正配置一致。
U-07 的校验上限与 C-04/机器契约保持一致：budget 10000..50000000，邮箱 120 字符。

主 agent 给 RouterView 增加可注入 pageModules、Application 可注入测试 view，默认仍加载
真实业务页；U-00 的 placeholder/router 与 client 生命周期测试明确使用隔离 fixture，不能
因为业务页已经交付而失败，也不能把旧任意 app.bootstrap 响应当作所有业务方法的响应。
另加实际业务页替代 placeholder 的路由焦点回归，不修改页面的生产发现机制。

未配置 key/email 只阻止新扫描，不能隐藏已有缓存的 pending/uncertain/processed 或证据。
尤其 demo.load 后 bootstrap 默认仍未配置，今日页必须可读预置 3 条 pending/1 条 uncertain，
在配置横幅下保留列表；空清单才使用配置空状态。清空 key 后同样保留历史结果与本地页面。

P-03 可先对权威 006/007/008 DDL与稳定机器契约独立开发，不依赖 ScanService 实现；测试仅临时库、未交付 DDL 按权威字节搭建明确fixture，最终与 S-05/P-02 联测不能省略。E-01 测试移入 core/tests/unit/demo/，避免默认 testpaths 只扫 tests 而遗漏生产包内的单测。

## 10. 主审的原生错误、缓存与风险事务修正

S-04 mapper 返回 SentinelError 公共基类，非上下文的 400/413/422 用 INTERNAL/INVALID_REQUEST，
auth/rate/timeout 保持独立且无原文回显；secret_provider 的基础 SentinelError 保留分类，
不能把系统钥匙串不可用误报为缺 key，读到的 key 必须注册脱敏。原生固定 pin 不支持 NOUL
criteria 透传，S-04 只能使用 instructions；其差异必须明确列入真实语义等价未验证项，
不得通过改问题文本伪造同等。是否改原生桥另立显式适配与产物验证，不夹带改依赖。

S-05 缓存行 relation 与 headline 必须匹配同一 Probabilities 的 classify/headline，
不是仅验证枚举/范围；created_at 读出补 UTC。模型用量归调用开始的 UTC 日期，跨午夜
返回仍记开始日；下一次证据请求属于新的日期。已完成调用的缓存去重不冒称零远端计费。

RiskService 在单一 read snapshot 中获取输入，退出读上下文后进行 NumPy/JSON，最后
短 write 只插入审计；审计输入 SHA 和矩阵保证其可复现，不为计算过程长期占住写锁。
行情终点为共同可用原 close 的最近日，min(latest) 的内洞可回退到共同日，不能删除权重。
收缩/奇异阈值拒绝 bool 和非数值。数值样例与零方差资产保留规则不变。

## 11. UI 生产反馈与演示回放推进

主审在 Application 的既有 AppShell 内挂载一次 FeedbackHost，createRoot 采用其安全回调，
onCoreRetry 复用原 retry/startApp 新客户端流程。AppShell.globalFeedback 模式禁用旧离线
横幅，保留独立 shell 兼容；反馈同时参考 dataStatus.offline，最终组合只一条离线提示。
U-00 placeholder 与生命周期 fixture 不随业务页面交付而改变输入语义。

模拟账户没有持仓或历史订单时，如果下一交易日全库具有 US instrument 的行情仍可推进
现金回放；否则 DATA_INSUFFICIENT。已有 involved 集合仍要求至少一个相关标的目标日行情，
不得以非 US 或未来 D+2 数据伪造可用。空账户不能永久无法前进（P-05 主审新增回归）。
所有业务页面可在已有 U-00/U-01 和契约基础上并行，U-02 额外公共 hook 在它主审后复用，
不复制未交付代码；真正共享通知和事件订阅的组合回归由主 agent 统一补齐。

## 12. 全量测试加载

S-05 与 D-01 均拥有不同目录的 test_cache.py；默认 pytest prepend 模式将其作为同名
顶层模块导入而发生 collection mismatch。主审将 core 的 addopts 改为 importlib 模式，
保留全部文件、testpaths、测试名与回归数量，不删缓存或排除测试来制造通过。
相应跨测试引用改为 tests.unit.* 包限定导入。D-03 的 decision 两列测试占位在真实
006 到来后移除，以实际判定 DDL 插入显式 synthetic 引用保护行，不改生产抓取逻辑。

## 13. 破坏性操作的公共备份互斥

P-05 reset 需要跨备份和删除的同一路径共享互斥，不能直接引用 Database._gate。
主审为 C-03 增加 exclusive() 公共上下文：只持路径共享 RLock，不暴露原始连接或事务；
拒绝从活动读写上下文进入，内部允许依次 read/backup/write。五个先红回归覆盖跨句柄
阻塞直到整个序列结束、备份内容、异常释放、事务嵌套及未打开数据库。
P-05 必须改用公共方法；依旧先确认、成功完成备份后才开始删除事务。

paper.createAccount.initialCash 的输入机器契约限定正数、整数最多 14 位、小数最多 4 位，
与 DECIMAL(18,4) 和实际 Python validator 一致；不能接受输出与数据库无法容纳的 15 位
整数。两个先红 contract 回归验证边界；原示例、方法数量、生成客户端字段保持不变。
Decimal 隔离测试分别以干净及已有 flags 执行，断言调用方 flags 原样保留，而非假定
全量测试进程的全局 Decimal flags 总为空；不让业务函数清除调用方历史状态。

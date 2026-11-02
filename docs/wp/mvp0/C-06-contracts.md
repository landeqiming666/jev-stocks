---
id: C-06
title: 契约文件与原型数据生成
phase: mvp0
platform: shared
lane: core
deps: [WP-00]
size: M
owns: [contracts/, scripts/gen_proto_mock.py, scripts/check_contracts.py, scripts/tests/test_contracts.py, .kiro/notes/author/data.py, design/prototype/data/mock.js]
appends: []
stubs: []
---

# C-06 契约文件与原型数据生成

## 0. 一眼看懂
- **目标**：把 [05] §4–§6 的 40 个方法、92 个示例、7 个通知和 15 个错误码固化成 `contracts/`，并提供生成原型 mock 与校验契约的脚本。
- **完成后解锁**：C-05、U-00、U-01–U-08；前端类型、mock 和原型共用同一份示例。
- **预计规模**：JSON 约 1,900 行，两个脚本约 430 行，一个 unittest 文件约 260 行；不新增依赖。

## 1. 背景与边界

### 1.1 为什么需要它
原型里的示例、前端 mock 和后端参数模型如果各自维护，页面状态会先漂移，最后才在联调时发现字段不一致。C-06 把示例固化为机器可读契约，并让 `mock.js` 成为可重复生成的产物，而不是手改的文件。

### 1.2 范围内
1. `contracts/index.json`：协议版本、40 个方法和 7 个通知的顺序表。
2. `contracts/types.schema.json`：公共类型 JSON Schema。
3. `contracts/errors.json`：15 个错误码、retryable 和 reason。
4. `contracts/notifications.json`：7 个通知的 schema 与示例。
5. `contracts/methods/<方法名>.json`：40 个方法文件，参数/结果 schema、owner、timeout、错误和示例。
6. `scripts/gen_proto_mock.py`：从契约写出 `design/prototype/data/mock.js`，并支持 `--check`。
7. `scripts/check_contracts.py`：只用标准库的最小 JSON Schema 校验器。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 前端 RpcClient、TypeScript 类型和 mock 场景 | C-05 |
| RPC 服务端、业务处理器和数据库 | C-01、C-03 及各业务包 |
| 修改 `design/prototype/` 的页面代码或示例正文 | 不改；生成物只写 `data/mock.js` |
| 新增契约字段或改变示例语义 | 变更申请；C-06 只固化已有设计 |
| 引入 `jsonschema`、网络校验或远程 schema | 禁止；脚本兼容 Python 3.9 标准库 |

本批主 agent 批准的例外见 [B10-01](../cr/B10-01-review-clarifications.md)：为落实已采纳的 R08，修正创作源 E1 为已完成减持，问题集版本升为 `qs-2026-11-02.2`，再重生成 mock。现有 92 个示例、ID、模拟概率和字段顺序不变；逐字节比较以修正后的创作源与 mock 为准。

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [05-接口契约.md](../../05-接口契约.md) | 4 公共类型、5 方法清单、6 通知、11 `contracts/` | 权威字段和方法表 |
| [03-界面设计规范.md](../../03-界面设计规范.md) | 6 页面状态总表与契约示例名 | 示例名必须覆盖的状态 |
| [09-测试与评测.md](../../09-测试与评测.md) | 4 契约测试、5 安全与隔离、6 端到端 | 示例、错误和校验规则 |
| [10-协作与工作包规范.md](../../10-协作与工作包规范.md) | 4.2 D1–D10、5 模板 | 本文件的详细程度 |

## 3. 前置条件
- WP-00 已合并：`scripts/check.*` 和 Python 3.9 标准库环境可用。
- 现有 `design/prototype/data/mock.js` 与 `.kiro/notes/author/examples.py` 是示例唯一来源；C-06 完成前不得手改它们。
- 前端尚未实现，C-05 依赖本包的 `contracts/`；本包不依赖 C-05。
- `contracts/` 当前不存在；本包第一次创建全部目录。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `contracts/index.json` | 新建 | 协议版本、方法/通知顺序 |
| `contracts/types.schema.json` | 新建 | 公共类型 `$defs` |
| `contracts/errors.json` | 新建 | 15 个错误码和 retryable |
| `contracts/notifications.json` | 新建 | 7 个通知 schema 与示例 |
| `contracts/methods/<method>.json` | 新建 | 40 个方法文件，格式见 §5.2 |
| `scripts/gen_proto_mock.py` | 新建 | 生成/检查 `mock.js` |
| `scripts/check_contracts.py` | 新建 | 契约结构、引用、示例校验 |
| `scripts/tests/test_contracts.py` | 新建 | §8.1 的 11 个测试 |

### 4.1 40 个方法文件
```text
app.ping app.bootstrap app.shutdown
settings.get settings.update settings.testConnection
secrets.set secrets.clear secrets.status
instruments.search holdings.list holdings.upsert holdings.archive prices.refresh
thesis.list thesis.create thesis.update thesis.archive thesis.versions
inbox.list decision.get decision.act decision.reopen
scan.start scan.cancel scan.status scan.history scan.detail scan.retryBatch
paper.accounts paper.createAccount paper.portfolio paper.order.place paper.order.cancel
paper.orders paper.advance paper.reset risk.compute demo.load demo.clear
```
每个文件名必须等于方法名加 `.json`；文件内 `method` 与文件名一致。`owner` 按 [05] §5：C-01、C-04、D-02、P-01、D-04、P-03、P-02、P-05、P-06、E-01。

## 5. 接口规格

### 5.1 脚本接口
```text
python3 scripts/gen_proto_mock.py --contracts contracts --out design/prototype/data/mock.js
python3 scripts/gen_proto_mock.py --contracts contracts --out design/prototype/data/mock.js --check
python3 scripts/check_contracts.py --contracts contracts
```
`gen_proto_mock.py` 的 `--check` 只比较，不写文件；一致时打印 `mock.js is up to date` 并返回 0，不一致时打印首个差异行并返回 1。`check_contracts.py` 成功时打印 `40 methods, 92 examples, 7 notifications, 15 errors` 并返回 0；任何结构或 schema 错误返回 1。

### 5.2 数据结构
| 文件 | 字段/结构 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `index.json` | `protocolVersion` | str | 是 | `"1.0"` | 协议版本 |
| | `methods` | str[] | 是 | 40 个，顺序按 [05] §5.10 | 方法名 |
| | `notifications` | str[] | 是 | 7 个，顺序按 [05] §6 | 通知名 |
| `types.schema.json` | `$defs` | object | 是 | 至少含 §5.3 的 34 个类型 | 公共类型 |
| `errors.json` | `codes` | object | 是 | 15 个键 | 错误码 |
| | `retryable` | bool | 是 | 与 [05] §3.2 一致 | 重试标记 |
| | `reasons` | str[] | 否 | 每个 reason 有归属方法 | 细分原因 |
| `notifications.json` | `<name>.params` | schema | 是 | object，`additionalProperties:false` | 通知负载 |
| | `<name>.example` | object | 是 | 能通过 schema | 示例 |
| method 文件 | `method` | str | 是 | 与文件名一致 | 方法名 |
| | `summary` | str | 是 | 非空中文 | 说明 |
| | `owner` | str | 是 | 合法工作包 ID | 负责人 |
| | `phase` | str | 是 | `mvp0` | 阶段 |
| | `timeoutMs` | int | 是 | 1–60,000 | 超时 |
| | `params` | schema | 是 | object，`additionalProperties:false` | 参数 |
| | `result` | schema | 是 | `$ref` 或内联对象 | 成功结果 |
| | `errors` | str[] | 是 | `errors.json` 子集 | 可能的错误 |
| | `examples` | object[] | 是 | 至少 1 个成功示例；name 唯一 | 示例 |
| | `examples[].name` | str | 是 | 方法内唯一 | 场景名 |

### 5.3 公共类型与错误码
`types.schema.json` 的 `$defs` 必须包含：`Decimal`、`IsoTime`、`IsoDate`、`Market`、`Relation`、`Engine`、`EngineChoice`、`ActionType`、`Instrument`、`Holding`、`Thesis`、`ThesisVersionItem`、`Probabilities`、`EventRef`、`Evidence`、`ActionRecord`、`DecisionSummary`、`DecisionDetail`、`DataStatus`、`Inbox`、`ScanRun`、`ScanBatch`、`PaperAccount`、`Fill`、`PaperOrder`、`Position`、`Portfolio`、`RiskResult`、`Settings`、`Bootstrap`、`EmptyParams`、`SettingsPatch`、`TestConnectionResult`、`NotificationMap`。
`errors.json` 的 15 个码必须逐字为：`INVALID_ARGUMENT`、`NOT_FOUND`、`CONFLICT`、`CONFIG_REQUIRED`、`UNAUTHENTICATED`、`ENGINE_UNAVAILABLE`、`SOURCE_UNAVAILABLE`、`RATE_LIMITED`、`MODEL_ERROR`、`BUDGET_EXCEEDED`、`DATA_INSUFFICIENT`、`ORDER_REJECTED`、`TIMEOUT`、`CANCELLED`、`INTERNAL`。`retryable=true` 只允许最后五个中的 `SOURCE_UNAVAILABLE`、`RATE_LIMITED`、`MODEL_ERROR`、`TIMEOUT`、`INTERNAL`；其余为 false。

### 5.4 生成格式
输出必须是 UTF-8、LF、无 BOM，第一行固定为：
```text
/* 由 contracts/ 的 examples 生成（scripts/gen_proto_mock.py）。请勿手改。纯 JSON，供脚本读回。 */
```
第二行是 `window.MOCK = `，中间是 `json.dumps({"examples": examples, "notifications": notifications}, ensure_ascii=False, indent=1, sort_keys=False)`，末尾是 `;\n`。`examples` 按 `index.methods` 顺序，示例名保持方法文件中的插入顺序；`notifications` 按 `index.notifications` 顺序。

## 6. 实现步骤
1. **建立索引**：从 [05] §5.10 逐字抄 40 个方法，从 §6 抄 7 个通知；协议版本写 `1.0`；不排序，保持文档顺序。
2. **建立类型 schema**：把 [05] §4 的接口逐个转成 JSON Schema；`Decimal`、`IsoTime`、`IsoDate` 用 `type:string` 加 `pattern`；可空字段用 `anyOf` 或 `type:["string","null"]`；所有对象 `additionalProperties:false`。
3. **建立 errors/notifications**：错误码、retryable 和 reason 从 [05] §3.2 与 [03] §6 抄；通知 schema 覆盖 `app.ready`、`scan.progress`、`scan.finished`、`inbox.updated`、`engine.changed`、`source.degraded`、`budget.updated`。
4. **固化示例**：从 `.kiro/notes/author/examples.py` 的 `EX` 和 `NOTIFICATIONS` 复制 92 个示例与 7 个通知；按方法分组写入 `examples`；不得改写数值、中文、字段顺序或示例名。
5. **建立方法文件**：每个文件写入 `method`、`summary`、`owner`、`phase:"mvp0"`、`timeoutMs`、`params`、`result`、`errors`、`examples`；`params.additionalProperties=false`。
6. **生成**：`gen_proto_mock.py` 读取 index，按顺序加载方法文件，构造 `payload`；`--check` 计算期望字节并与 `--out` 比较；默认不允许 `--out` 指向 `contracts/` 内部。
7. **校验**：`check_contracts.py` 先校验 index 数量/唯一性，再校验引用、schema 关键字、示例 params/result/error；最后统计 15 个错误码覆盖和 7 个通知示例。
8. **接入检查**：`scripts/check.py` 的 `generated-proto` 步骤调用 `gen_proto_mock.py --check`；本包不修改 `check.py`，由 WP-00 的步骤占位触发。

## 7. 错误与边界情况
| 情形 | 行为 | 输出/退出 |
|---|---|---|
| index 方法数不是 40 | 拒绝生成 | `check_contracts.py` 退出 1 |
| 方法文件缺失或多出 | 列出文件名 | 退出 1 |
| 未知 `$ref` | 指出 JSON Pointer | 退出 1 |
| 示例不通过 params/result | 指出方法、示例名、字段路径 | 退出 1 |
| 错误示例缺 `data.retryable` | 拒绝契约 | 退出 1 |
| 15 个错误码有未覆盖项 | 列出缺失码 | 退出 1 |
| 生成结果与 mock.js 不同 | 只读检查 | `--check` 退出 1 |
| 输出路径在 contracts 内 | 拒绝写入 | 退出 2 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_index_lists_exactly_40_methods_and_7_notifications` | `test_contracts.py` | 真实 `contracts/` | 40 和 7 |
| `test_every_method_file_matches_its_method_field` | 同上 | 遍历 40 个文件 | 0 个不匹配 |
| `test_every_method_has_one_success_example` | 同上 | 每个 `examples` | 至少 1 个 `result` 示例 |
| `test_all_15_error_codes_are_exercised` | 同上 | 全部错误示例 | 15 个码都出现 |
| `test_notifications_have_schema_and_example` | 同上 | `notifications.json` | 7 个都有两者 |
| `test_generator_matches_existing_mock_byte_for_byte` | 同上 | 临时输出与现有 mock.js | 字节相等 |
| `test_check_mode_detects_modified_output` | 同上 | 改动临时输出末字节 | 退出 1 |
| `test_additional_properties_false_is_enforced` | 同上 | 参数多 `x` | 校验失败 |
| `test_unknown_ref_is_rejected` | 同上 | `$ref:"#/$defs/Nope"` | 退出 1 |
| `test_error_example_requires_retryable` | 同上 | 删除 `data.retryable` | 退出 1 |
| `test_prototype_state_examples_all_exist` | 同上 | [03] §6 的方法/示例名 | 全部存在 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增 JSON fixture | 临时目录中复制真实 contracts 并做单点破坏 | `tempfile.TemporaryDirectory()` |
| `design/prototype/data/mock.js` | 现有原型生成物，仅作为字节比较基准 | 只读；不手改 |
| `.kiro/notes/author/examples.py` | 92 个示例和 7 个通知的创作源 | 只读；不改 |

## 9. 验收

### 9.1 命令与期望输出
```bash
python3 scripts/check_contracts.py --contracts contracts
# 期望：40 methods, 92 examples, 7 notifications, 15 errors
python3 scripts/gen_proto_mock.py --contracts contracts --out design/prototype/data/mock.js --check
# 期望：mock.js is up to date
python3 -m unittest scripts.tests.test_contracts -v
# 期望：11 tests, OK
```

### 9.2 完成清单
- [ ] 第 4 节每个文件已创建
- [ ] 40 个方法、92 个示例、7 个通知、15 个错误码全部存在
- [ ] `--check` 与现有 `mock.js` 逐字节一致
- [ ] 第 8.1 节 11 个测试全部存在且通过
- [ ] 没有新增依赖，没有手改 `design/prototype/` 或 `.kiro/`
- [ ] 已写 `docs/wp/status/C-06.md`

## 10. 给下游的交接
| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| C-05 | `index.json`、`types.schema.json`、`mock-data` 示例 | 生成 TypeScript 时只读契约，不手写示例 |
| U-00–U-08 | `design/prototype/data/mock.js` | 页面状态名与示例名必须对齐 [03] §6 |
| 所有后端工作包 | `methods/<method>.json` | 参数模型必须与 `params` 一致，错误必须在 `errors` 中 |
| 协调者 | `check_contracts.py` 与 `--check` | 改契约必须走变更申请并重新生成 mock |

# 交接说明

> 给接手的 agent 和人。读完这一页，你应该知道：现在有什么、还缺什么、按什么顺序做、怎么验证、什么不能碰。
> 交接时间：2026-11-02。此前的工作由文档作者 agent 完成；之后的工作由你们接手。

## 1. 现在有什么

| 类别 | 内容 | 状态 |
|---|---|---|
| 设计文档 | `docs/` 下 00～10、`decisions.md`、`README.md`，共约 4,970 行 | **已定稿**，`check_docs.py --strict` 0 错误 |
| UI 原型 | `design/prototype/`：7 个页面、43 个页面状态 + 今日页 6 种证据抽屉（共 49 个画面）、组件陈列页，双击 `index.html` 即可 | **已完成**，`check_proto.py` 0 问题 |
| 工作包 | 46 个已规划（看板见 [README.md](README.md)）；**46 个均已写完整文档**（满足 D1–D10） | 待派发 |
| 检查脚本 | `scripts/` 下 `check_docs.py`、`check_proto.py`、`check_contrast.py`、`gen_wp_board.py`、`proto_render.js`，共 105 个单元测试 | 全部通过 |
| 示例数据 | `design/prototype/data/mock.js`：40 个方法、92 个契约示例、7 个通知，15 个错误码全部覆盖 | 已生成；**来源是 `.kiro/notes/author/`（见第 5 节）** |
| 代码 | **没有任何产品代码**。仓库里没有 `core/`、`apps/` | 从 WP-00 开始 |

## 2. 还缺什么，按顺序

### 第 1 步：补写缺的工作包文档（已完成）

2026-11-02 已按 [10 第 4.2 节](../10-协作与工作包规范.md) 的 D1–D10 门槛补全其余 42 个工作包。下面的来源表保留作复核依据；如后续修改工作包，仍按它定位权威章节。

| 工作包 | 内容主要来自 |
|---|---|
| C-00 基础模块（`ids` `clock` `errors` `messages` `logging_setup` `security/redact`） | [00](../00-术语与约定.md) 3、4 节；[02](../02-技术架构.md) 11 节；[05](../05-接口契约.md) 3 节 |
| C-01 RPC 服务端 | [02](../02-技术架构.md) 6、7、8 节；[05](../05-接口契约.md) 1、2、7、8 节 |
| C-02 Rust 桥接 | [02](../02-技术架构.md) 6.1、6.2、8、9 节；WP-00 的 `Platform` trait |
| C-03 存储与迁移 | [04](../04-数据模型.md) 1、2、7 节 |
| C-04 设置与密钥 | [04](../04-数据模型.md) 5 节；[05](../05-接口契约.md) 5.1、5.2；[06](../06-语义判定与Jev.md) 7.2 |
| C-05 前端 RpcClient 与类型生成 | [02](../02-技术架构.md) 6.3；[05](../05-接口契约.md) 11 节 |
| C-06 契约文件与原型数据生成 | [05](../05-接口契约.md) 4、5、6、11 节；`design/prototype/data/mock.js` + `.kiro/notes/author/`（第 5 节） |
| G0-JEV / G0-JEVDB / G1-US 三个探针 | [06](../06-语义判定与Jev.md) 11 节；[07](../07-美股数据源.md) 11 节；[09](../09-测试与评测.md) 10 节；[decisions.md](../decisions.md) 附录 |
| D-01～D-04 数据层 | [07](../07-美股数据源.md)；[04](../04-数据模型.md) 3.2、3.4、3.5 |
| S-01～S-05 语义层 | [06](../06-语义判定与Jev.md) 全文；[04](../04-数据模型.md) 3.6、3.9 |
| P-01～P-03 持仓、扫描、清单 | [05](../05-接口契约.md) 5.3～5.6；[04](../04-数据模型.md) 3.3、3.7、3.8、8.1；[06](../06-语义判定与Jev.md) 7 节 |
| P-04～P-06 交易与风险 | [08](../08-模拟交易与风险.md) 全文；[04](../04-数据模型.md) 3.10、3.11 |
| E-01 演示数据、E-02 评测 | [09](../09-测试与评测.md) 9 节；[07](../07-美股数据源.md) 9 节；`.kiro/notes/author/` |
| U-00～U-08 前端 | [03](../03-界面设计规范.md) 全文；**`design/prototype/` 是实现基线**；[09](../09-测试与评测.md) 6、7 节 |
| I-01、I-02 联调与验收 | [01](../01-产品需求.md) 7、8 节；[09](../09-测试与评测.md) 11 节 |
| W-02～W-05 | [10](../10-协作与工作包规范.md) 9 节；[01](../01-产品需求.md) 8 节 Windows 验收；W-00、W-01 |

写完一批后运行：

```bash
python3 scripts/check_docs.py --strict        # 头部字段、依赖、owns 互斥、stubs 接手
python3 scripts/gen_wp_board.py               # 重新生成看板
python3 scripts/gen_wp_board.py --check       # 确认看板是最新的
```

`check_docs.py` 会在你写的工作包违反规则时报错（owns 重叠、依赖不存在、Mac 依赖 Windows 等）。工作包头部的 `deps` 必须与 [backlog.json](backlog.json) 一致；如果你认为依赖需要调整，先改 backlog 并说明理由，**不要让头部和 backlog 悄悄不一致**（生成看板时以文件头部为准）。

**建议的批次**（后面的依赖前面的，同一批内可以并行）：

1. 契约与基础：C-06、C-00、C-05、C-01
2. 存储与探针：C-03、C-04、G0-JEV、G0-JEVDB、G1-US
3. 数据与语义：D-01～D-04、S-01～S-05
4. 业务：P-01～P-06、E-01、E-02
5. 前端：U-00～U-08（先写 U-00、U-01，其余页面工作包依赖原型，可以并行写）
6. 联调与 Windows 余下：C-02、I-01、I-02、W-02～W-05

### 第 2 步：生成 `contracts/`（可与第 1 步并行，对应工作包 C-06）

`contracts/` 目前**不存在**。[05 第 11 节](../05-接口契约.md)定义了它的结构；内容来自三处：05 第 4～6 节的类型和方法表、`design/prototype/data/mock.js` 的 92 个示例、15 个错误码。要点：

- 40 个方法每个一个 `contracts/methods/<方法名>.json`，含 `params`/`result` 的 JSON Schema 和 `examples`；
- `types.schema.json`、`errors.json`、`notifications.json`、`index.json`；
- 写 `scripts/gen_proto_mock.py`：从 `contracts/` 生成 `design/prototype/data/mock.js`，`--check` 检查是否过期。**生成结果必须与现有 `mock.js` 逐字节一致**（这是验收：证明契约与原型数据是同一份）；
- 写 `scripts/check_contracts.py`（只用标准库，自带一个最小 JSON Schema 校验器）：每个示例通过自己的 schema；所有错误码都在 `errors.json`；15 个错误码每个至少出现一次；
- 契约里的示例名必须覆盖 [03 第 6 节](../03-界面设计规范.md)总表引用的每一个“方法/示例名”。

### 第 3 步：按看板派发实现

文档补齐后，协调者按 [README.md](README.md) 的看板和 [10 第 3、10 节](../10-协作与工作包规范.md)的流程派发。第一个必须是 **WP-00**，它合并之前其他实现类工作包都不能开始（探针工作包 G0-JEV / G0-JEVDB / G1-US 也依赖 WP-00，因为它们要往仓库里放脚本和录制数据）。

## 3. 开工前先做的三件事

1. **做一次初始提交**。仓库现在没有任何 git 提交，所以没有分支可建，现有成果也没有版本保护。`.gitignore` 由 WP-00 创建，现在还没有，所以**不要用 `git add .`**，按目录添加：

   ```bash
   git add docs design scripts .kiro/notes
   git commit -m "docs: baseline design docs, prototype, check scripts, handoff"
   ```

   `.kiro/notes/` 要提交：里面有示例数据创作脚本，WP-00 的 `.gitignore` 也明确不忽略它。`.kiro/backup/` 不要提交：它是旧版文档备份，WP-00 的 `.gitignore` 会列出它。
2. **确认三个外部事实**，它们决定后面的实现（详见 [decisions.md 附录](../decisions.md)的闸门记录，现在全是“待测”）：
   - 你们的 Jev 密钥能不能调用 `jev-1.14.0`；
   - 你们的网络能不能访问 SEC（`www.sec.gov`、`data.sec.gov`）和哪个行情源（课程所在网络很可能无法访问 Yahoo）；
   - JEVDB 能不能在这台 Mac 上编译（开发期失败可临时用 Jev 直连；最终验收仍硬性要求真实 JEVDB，见 ADR-018）。
3. **人工审阅一次 [06 第 3.3 节](../06-语义判定与Jev.md)的五个英文问题**。这是整个产品判定质量的来源，我写的是初稿，没有真实调用验证过。

## 4. 不要碰什么

| 不要 | 原因 |
|---|---|
| 修改 `docs/` 下已定稿的文档、`design/prototype/` | 它们是基线。发现错误或做不到，写变更申请（[10 第 8 节](../10-协作与工作包规范.md)），不要自己改。例外：新增工作包文件、`wp/status/`、`wp/cr/`、`wp/windows-matrix.md`、`wp/backlog.json` |
| 修改 `scripts/check_docs.py` 等已有脚本 | 它们有测试；改之前先读测试。WP-00 明确把这几个文件列为“不得修改” |
| 在 `design/prototype/data/mock.js` 里手改数据 | 它是生成物。改数据要改 `contracts/` 再重新生成 |
| 往 `pyproject.toml` / `package.json` / `Cargo.toml` 加依赖 | 依赖白名单在 [02 第 4 节](../02-技术架构.md)，WP-00 一次装齐，之后新增必须走变更申请 |
| 删除 `.kiro/backup/` 和 `.kiro/notes/` | 前者是旧版文档备份，后者是创作过程记录和示例数据创作脚本 |
| 在界面或文档里写“已验证” | 标了 `TODO-VERIFY(<工作包>)` 的内容都没有被验证过，必须由对应工作包实测后才能改写 |

## 4.1 已知的“没验证过”清单

这些地方我无法验证，文档里都已用 `TODO-VERIFY` 标明，**不要把它们当成事实**：

| 内容 | 位置 | 谁验证 |
|---|---|---|
| SEC 的 `User-Agent` 格式、限速、`company_tickers*.json` 与 `submissions` 的字段、`-index.htm` 页面结构 | [07](../07-美股数据源.md) | G1-US |
| 行情源的可用性、字段、条款、能否从你们的网络访问 | [07](../07-美股数据源.md) 6.2 | G1-US |
| NYSE 2025–2027 完整休市日（只有提前收盘日是核实过的） | [07](../07-美股数据源.md) 7.3 | D-04 |
| SEC 与 FINRA 监管费率和生效日期（默认写 0，标“未核实”） | [08](../08-模拟交易与风险.md) 3 节 | P-04 |
| Jev SDK 的构造参数、`model` 的传法、重试是否按文档生效 | [06](../06-语义判定与Jev.md) 2.2 | G0-JEV |
| 打包多条逻辑到一个请求是否可靠、证据句定位准确率、中文逻辑的表现 | [06](../06-语义判定与Jev.md) 3.2、5、9 | G0-JEV |
| JEVDB 在 STRUCT 输入下能否理解“第一个输入的 thesis 字段”这种指代 | [06](../06-语义判定与Jev.md) 6.4 | G0-JEVDB |
| Windows 上的 PowerShell 写法、`icacls`、`ctypes` 调用 | [W-01](mvp0/W-01-windows-platform-layer.md) | W-01 |
| DuckDB 对索引列 `UPDATE`、同事务删除再插入的具体限制 | [04](../04-数据模型.md) 1 节 | C-03 |
| Playwright 用“写入快照路径再比较”实现像素比对的具体写法 | [09](../09-测试与评测.md) 7.1 | U-01 |
| `typesafe-sdk`、JEVDB 的许可证 | [02](../02-技术架构.md) 4.1 | WP-00、G0-JEVDB |

## 5. 示例数据的来源

`design/prototype/data/mock.js` 是**生成物**，但目前的生成器放在 `.kiro/notes/author/`（Python：`data.py`、`data_more.py`、`examples.py`、`build_mock.py`），不属于仓库的正式部分。用途：

- 它是 92 个契约示例的**唯一创作来源**，C-06 的工作是把它们**固化**进 `contracts/`，之后 `gen_proto_mock.py` 反向从契约生成 `mock.js`；
- C-06 完成并通过“逐字节一致”的验收后，`.kiro/notes/author/` 就完成了使命，可以归档；
- 在那之前，如果需要新增示例（例如新页面状态），改 `.kiro/notes/author/examples.py` 然后 `cd .kiro/notes/author && python3 build_mock.py`。

## 6. 验证命令速查

```bash
python3 -m unittest discover -s scripts/tests          # 105 个脚本测试
python3 scripts/check_docs.py --strict                 # 文档：链接、锚点、文档名、状态、工作包头部与依赖
python3 scripts/check_proto.py                         # 原型：样式约定 + 渲染 49 个画面做无障碍与结构检查（需要 node）
python3 scripts/check_contrast.py                      # 令牌对比度，32 对
python3 scripts/gen_wp_board.py --check                # 看板是否最新
open design/prototype/index.html                       # 看原型
```

## 7. 一个提醒

写工作包时，**不要让“详细”变成“啰嗦”**。D1–D10 要求的是实现者不再需要做设计决定，不是把文档复制一遍。WP-00 是最大的一个（约 710 行），其余多数应在 250–450 行。每个工作包的第 1 节“边界”和第 1.3 节“明确不做”最重要——它们防止 agent 越界。

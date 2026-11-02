# 美股中文名称来源与核验

`us_zh.json` 原样采用主 agent 已抓取并完成 SEC 匹配的 237 条候选，不添加模型生成名称。每条只有 `symbol`、`name_zh`、`aliases`。237 条的 `aliases` 都为空；主名本身参与中文离线搜索。

## 来源与时间证据

- 名称来源：东方财富公开美股名单，代码取 `f12`，中文名称取 `f14`，按市值 `f20` 降序。请求参数、候选数量和原始 10 条示例保存在 `provenance.json`。
- URL 模板：<https://push2.eastmoney.com/api/qt/clist/get?pn={page}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f20&fs=m%3A105%2Cm%3A106%2Cm%3A107&fields=f12%2Cf14%2Cf13>。
- 第一页可复核地址：<https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fid=f20&fs=m%3A105%2Cm%3A106%2Cm%3A107&fields=f12%2Cf14%2Cf13>。
- SEC 核验来源：<https://www.sec.gov/files/company_tickers_exchange.json>。本包使用提供的快照，没有使用虚构用户邮箱重新请求 SEC。
- 采集时间证据：名称来源记录文件落盘于 `2026-11-02T16:02:39.563683Z`（北京时间 2026-11-03 00:02:39）；SEC 核验快照落盘于 `2026-11-02T16:26:56.661841Z`，匹配候选落盘于 `2026-11-02T16:26:56.724725Z`。这是提供文件的 mtime，可确定快照记录时间；原请求的 HTTP Date 和起止时间未提供，不能声称已经核实精确网络采集时间。

输入文件 SHA-256：

| 提供文件 | SHA-256 |
|---|---|
| `jev-us-aliases-provenance.json` | `6e06b8ad70728e7f83603b67287c0315bc08daeaa5b5680812db8eb14e7c82f5` |
| `jev-sec-tickers-alias-validation.json` | `67da093c67735ef6dd1182a5ab95040559c99456a8724b740196b7cd00e75f77` |
| `jev-us-aliases-sec-matched.json` | `6b128cce1745d2d7af6db926aee8aa24ae5a66956f36998bb4a7830fcc704d35` |

## 筛选方法与计数

1. 公开名称候选记录为 239 条，主 agent 提供的 SEC 匹配后候选为 237 条（差额 2 条；原始完整 239 条及排除代码未随当前材料提供，不能补造）。
2. 检查 SEC `fields` 恰为 `["cik", "name", "ticker", "exchange"]`，快照包含 10,423 行。
3. SEC 代码 `strip().upper().replace('-', '.')`；只取 `Nasdaq`、`NYSE`、`NYSE American`、`CBOE`。快照白名单规范代码集合有 7,672 个。
4. 逐条检查 237 条候选的代码在该集合内；检查三字段结构、规范代码唯一、中文名称非空。全部通过。本包直接重序列化候选，没有新增名称或别名。
5. SEC 只验证上市代码与交易所，不能独立认证东方财富中文译名。名称保留公开来源原有类别后缀，例如 `GOOGL=谷歌-A`、`GOOG=谷歌-C`。本包不把不同股类混成一个名称。

## 可抽查样本

以下 12 条均来自提供候选，与 SEC 快照代码匹配：`NVDA=英伟达`、`AAPL=苹果`、`MSFT=微软`、`GOOGL=谷歌-A`、`GOOG=谷歌-C`、`AMZN=亚马逊`、`TSM=台积电`、`TSLA=特斯拉`、`AVGO=博通`、`LLY=礼来`、`SKHY=SK海力士`、`WMT=沃尔玛`。

## 未验证项与资源注入

- 没有为 BRK.B 添加生产中文别名：当前候选没有该项，且没有提供其他公开名称来源。`伯克希尔/伯克希尔哈撒韦/巴菲特` 仅在规格样例测试 fixture，属于构造数据，不能当作已核实来源。
- 未独立重新访问公开网络或逐一核实 237 个中文译名；主 agent 可按来源地址抽查 10 条以上。没有额外未经核验的生产别名，也没有读取真实持仓。
- 开发仓库默认从模块文件位置定位仓库 `resources/aliases/us_zh.json`，不依赖工作目录。`InstrumentRepository(db, resource_dir=...)` 接收资源根目录，其下读取 `aliases/us_zh.json`；`alias_path=...` 可直接指定文件。二者不能同时指定。路径包含空格或中文已由测试覆盖。发布打包由 C-07 注入资源根目录。
- 资源在构造时与每次导入前严格校验；缺失、不可读、JSON 损坏、字段或别名类型错误、规范代码重复都抛 `INTERNAL`。空列表是合法的显式无别名资源；生产数量由资源验收检查要求至少 100。

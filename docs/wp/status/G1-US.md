# G1-US 执行状态

- 基线：`7b366dc7ae1a48863d8375fcc9a1a4179faf3452`。
- 代码实现、公开录制、外部闸门分别验收；当前 SEC 联系邮箱未配置，禁止本轮 SEC 请求。总闸门未通过。
- 自行编辑仅 G1-US owns 与本文件；没有 push、merge、修改 main、依赖、契约、知识库或个人日志。
- 追加用户批准的前置 `78673adf3f3a7407fa216292b0fe61ff8b2cf5a3`，本地 cherry-pick SHA：
  `2cf8fecf28539f5eb1a4a9236fc8cc6b63e0d1bf`。该共享提交带入脚本 pytest runner、其回归测试和 N10-01 §5，
  没有自行编辑上述三份共享文件。最终 G1-US 提交 SHA 由最终交接消息列出，避免报告自引用 SHA。

## CR：真实 ticker fixture 不得伪造边界行

先于实现提交给主 agent 的证据（2026-11-03）：历史文件
`/tmp/jev-sec-tickers-alias-validation.json` SHA-256 为
`67da093c67735ef6dd1182a5ab95040559c99456a8724b740196b7cd00e75f77`，
与基线 `resources/aliases/README.md` 记录完全相同。
公开来源是 <https://www.sec.gov/files/company_tickers_exchange.json>，
历史文件 mtime 为 `2026-11-02T16:26:56.661841Z`，原请求时间和 HTTP 元数据未知。
核验 10,423 行、四列字段、BRK-B 一行、OTC 2,572 行；重复 ticker 0，含空白 ticker 0。
工作包 §4/6 与 docs/07 §10 强制真实裁剪含重复和空白 ticker，与这份历史响应冲突。
请求协调者澄清：真实裁剪只选原有行；不存在的边界使用单独明确 synthetic fixture。
用户已授权该隔离方式，本包不改规范。历史复用不能称本轮 live。
`/tmp/jev-us-aliases-provenance.json` 是东方财富名单来源，不是 SEC HTTP 来源证据。

## 待验证

- SEC submissions 时间实际精度与 filing index 结构：待真实联系邮箱配置；不能依据旧三位毫秒 regex 宣称已核实。
- 行情连续性、复权语义、交易日历来源、使用条款和限速：`TODO-VERIFY(G1-US)`，仅 HTTP 可达不能通过总闸门。

## CR：实现与测试规模

首轮格式化后脚本 747 行、规定测试 138 行，共 885 行，已超过 800 行边界。
请求主 agent 接受规模调整：来源校验、低频采样、完整 provenance、裁剪、离线校验与报告均需实现，
后续仍补充回归，不通过删除测试压缩规模。最终精确行数在交接时列出。

已安装锁定 `selectolax==1.0.2` 的 `selectolax.parser` 导入直接抛 ImportError，
错误明确要求 `selectolax.lexbor.LexborHTMLParser`；采用同一已安装依赖的 Lexbor 接口，不改依赖。

## CR：本轮腾讯公开实测字段与数据范围

2026-11-03 首轮真实请求（完整 URL/时间/hash 保存到自有 `schema_observations.json`）：

- <https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=usAAPL,day,,,30,qfq>
  三次均返回 2 行，首行日期 2011-06-02，与预探针最新数据及 30 日范围不符。
- <https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=hk00700,day,,,30,qfq>
  返回 31 行，字段数集合为 6/7；第七字段是带 `cqr/FHcontent/HGcontent` 的对象，
  前六列仍是日期、开、收、高、低、量。工作包 §6 的固定六列要求无法解析实际港股响应。
- 请求协调者澄清为：允许保留来源第七字段，仅解析前六价格列；未知额外列仍拒绝。
  不猜测替换 US symbol 后缀，不把少量或陈旧行当 250 日成功。
- 首轮 A 股成交量为带三位小数的字符串。保留 Decimal，检查是否存在实际非整数，
  成交量单位没有独立核实，不宣称为股数。

## CR：负向源结论变化

2026-11-03 公开、单次、低频请求：Yahoo 429（非旧报告的 403），Stooq 404（非旧报告的 200 验证页），
东方财富 HTTP 200、`rc=0`、`data.klines` 非空（非旧报告的 `rc=102/data=null`）。
完整请求参数、时间、内容类型、HTTP Date、响应 SHA-256 和最多 200 字符摘要在 `negative_sources.json`。
只记观察 `warn`；请求协调者重新评估预探针“东方财富不可用”的结论。本包不更换主/备源或修改 docs/07。

## 代码交付

- 实现七个规定公开函数、全部 CLI 参数及 0/1/2 退出码；缺少邮箱在建 client 前 exit 2，且不写输出目录。
  真实请求不接受 example.com/org/net 占位邮箱；只读取 SEC 联系邮箱、offline 与公共 clock 配置，不读 Jev 密钥。
- SEC 支持 submissions、ticker 表、browse-edgar 与从实际 accession 导出的 index；安全 UA、429 warn/Retry-After、
  403 fail、超时/编码/字段错误有测试。没有本轮真实 SEC 请求，submissions/index 成功 fixture 保持缺失。
- 腾讯三市场三次串行采样与中位耗时；接受六列及已观察的第七 metadata 对象，未知额外列拒绝。
  Nasdaq 美元前缀、逗号分组与日期解析；价格为正且有限 Decimal，OHLC 区间、空缺、日期行序与重复检查。
  成交量按 Decimal 原值检查并报告实际小数，未核实单位或复权语义。
- 连续性五代码逐一请求并统计，不存完整行情；超过 4 个自然日的间隔只是启发统计，不能当交易日历验收。
  用户已告知主 agent 核实 NYSE 2025/26/27 日历，G1 没有重复 D-04 日历任务或伪称已用该日历复核行情。
- JSON 保留原响应形状和 `_provenance`；manifest 保留文件哈希与检查结果；offline 校验本地形状和哈希，
  从不建网络 client，成功 exit 0 只代表解析通过，报告固定 `Gate: NOT PASSED`。
- 最终实现 758 行、测试 384 行，共 **1,142 行**。超过 800 行的规模 CR 已先提出，未删除回归。

## 本轮公开录制

共 **21 次公开 HTTP 请求，0 次 SEC 请求**：首轮 18 次；修正已观察港股字段后另做三次港股复测。
均串行且请求起点至少相隔 1 秒，无高频压测。保留的本轮请求区间：
`2026-11-03T03:42:57.568519Z` 至 `2026-11-03T03:47:51.531159Z`。

| 来源/检查 | 本轮 HTTP | 实际行数 | 中位/单次耗时 | 结论 |
|---|---|---|---|---|
| 腾讯 usAAPL，30 日 | 200 ×3 | 2 | 3530 ms | fail；日期跨 2011-06-02 至 2026-11-02，不能当 30/250 日成功 |
| 腾讯 hk00700，复测 | 200 ×3 | 31 | 1621 ms | warn；6/7 字段，第七 metadata 原样保存，裁剪末 30 行 |
| 腾讯 sh600519 | 200 ×3 | 31 | 127 ms | warn；qfqday，有一次慢响应；裁剪末 30 行，复权语义未核实 |
| Nasdaq AAPL | 200 | 30 | 3634 ms | warn；MM/DD/YYYY、价格美元前缀；未核实复权语义 |
| 腾讯 AAPL/MSFT/NVDA/KO，250 日 | 200 | 各 2 | 88/127/108/7123 ms | 全 fail；不达 250 行 |
| 腾讯 BRK.B → usBRK-B，250 日 | 200 | 0 | 6772 ms | fail；空 rows，没有猜测 symbol 后缀 |
| Yahoo / Stooq / 东方财富 | 429 / 404 / 200 | 只录摘要 | 654 / 931 / 392 ms | warn；东方财富返回非空 klines |
| SEC 表历史复用 | 本轮未请求 | 原 10423，裁剪 25 | 原耗时未知 | historical；哈希核验，不能称本轮 live |

腾讯港股和 A 股实际含 2026-11-03 行；采样时当地市场仍在交易，未证明末行已收盘。
本轮小数成交量字符串的 Decimal 值均为整数，不能由此证明成交量单位。
总报告为 **required 3 passed, 14 failed**（CLI 按规格将 warn 计入 passed），总闸门未通过。
250 交易日连续性已发现不足；SEC 联系配置、复权、条款、限速与日历对照仍保持 TODO，不解锁 D-03/D-04 外部验收。

## 最终全部 G1-US 变更路径

| 路径 | 内容 |
|---|---|
| `scripts/probe_sources.py` | 探针、裁剪、报告、offline CLI |
| `core/tests/unit/markets/probe/test_probe_sources.py` | 规定十项及边界/来源隔离回归，67 项 |
| `core/tests/fixtures/markets/probe/REPORT.md` | 实际检查结论与四项 TODO |
| `core/tests/fixtures/markets/probe/manifest.json` | 模式、检查值、裁剪文件哈希 |
| `core/tests/fixtures/markets/probe/company_tickers_exchange.probe.json` | 历史 SEC 25 行，不含伪造边界 |
| `core/tests/fixtures/markets/probe/quotes_tencent_us.probe.json` | 真实仅 2 行，未补造 30 行 |
| `core/tests/fixtures/markets/probe/quotes_tencent_hk.probe.json` | 真实 30 行，保留第七字段 |
| `core/tests/fixtures/markets/probe/quotes_tencent_cn.probe.json` | 真实 30 行 qfqday |
| `core/tests/fixtures/markets/probe/quotes_nasdaq_us.probe.json` | 真实 30 行 |
| `core/tests/fixtures/markets/probe/prices_250d_summary.json` | 五代码实测统计，BRK.B 明确失败 |
| `core/tests/fixtures/markets/probe/negative_sources.json` | 三公开负向源实际结果 |
| `core/tests/fixtures/markets/probe/schema_observations.json` | 首轮真实字段与日期异常证据，不是成功全量 cassette |
| `core/tests/fixtures/markets/probe/synthetic_boundaries.json` | 独立构造的重复/空白/OTC/非法价格边界 |
| `docs/wp/status/G1-US.md` | 本状态与 CR |

前置共享提交另带入（本 G1 提交不包含）：`scripts/check.py`、`scripts/tests/test_check_runner.py`、
`docs/wp/cr/N10-01-execution-clarifications.md`。

## 测试与验收证据

- 初始化 `cd core && uv sync --frozen --offline`：锁定 43 个包，未改依赖/锁。
  全仓前端检查另用 `pnpm install --frozen-lockfile --offline` 复用 228 包，下载 0。
- 先写规定十个测试，运行 `uv run --frozen --offline pytest tests/unit/markets/probe -q`：
  **10 errors**，全部因实现文件尚不存在；随后实现，十项通过；补充回归最终 **67 passed**。
- 专项 ruff check / format、`git diff --check` 均通过。
- 实际缺邮箱 CLI：`--contact '' --out /tmp/jev-g1-no-contact` **exit 2**；该目录不存在，未请求 SEC。
- 实际 offline CLI：`SENTINEL_OFFLINE=1 ... --offline-fixtures core/tests/fixtures/markets/probe --out /tmp/jev-g1-offline`
  **exit 0，required 9 passed, 0 failed**，报告明确 OFFLINE 和 Gate NOT PASSED。
- `python3 scripts/check_docs.py --strict`：**0 错误、0 警告**。
- `UV_OFFLINE=true CARGO_NET_OFFLINE=true CARGO_TARGET_DIR=<用户指定缓存> scripts/check.sh`：
  **15 passed、0 failed、2 skipped**。Python 核心 **1331 passed**（包含 G1 的 67）；
  scripts-test 使用已批准 core pytest runner：**196 passed，4282 subtests passed**；前端 **1 passed**。
  全仓 ruff/format/mypy、前端 lint/typecheck、Rust fmt/clippy 均通过。
  两个未执行项明确为缺失的 generated-ts 与未启用 E2E；未把它们计作已验证。
- 无真实 SEC、Jev、GUI E2E、Windows 或来源高频限速验证；不把上述绿色代码门禁冒充外部闸门通过。

---
id: E-01
title: 演示数据与载入脚本
phase: mvp0
platform: shared
lane: semantic
deps: [P-03, P-05]
size: M
owns: [core/sentinel/demo/, core/sentinel/storage/migrations/012_demo.sql, resources/demo/, scripts/load_demo.py]
appends: []
stubs: []
---

# E-01 演示数据与载入脚本

## 0. 一眼看懂

- **目标**：用一套确定、离线、可一键清除的虚构数据，让六个页面在 30 秒内都有内容；同一份数据支撑 I-01、I-02 和 5 分钟演示。
- **完成后解锁**：I-01、I-02。
- **预计规模**：约 550 行，含 fixture、载入器、RPC 适配、测试；数据文件另计。

## 1. 背景与边界

### 1.1 为什么需要它
联调和现场演示不能依赖实时 SEC、行情或 Jev。演示数据必须同时覆盖推翻、削弱、支持、待确认、关注、空持仓、模拟交易和风险样本，并且能证明“清除后不残留”。

### 1.2 范围内
1. 6 家虚构公司的持仓、6 条逻辑、6 份披露、12 条判定、1,560 行合成行情。
2. 1 个模拟账户、2 笔订单、2 条处理记录、1 条风险审计记录和 1 份扫描历史。
3. `demo.load` / `demo.clear` 的纯本地实现，以及 `scripts/load_demo.py`。
4. 所有演示行登记在 `demo_row`，只允许 `demo.clear` 删除登记过的行。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 真实 SEC 下载、行情刷新或 Jev 调用 | D-03、D-04、S-03 |
| 修改任何业务表 DDL | C-03 按 [04](../../04-数据模型.md#312-012_demosql--e-01) 建表 |
| 新 RPC 方法或新字段 | 只实现 [05](../../05-接口契约.md#59-演示数据2) 的 `demo.load`、`demo.clear` |
| 演示页面和设置页按钮 | U-03～U-07 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | 1.4 虚构示例数据、3.1 业务 ID、4 时间与金额 | 固定公司、ID 与数值格式 |
| [04-数据模型.md](../../04-数据模型.md) | 3.3、3.4、3.6～3.12 | 要写入的表和主键 |
| [05-接口契约.md](../../05-接口契约.md) | 5.9 演示数据、3.2 错误码 | 两个方法的输入、返回和错误 |
| [01-产品需求.md](../../01-产品需求.md) | US-15、第 8 节 M-2 | 离线与可清除验收 |
| [09-测试与评测.md](../../09-测试与评测.md) | 3 测试数据规则、6 端到端场景 | fixture 限制与 E2E-15 |

## 3. 前置条件

- P-03 已提供 `inbox.list` 所需的 `decision`、`thesis_action` 与 `v_last_action`。
- P-05 已提供 `paper_account`、`cash_ledger`、`paper_order`、`fill`、`position`、`equity_snapshot` 的统一写入规则。
- C-07 的组合根中已有一个 4 行适配器 `core/sentinel/app/methods/demo.py`，只从 `sentinel.demo.rpc` 导入 `register_handlers`；该文件属于 C-07，E-01 不得修改它。
- C-03 提供迁移执行器；`012_demo.sql` 由本包创建，内容逐字取自 [04](../../04-数据模型.md) §3.12。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `resources/demo/manifest.json` | 新建 | 版本、计数、文件哈希与预期页面摘要 |
| `resources/demo/instruments.json` | 新建 | 6 家虚构公司与别名 |
| `resources/demo/portfolio.json` | 新建 | 5 条持仓、6 条逻辑版本、2 条处理记录 |
| `resources/demo/filings.json` | 新建 | 6 份披露、文件、段落和 12 条判定 |
| `resources/demo/prices.csv` | 新建 | 6 × 260 行日线，`source=demo` |
| `resources/demo/paper.json` | 新建 | 账户、现金流水、订单、成交、持仓、权益快照 |
| `core/sentinel/demo/__init__.py` | 新建 | 导出 `DemoService`、`load_demo`、`clear_demo` |
| `core/sentinel/demo/service.py` | 新建 | 载入、清除、冲突检查与计数 |
| `core/sentinel/demo/loader.py` | 新建 | 按依赖顺序写入并登记 `demo_row` |
| `core/sentinel/demo/rpc.py` | 新建 | `METHODS` 中两个处理器的参数/结果模型 |
| `core/sentinel/storage/migrations/012_demo.sql` | 新建 | 逐字复制 [04](../../04-数据模型.md) §3.12 的 `demo_row` 表 |
| `core/sentinel/demo/tests/test_{loader,service,rpc}.py` | 新建 | §8.1 的单元测试 |
| `scripts/load_demo.py` | 新建 | 命令行载入/清除，输出 JSON 摘要 |

## 5. 接口规格

### 5.1 公开接口
```python
class DemoService:
    def __init__(self, db: Database, resources: Path, clock: Callable[[], datetime]) -> None: ...
    def load(self) -> DemoCounts: ...
    def clear(self) -> None: ...
    def status(self) -> DemoStatus: ...

def load_demo(db: Database, resources: Path, clock: Callable[[], datetime]) -> DemoCounts: ...
def clear_demo(db: Database, clock: Callable[[], datetime]) -> None: ...

def demo_load(params: DemoLoadParams, ctx: RequestContext) -> DemoLoadResult: ...
def demo_clear(params: DemoClearParams, ctx: RequestContext) -> dict[str, bool]: ...
def register_handlers(registrar: HandlerRegistrar, service: DemoService) -> None: ...
```
`load` 的写操作在一个 `Database.write()` 事务内完成，失败全回滚。`clear` 同样单事务，按 §6 的逆序删除，重复调用返回成功且计数为 0。线程安全由数据库写锁保证；资源文件只在构造时读取一次。

### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `DemoCounts` | `instruments` | int | 是 | `6` | 标的数 |
| | `holdings` | int | 是 | `5` | 持仓/关注数 |
| | `theses` | int | 是 | `6` | 有效逻辑数 |
| | `events` | int | 是 | `6` | 披露数 |
| | `decisions` | int | 是 | `12` | 判定数 |
| | `prices` | int | 是 | `1560` | 行情行数 |
| `DemoStatus` | `loaded` | bool | 是 | 由 `setting.demoDataLoaded` 与登记簿共同决定 | 是否已载入 |
| | `rows` | int | 是 | ≥ 0 | `demo_row` 行数 |
| `DemoLoadResult` | `loaded` | bool | 是 | 固定 `true` | 成功标志 |
| | `counts` | DemoCounts | 是 | 上表精确值 | 设置页展示 |
| `DemoLoadParams` | — | pydantic BaseModel | 是 | `extra="forbid"`、无字段 | `demo.load` 空参数 |
| `DemoClearParams` | — | pydantic BaseModel | 是 | `extra="forbid"`、无字段 | `demo.clear` 空参数 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `DEMO_VERSION` | `"1"` | `manifest.json` | 数据版本；变更必须全量重录 |
| `DEMO_START` | `2025-10-01` | `prices.csv` | 首个共同交易日 |
| `DEMO_END` | `2026-10-30` | `prices.csv` | 最后一个共同交易日 |
| `PENDING_COUNT` | `3` | `manifest.json` | 今日页未处理条目数 |
| `UNCERTAIN_COUNT` | `1` | `manifest.json` | “系统拿不准”条目数 |
| `DEMO_SCAN_ID` | `01K00000000000000000000001` | `portfolio.json` | 演示扫描运行 ID |

## 6. 实现步骤

1. 校验 `SENTINEL_OFFLINE` 不等于 `0` 也不影响本包；本包从不创建 HTTP 客户端。
2. 读 `setting.demoDataLoaded`；为 `true` 时抛 `CONFLICT`，`data.reason="ALREADY_LOADED"`。
3. 在只读事务中检查 `holding`、`thesis`、`paper_account` 是否存在 `source/is_demo` 之外的任何行；存在则抛 `CONFLICT`，`reason="REAL_DATA_PRESENT"`，禁止混入真实账户。
4. 解析全部 JSON/CSV；校验总数、主键唯一、`ZZ*` 代码与 SEC 标的表不冲突（有缓存表才查，无缓存跳过）、价格日期严格升序且每天 6 行。
5. 开启单事务，按 `instrument → holding → thesis → thesis_version → event_doc → event_file → event_passage → decision → thesis_action → scan_run → scan_batch → price_daily → paper_account → cash_ledger → paper_order → fill → position → equity_snapshot → risk_run` 顺序插入。
6. 每插入一行，同步写一条 `demo_row(table_name, pk_json, inserted_at)`；`pk_json` 用排序后的键序列化，禁止空白差异。
7. 写 `setting` 的 `demoDataLoaded=true`；该行也登记到 `demo_row`，清除时恢复为 `false` 而不是删除设置键。
8. 提交后重新查询六类计数，任一与 `manifest.json` 不符则记录 `INTERNAL`，但数据已提交，必须在状态文件列为缺陷并停止发布。
9. `clear` 读取 `demo_row`，按第 5 步的逆序执行 `DELETE`；`setting` 留到最后改为 `false`；随后删除全部演示登记行。
10. `scripts/load_demo.py` 先获取 `platform.file_lock(data_dir/"core.lock")`，被占用时退出码 2；支持 `--clear`、`--dry-run`、`--json`。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 已载入再次载入 | 不写库 | `CONFLICT` / `ALREADY_LOADED` | `error.CONFLICT`；设置页映射“演示数据已经载入” |
| 数据库已有真实持仓/逻辑/账户 | 不写库 | `CONFLICT` / `REAL_DATA_PRESENT` | `error.CONFLICT`；设置页说明先清空或使用独立数据目录 |
| fixture 计数不一致 | 全回滚 | `INTERNAL` | `error.INTERNAL`，带 `requestId` |
| `demo.clear` 时登记行已被手工删除 | 跳过并继续 | — | 返回 `{ok:true}` |
| 清除后仍有 `source=demo` 行 | 回滚并在日志列出表名 | `INTERNAL` | `error.INTERNAL` |
| 核心进程正在运行 | CLI 退出 2，不改库 | — | 终端输出“请先关闭应用” |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_load_returns_exact_manifest_counts` | `core/sentinel/demo/tests/test_service.py` | 空临时库 | 六类计数为 `6/5/6/6/12/1560` |
| `test_load_is_atomic_on_bad_price_row` | 同上 | 删除 `prices.csv` 一行 | 抛 `INTERNAL`，所有业务表 0 行 |
| `test_load_twice_returns_conflict` | 同上 | 连续两次 `load()` | 第二次 `CONFLICT/ALREADY_LOADED` |
| `test_load_refuses_real_holding` | 同上 | 预置 1 条真实持仓 | `CONFLICT/REAL_DATA_PRESENT`，真实行保留 |
| `test_clear_removes_only_demo_rows` | 同上 | 演示数据 + 1 条真实设置 | 演示计数全 0，真实设置保留 |
| `test_clear_is_idempotent` | 同上 | 连续两次 `clear()` | 两次成功，第二次不抛 |
| `test_demo_rows_cover_every_inserted_table` | `test_loader.py` | 载入后逐表统计 | 每张业务表的演示行数等于登记簿对应数 |
| `test_rpc_load_result_matches_contract` | `test_rpc.py` | 调用 `demo_load(ctx)` | 键仅为 `loaded/ counts`，驼峰字段通过模型 |
| `test_pending_inbox_has_three_and_one_uncertain` | `test_service.py` | 载入后调用 `inbox.list` | 待处理 3，顺序为 0.93、0.78、0.71；待确认 1 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `resources/demo/prices.csv` | 6 个代码 × 260 个共同交易日，几何随机游走，种子 `20261102` | 用 `random.Random(20261102)` 生成后提交，不在运行时生成 |
| `resources/demo/filings.json` | 6 份虚构披露，段落 ≤ 1200 字符 | 按 [00](../../00-术语与约定.md) 的虚构公司手写，禁止真实公司事件 |
| `core/sentinel/demo/tests/bad_counts.json` | 故意少 1 条判定 | 复制 manifest 后改 `decisions` 为 11 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd core && uv run pytest tests/../sentinel/demo/tests -q
# 期望：9 passed，0 failed
SENTINEL_DATA_DIR="$(mktemp -d)" uv run --project core python ../scripts/load_demo.py --json
# 期望：退出码 0；JSON 中 instruments=6、prices=1560
SENTINEL_DATA_DIR="$(mktemp -d)" uv run --project core python ../scripts/load_demo.py --clear
# 期望：退出码 0；输出 "removed": 1608
scripts/check.sh
# 期望：失败 0
```

### 9.2 完成清单
- [ ] 第 4 节全部文件存在，数量与 §5.2 一致
- [ ] `012_demo.sql` 与 04 §3.12 逐字一致
- [ ] §8.1 的 9 个测试全部存在且通过
- [ ] 离线、重复载入、真实数据冲突、清除后残留四类测试有“先失败”记录
- [ ] `scripts/check.sh` 全绿；`owns` 之外无改动
- [ ] 已写 `docs/wp/status/E-01.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| I-01 | `demo.load`、`demo.clear`、固定计数 | 测试只调用 RPC，不直接写 fixture |
| I-02 | `manifest.json` 的 3 条待处理与 1 条待确认 | 演示稿中的数字必须从 manifest 读取 |
| U-07 | `DemoLoadResult` | 已载入和真实数据冲突都显示为可操作提示 |
| E-02 | 虚构公司 ID 与段落文本 | 评测样本不得修改这些 fixture |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| 并行工作包改了表结构 | 插入列数不匹配 | 停写并提交变更申请，禁止在 fixture 里补列 |
| 演示行遗漏登记 | `clear` 后仍有 `source=demo` | 自动整批回滚；修复登记遍历测试 |
| 固定 ID 与真实 ULID 冲突 | 主键冲突 | 演示 ID 统一使用 `01K000...` 段；冲突时中止，不覆盖真实行 |

---
id: P-01
title: 持仓与投资逻辑
phase: mvp0
platform: shared
lane: data
deps: [C-01, C-03, D-02]
size: M
owns: [core/sentinel/portfolio/, core/sentinel/storage/migrations/003_portfolio.sql, core/tests/unit/portfolio/]
appends: []
stubs: []
---
# P-01 持仓与投资逻辑

## 0. 一眼看懂
- **目标**：实现持仓登记、只关注标的、投资逻辑版本化、乐观锁和列表状态计算，交付 8 个 RPC 方法的后端业务层。
- **完成后解锁**：P-02 可以取得可扫描标的和有效逻辑，U-03 可以展示持仓与逻辑。
- **预计规模**：实现约 360 行，测试约 260 行；实现 6 个模块，测试 3 个文件。

## 1. 背景与边界
### 1.1 为什么需要它
扫描的前提是“某人有若干条针对某只股票的可检验判断”。持仓与逻辑必须共享同一套标的标识、版本号和事务规则，否则扫描结果无法回指到当时的逻辑版本。
### 1.2 范围内
1. `holding` 的新增、重新添加、更新和归档。
2. `thesis` 创建、编辑、归档、版本查询，以及每标的最多 5 条有效逻辑。
3. `expectedVersion` 乐观锁与不可变 `thesis_version`。
4. `holdings.list` 的市值、日涨跌、逻辑数、待处理数和 `guarded | attention | unguarded` 状态。
5. 8 个 RPC：`holdings.list`、`holdings.upsert`、`holdings.archive`、`thesis.list`、`thesis.create`、`thesis.update`、`thesis.archive`、`thesis.versions` 的参数模型、业务调用和错误映射。
### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| SQL 迁移执行器与备份 | C-03 提供；本包创建 `003_portfolio.sql` |
| 标的搜索、标的表刷新 | D-02 |
| 行情刷新 | D-04 |
| RPC 分发、取消、JSON 序列化 | C-01 |
| 判定、待处理清单分组、处理动作 | S-05、P-03 |
| 用户可见长文案文件 | C-00；本包只使用已有的 `error.*` 文案和 `data` 细分 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | §3.1 业务 ID、§3.2 代码命名、§4 时间与金额、§5 环境变量 | ULID、UTC、`Decimal`、测试时钟 |
| [04-数据模型.md](../../04-数据模型.md) | §3.3 `003_portfolio.sql`、§4 哈希、§6 删除策略、§7 完整性、§8.2 持仓列表 | 权威表结构与查询 |
| [05-接口契约.md](../../05-接口契约.md) | §3 错误、§4 `Holding`/`Thesis`、§5.3、§5.4、§7.4、§8 | 字段、方法、错误与并发 |
| [09-测试与评测.md](../../09-测试与评测.md) | §2.1 测试命名、§2.2 确定性 | 固定时钟和测试风格 |

## 3. 前置条件
- C-01 提供 `register(method: str, handler: Callable, params_model: type[BaseModel]) -> None`。
- C-03 提供 `Database.read()`、`Database.write()` 和 `IntegrityError`；时间一律来自 `sentinel.clock.now()`。
- D-02 提供 `InstrumentRepository.get(instrument_id) -> InstrumentRow | None`，并保证 `instrument_id` 已规范化为 `市场:代码`。
- `003_portfolio.sql` 必须逐字使用 [04-数据模型.md](../../04-数据模型.md) §3.3 的 DDL；若派发时不存在，实现者停止并提变更申请，不得私建同名表。
- `decision` 与 `v_last_action` 可能由后续工作包才建表；本包在表不存在时把待处理计数固定为 0，表存在后使用同一条查询计算真实值。
- 本包不修改 `pyproject.toml`，只使用标准库和 WP-00 已批准的 `pydantic`。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/portfolio/__init__.py` | 新建 | 导出 `PortfolioService` 与 `register_handlers` |
| `core/sentinel/portfolio/models.py` | 新建 | 行模型、RPC 参数与返回模型 |
| `core/sentinel/portfolio/validation.py` | 新建 | 持仓数量、成本、备注、逻辑文字校验与内容哈希 |
| `core/sentinel/portfolio/repository.py` | 新建 | 三张表的参数化 SQL 与行映射 |
| `core/sentinel/portfolio/service.py` | 新建 | 8 个用例、事务边界、乐观锁 |
| `core/sentinel/portfolio/handlers.py` | 新建 | RPC 参数模型与 handler 注册 |
| `core/sentinel/storage/migrations/003_portfolio.sql` | 新建 | 逐字复制 [04](../../04-数据模型.md) §3.3 的 `holding`、`thesis`、`thesis_version` 三张表 |
| `core/tests/unit/portfolio/test_validation.py` | 新建 | 边界值与哈希测试 |
| `core/tests/unit/portfolio/test_repository.py` | 新建 | 真实 DuckDB 临时库查询测试 |
| `core/tests/unit/portfolio/test_service.py` | 新建 | 用例、并发冲突、状态汇总测试 |

## 5. 接口规格
### 5.1 公开接口
```python
class PortfolioService:
    def list_holdings(self) -> list[HoldingView]: ...
    def list_scannable_instruments(self) -> list[str]: ...
    def list_active_theses(self, instrument_id: str) -> list[ThesisView]: ...
    def count_holdings(self) -> int: ...
    def upsert_holding(self, instrument_id: str, quantity: Decimal,
                       avg_cost: Decimal | None, note: str | None) -> HoldingView: ...
    def archive_holding(self, instrument_id: str) -> None: ...
    def list_theses(self, instrument_id: str | None,
                    status: Literal["active", "archived"] | None) -> list[ThesisView]: ...
    def create_thesis(self, instrument_id: str, statement: str,
                      kill_condition: str | None) -> ThesisView: ...
    def update_thesis(self, thesis_id: str, statement: str,
                      kill_condition: str | None, expected_version: int) -> ThesisView: ...
    def archive_thesis(self, thesis_id: str) -> None: ...
    def list_versions(self, thesis_id: str) -> list[ThesisVersionView]: ...
def register_handlers(registrar: HandlerRegistrar, service: PortfolioService) -> None: ...
```
- 所有 ID 去首尾空白后按原大小写使用；股票代码大小写由 D-02 负责，本包不二次改写。
- `upsert_holding` 在一个写事务内完成“标的存在校验 + 新增或恢复 + 更新”；事务外不得请求网络。
- `create_thesis` 与 `update_thesis` 在同一个写事务中写 `thesis` 与 `thesis_version`，任一语句失败全部回滚。
- 查询允许并发；写操作由 C-03 的进程内写锁串行化。
- 业务异常只抛 `UserError`：参数错误为 `INVALID_ARGUMENT`，记录不存在为 `NOT_FOUND`，版本冲突为 `CONFLICT`。
### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| RPC `holdings.upsert` | `instrumentId` | str | 是 | 已存在的 `market:symbol` | 标的 |
| | `quantity` | Decimal | 是 | `0 ≤ q ≤ 99999999999999.9999`，最多 4 位小数 | 0 表示只关注 |
| | `avgCost` | Decimal | 否 | 非负、最多 4 位小数；数量为 0 时必须为 null | 真实平均成本 |
| | `note` | str | 否 | 去空白后 ≤ 200 个 Unicode 码点；空串转 null | 备注 |
| RPC `thesis.create/update` | `statement` | str | 是 | 去空白后 1–500 个 Unicode 码点 | 逻辑正文 |
| | `killCondition` | str | 否 | 去空白后 1–300；空串转 null | 失效条件 |
| | `expectedVersion` | int | update 必填 | ≥ 1 且等于当前值 | 乐观锁 |
| `HoldingView` | `holdingId` | str | 是 | ULID | 持仓 ID |
| | `thesisCount` | int | 是 | ≥ 0 | 当前有效逻辑数 |
| | `pendingCount` / `uncertainCount` | int | 是 | ≥ 0 | 待处理推翻削弱数 / 待确认数 |
| | `status` | enum | 是 | `guarded/attention/unguarded` | 无逻辑、有处理项、正常 |
| `ThesisView` | `version` | int | 是 | 从 1 开始 | 当前版本 |
| | `versionCount` | int | 是 | ≥ 1 | 不可变版本总数 |
| | `status` | enum | 是 | `active/archived` | 逻辑状态 |
### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MAX_ACTIVE_THESES` | `5` | `service.py` | 每标的上限 |
| `MAX_STATEMENT_CODEPOINTS` | `500` | `validation.py` | 逻辑正文上限 |
| `MAX_KILL_CONDITION_CODEPOINTS` | `300` | `validation.py` | 失效条件上限 |
| `MAX_NOTE_CODEPOINTS` | `200` | `validation.py` | 持仓备注上限 |
| `QUANTITY_QUANTUM` | `Decimal("0.0001")` | `validation.py` | 与 `DECIMAL(18,4)` 一致 |

## 6. 实现步骤
1. **规范化文字**：先 `strip()`；`statement` 与 `killCondition` 的计数使用 `len(str)`（Python 对 Unicode 码点计数）。`killCondition == ""` 转 `None`。
2. **内容哈希**：按 [04-数据模型.md](../../04-数据模型.md) §4 计算 `sha256(norm(statement) + "\n---\n" + norm(kill_condition or ""))`；`norm` 使用 NFC、统一换行、去首尾空白。
3. **持仓 upsert**：事务内查标的；无记录或 `is_active = false` 抛 `NOT_FOUND`。按 `instrument_id` 查持仓；不存在时插入新 ULID、`created_at = updated_at = clock.now()`；存在时更新数量、成本、备注、`updated_at`，并令 `archived_at = NULL`。数量为 0 时拒绝非空 `avg_cost`。
4. **逻辑创建**：事务内统计该标的 `status = 'active'` 的行数；达到 5 时抛 `INVALID_ARGUMENT(field="instrumentId", data={"max":5})`。插入 `thesis(current_version=1)` 与 `thesis_version(version=1)`。
5. **逻辑编辑**：读取 `thesis`；状态非 active 抛 `NOT_FOUND`。`expected_version != current_version` 时抛 `CONFLICT(data.currentVersion)`。若新内容哈希等于当前版本哈希，直接返回当前视图，不写行。否则插入 `version = current + 1`，并用 `UPDATE thesis SET current_version = :next WHERE thesis_id = :id AND current_version = :expected`；受影响行数不是 1 时抛 `CONFLICT`。
6. **归档**：持仓与逻辑都用 `archived_at`；重复归档幂等返回成功。归档持仓不删除逻辑、判定和处理记录。
7. **列表 SQL**：持仓严格按 [04-数据模型.md](../../04-数据模型.md) §8.2；额外用子查询统计有效逻辑、待处理推翻/削弱、待确认。`status` 优先级：无有效逻辑 → `unguarded`；存在待处理推翻/削弱 → `attention`；其他 → `guarded`。
8. **返回转换**：金额用 `Decimal` 量化为 4 位并序列化为十进制字符串；行情价格保持 `float`；时间用 `to_iso()` 输出 `Z` 结尾。

## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户可见文案（messages 键） |
|---|---|---|---|
| 数量为负、超过 4 位小数或超过上限 | 不写数据库，`data.field="quantity"` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 数量为 0 但提供成本 | `data.field="avgCost"` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 备注超过 200 码点 | `data.field="note"`、`data.max=200` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 标的不存在或未激活 | 不创建持仓 | `NOT_FOUND` | `error.NOT_FOUND` |
| 逻辑正文为空或超过 500 码点 | `data.field="statement"` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 失效条件超过 300 码点 | `data.field="killCondition"` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 第 6 条有效逻辑 | `data.field="instrumentId"`、`data.max=5` | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 编辑版本过期 | 返回最新版本号，不覆盖 | `CONFLICT` | `error.CONFLICT` |
| 重复创建同一版本内容 | 返回当前对象，不新增版本 | — | — |
| 数据库写入失败 | 回滚整个用例，记录结构化日志 | `INTERNAL` | `error.INTERNAL` |

## 8. 测试（先写）
### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_statement_counts_unicode_codepoints` | `test_validation.py` | 500 个 `测` 加 1 个 `试` | `INVALID_ARGUMENT`，`field="statement"` |
| `test_kill_condition_blank_becomes_none` | `test_validation.py` | `"  \n "` | `None`，哈希与无失效条件相同 |
| `test_quantity_rejects_fifth_decimal_place` | `test_validation.py` | `Decimal("0.00001")` | `INVALID_ARGUMENT`，`field="quantity"` |
| `test_upsert_reactivates_archived_holding` | `test_service.py` | 归档 `us:ZZAR` 后以 25 股重新添加 | `archived_at is None`，数量 `"25.0000"` |
| `test_upsert_holding_rolls_back_when_cost_invalid` | `test_service.py` | 数量 0、成本 10 | 抛错；原持仓数量与更新时间不变 |
| `test_sixth_active_thesis_is_rejected` | `test_service.py` | 同一标的已有 5 条 active 逻辑 | `INVALID_ARGUMENT`，`data.max == 5` |
| `test_update_same_content_does_not_add_version` | `test_service.py` | 当前版本 1，提交相同文字 | 返回版本 1；`thesis_version` 仍为 1 行 |
| `test_update_stale_version_returns_conflict` | `test_service.py` | 当前 3，提交 expected 2 | `CONFLICT`，`data.currentVersion == 3` |
| `test_archive_keeps_versions_and_decisions` | `test_repository.py` | 逻辑有 2 个版本和 1 条判定后归档 | `thesis.status == archived`；版本与判定行数不变 |
| `test_holding_status_precedence` | `test_repository.py` | 一只无逻辑、一只待处理、一只正常 | 状态依次为 `unguarded/attention/guarded` |
| `test_holdings_order_puts_positions_before_watchlist` | `test_repository.py` | 两只只关注、一只持仓 | 持仓第一；同组按 symbol 升序 |
| `test_all_mutations_use_utc_clock` | `test_service.py` | `SENTINEL_CLOCK=2026-11-02T00:35:00Z` | 新增行 `created_at == 2026-11-02 00:35:00` |
### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增文件 | 每个测试创建临时 DuckDB，执行 `001_core` 到 `003_portfolio` 的迁移，再插入 `us:ZZAR`、`us:ZZFD`、`us:ZZCL` | 测试内构造；禁止写真实数据目录 |

## 9. 验收
### 9.1 命令与期望输出
```bash
(cd core && uv run pytest tests/unit/portfolio -q)
# 期望：12 passed，0 failed
scripts/check.sh
# 期望：exit=0；ruff、mypy 对 sentinel/portfolio 全绿
```
### 9.2 完成清单
- [ ] 第 4 节全部文件存在，且没有修改 `owns` 之外的路径
- [ ] `003_portfolio.sql` 与 04 §3.3 逐字一致
- [ ] 8 个 RPC 方法按 [05-接口契约.md](../../05-接口契约.md) §5.3、§5.4 注册
- [ ] 第 8.1 节 12 个测试全部存在并先失败后通过
- [ ] 所有写用例在 `Database.write()` 中完成，网络调用为 0 次
- [ ] 已写 `docs/wp/status/P-01.md`

## 10. 交接、风险与回退
| 对象 | 使用或风险 | 约定与回退 |
|---|---|---|
| P-02 | 使用 `list_scannable_instruments()` 和 `list_active_theses()` | 本包额外提供两个只读方法，返回不可变视图；P-02 不直接查 `thesis` 表 |
| P-03 | 使用持仓与 `thesis_version` 关联判定 | 逻辑编辑产生新版本，旧判定仍指向旧版本 |
| U-03 | 使用 8 个 RPC 方法 | 所有金额是十进制字符串，时间以 `Z` 结尾 |
| 迁移文件缺失 | 实现者无法建表 | 停止并提 CR；不得把 DDL 内联进 Python |
| 并发编辑 | 两个窗口同时提交 | 只允许一个成功；另一个收到 `CONFLICT` 并刷新 |

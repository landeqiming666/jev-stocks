---
id: C-03
title: 存储：DuckDB 封装、迁移、备份
phase: mvp0
platform: shared
lane: core
deps: [C-00]
size: M
owns: [core/sentinel/storage/__init__.py, core/sentinel/storage/db.py, core/sentinel/storage/migrations.py, core/sentinel/storage/backup.py, core/sentinel/storage/integrity.py, core/sentinel/storage/migrations/001_core.sql, core/tests/unit/storage/, core/tests/fixtures/storage/]
appends: []
stubs: []
---

# C-03 存储：DuckDB 封装、迁移、备份

## 0. 一眼看懂
- **目标**：提供单文件 DuckDB 的唯一入口、只读游标、单写入者事务、迁移执行器、迁移前备份、备份保留和完整性检查。
- **完成后解锁**：C-04、D-02、D-03、D-04、P-01、P-05、P-06、S-05。
- **预计规模**：实现约 430 行，测试约 300 行；迁移 SQL、执行器、备份、完整性各一个模块。

## 1. 背景与边界

### 1.1 为什么需要它
每个仓储如果自己打开连接、拼 SQL、处理事务，同一个数据库会出现多个写入者、半个订单和无法回滚的迁移。C-03 把所有 DuckDB 访问收口到一个 `Database`，并让迁移失败时自动回到备份。
### 1.2 范围内
1. `Database`：打开、关闭、`read()` 游标、`write()` 事务、`schema_version`。
2. 迁移执行器：发现、校验和、按编号补迁移、事务性执行、失败还原。
3. 备份：迁移前复制、命名、保留最近 3 份。
4. `001_core.sql` 的 `setting` 表，逐字使用 [04] §3.1。
5. `check_integrity(db) -> list[str]`，覆盖 [04] §7 的 16 个检查名称。
6. 测试 fixture 中的成功、坏 SQL、被篡改迁移和断链数据。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| `002`–`012` 迁移和业务表 | 各自的 D-、P-、S-、E- 工作包 |
| 设置项的默认值和 RPC | C-04 |
| 持仓、判定、扫描、账本仓储 | P-01、S-05、P-02、P-05、P-06 |
| 数据清理、演示数据删除 | E-01 与各业务包，按 [04] §6 |
| 修改 `duckdb==1.4.3` 版本 | 禁止；需要变更申请 |

## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [04-数据模型.md](../../04-数据模型.md) | 1 总则、2 迁移、3.1 `001_core.sql`、5 设置项、7 完整性检查 | 权威 DDL 与迁移规则 |
| [02-技术架构.md](../../02-技术架构.md) | 7.3 数据库访问规则、10 存储与目录、12 稳定性 | 单写入者、备份目录、失败回退 |
| [00-术语与约定.md](../../00-术语与约定.md) | 3.1 业务 ID、4 时间与金额、6 目录约定 | ID、UTC、`SENTINEL_DATA_DIR` |
| [09-测试与评测.md](../../09-测试与评测.md) | 2.2 确定性、3 测试数据、4 契约测试 | 临时目录和固定时间 |

## 3. 前置条件
- WP-00 与 C-00 已合并：`duckdb==1.4.3`、`InternalError`、`clock.now`、`new_id` 可用。
- 测试使用 `tmp_path` 与 `SENTINEL_DATA_DIR`，禁止连接真实数据目录。
- 不启动网络，不调用 Jev；迁移失败时不得向 stdout 输出日志。

## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/storage/__init__.py` | 新建 | 导出 `Database`、`WriteTx`、`SqlExecutor`、`MigrationReport`、`check_integrity` |
| `core/sentinel/storage/db.py` | 新建 | 连接、线程本地读游标、写锁与事务上下文 |
| `core/sentinel/storage/migrations.py` | 新建 | 文件发现、SHA-256、SQL 切分、迁移执行与失败还原 |
| `core/sentinel/storage/backup.py` | 新建 | 备份命名、复制、按文件名只保留最近 3 份 |
| `core/sentinel/storage/integrity.py` | 新建 | 16 个只读完整性查询 |
| `core/sentinel/storage/migrations/001_core.sql` | 新建 | `setting` 表，逐字使用 [04] §3.1 |
| `core/tests/unit/storage/test_db.py` | 新建 | 连接、读游标、事务回滚 |
| `core/tests/unit/storage/test_migrations.py` | 新建 | 编号、校验和、乱序、失败还原 |
| `core/tests/unit/storage/test_backup.py` | 新建 | 命名与保留 3 份 |
| `core/tests/unit/storage/test_integrity.py` | 新建 | 构造违规数据并检查 |
| `core/tests/fixtures/storage/` | 新建 | §8.2 的迁移与断链 fixture |

## 5. 接口规格

### 5.1 公开接口
```python
class SqlExecutor(Protocol):
    def execute(self, sql: str, params: Sequence[object] | None = None) -> object: ...
    def executemany(self, sql: str, rows: Sequence[Sequence[object]]) -> object: ...
    def fetchone(self) -> tuple[object, ...] | None: ...
    def fetchall(self) -> list[tuple[object, ...]]: ...

class Database:
    def __init__(self, path: Path, *, read_only: bool = False) -> None: ...
    def open(self) -> None: ...
    def close(self) -> None: ...
    def read(self) -> ContextManager[SqlExecutor]: ...
    def write(self) -> ContextManager[WriteTx]: ...
    def exclusive(self) -> ContextManager[None]: ...
    def backup(self, label: str) -> Path: ...
    def migrate(self, migrations_dir: Path | None = None) -> MigrationReport: ...
    @property
    def schema_version(self) -> int: ...
    @property
    def path(self) -> Path: ...
class WriteTx(SqlExecutor):
    def execute(self, sql: str, params: Sequence[object] | None = None) -> WriteTx: ...
    def executemany(self, sql: str, rows: Sequence[Sequence[object]]) -> None: ...
    def fetchone(self) -> tuple[object, ...] | None: ...
    def fetchall(self) -> list[tuple[object, ...]]: ...
@dataclass(frozen=True)
class MigrationReport:
    applied: tuple[int, ...]
    current_version: int
    backup_path: Path | None
def backup_database(db_path: Path, backup_dir: Path, version: int, now: datetime) -> Path: ...
def check_integrity(db: Database) -> list[str]: ...
```
`open` 只建立连接，不自动迁移；`migrate` 在启动序列中显式调用。`read` 返回当前线程的 cursor（实现 `SqlExecutor`），退出时关闭 cursor 但不关闭主连接。**DuckDB cursor 拥有独立事务**。`read()` 与 `write()` 共用按数据库路径共享的 `threading.RLock`，整个上下文期间持锁，避免本进程内读写交错。写事务内同一线程可以另开 `read()`，但它只见已提交快照；需要读取自身未提交数据时必须使用原 `tx`。**禁止在读上下文内调用 `write()`**，也禁止嵌套写事务。`write` 进入时执行 `BEGIN TRANSACTION`，正常退出 commit，任意异常 rollback；`WriteTx` 同样实现 `SqlExecutor`，只读函数应接受读游标或写事务。`execute()` 返回自身，支持 fetch 链式调用但不暴露原始连接的 commit/rollback。`backup(label)` 供业务包在破坏性操作前调用。重复 `close` 是空操作；关闭后调用 `read` 或 `write` 抛 `RuntimeError`。

`backup(label)` 规则：`label` 只允许 `^[a-z][a-z0-9_.-]{0,31}$`，用于文件名；实际文件名为 `sentinel-v<version>-<label>-<UTC 时间戳>.duckdb`；同一秒冲突时追加 `-2`、`-3`。复制前 checkpoint WAL，正文先写同目录临时文件并 flush/fsync，再原子、不覆盖地发布正式文件；恢复也先同步临时文件再 replace。正式备份按真实 UTC 时间戳保留最近 3 份，不按版本号或 label 字典序排序。非法 `label` 抛 `ValueError`。

`exclusive()` 供破坏性业务操作将备份与后续短事务置于同一路径共享锁中，避免其他句柄在
备份后、删除前插入未备份数据。它不返回 SQL executor、不打开事务，内部仍显式使用
`read()`、`backup()`、`write()`；从已有读写事务进入会失败，未打开数据库也会失败。

### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `Migration` | `version` | int | 是 | 3 位数字，唯一 | 编号 |
| | `name` | str | 是 | `^[a-z0-9_]+$` | 文件名主体 |
| | `sql_path` | Path | 是 | `NNN_*.sql` | 文件 |
| | `checksum` | str | 是 | 64 位小写十六进制 | 内容 SHA-256 |
| `schema_version` | `version` | int | 是 | 主键 | 已应用编号 |
| | `name` | str | 是 | 非空 | 迁移名 |
| | `checksum` | str | 是 | 64 位十六进制 | 记录时的摘要 |
| | `applied_at` | datetime | 是 | UTC | 应用时刻 |
| `MigrationReport` | `applied` | tuple[int,...] | 是 | 升序 | 本次应用 |
| | `current_version` | int | 是 | ≥ 0 | 最大版本 |
### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `DB_FILENAME` | `"sentinel.duckdb"` | `db.py` | 主库文件名 |
| `BACKUP_KEEP` | `3` | `backup.py` | 保留备份数 |
| `MAX_MIGRATION_BYTES` | `2_097_152` | `migrations.py` | 单个迁移上限 |
| `SQL_NAME_RE` | `^\d{3}_[a-z0-9_]+\.sql$` | `migrations.py` | 文件名规则 |
| `SCHEMA_TABLE_SQL` | 见 [04] §2.1 | `migrations.py` | `schema_version` 建表语句 |

## 6. 实现步骤
1. **打开**：`path.parent.mkdir(parents=True, exist_ok=True)`；用 `duckdb.connect(str(path), read_only=read_only)`；连接后执行 `PRAGMA enable_progress_bar=false` 和 `SET TimeZone='UTC'`。失败包装为 `InternalError("INTERNAL", detail="open")`。
2. **读游标**：进入 `read()` 先获取 `RLock`，用 `threading.local()` 保存 cursor；每次创建 `connection.cursor()`，上下文退出时 `cursor.close()` 并释放锁；不得在 read 中执行写语句。读上下文内禁止调用 `write()`（同线程会重入并破坏事务边界），也禁止网络/模型调用，避免长时间持锁。
3. **写事务**：锁内 `BEGIN TRANSACTION`；`WriteTx` 把参数原样传给 DuckDB，禁止字符串拼接用户输入；异常 rollback 后重新抛出原异常；退出锁。
4. **发现迁移**：枚举 `*.sql`，名称不符合 `SQL_NAME_RE` 或编号重复时抛 `InternalError`；按 `version` 升序读取；单文件超过 2 MiB 抛 `InternalError`。
5. **检查**：`CREATE TABLE IF NOT EXISTS schema_version (...)`；对已记录版本重新计算 SHA-256，文件缺失或不一致立即抛 `InternalError`，消息含文件名。
6. **备份**：待应用迁移非空且数据库已存在且 `stat().st_size > 0` 时，调用 `backup_database`；备份名格式为 `sentinel-v{current_version}-{YYYYMMDDTHHMMSSZ}.duckdb`，同一秒冲突时追加 `-2`、`-3`。保留按文件名升序最后 3 个。
7. **应用**：每个待应用迁移独立事务；`split_sql()` 扫描字符状态，忽略单引号、双引号、`--` 行注释中的分号；逐句 `execute`，最后插入 `schema_version` 并 commit。即使编号低于当前最大值也应用。
8. **失败还原**：事务 rollback 后关闭连接，把备份复制回原路径；没有备份时删除新建文件；抛 `InternalError`，`detail` 含迁移文件名和语句序号。
9. **完整性**：依次执行 [04] §7 的 16 个查询；每条返回中文描述，例如 `orphan_thesis_version: thesis_id=...`；结果升序排序，不修改数据。
10. **手动备份**：`Database.backup(label)` 复用第 6 步的复制与保留逻辑，但**不要求有待应用迁移**；数据库不存在或大小为 0 时抛 `ValueError`；返回绝对路径，调用方负责在失败提示中展示该路径。

## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户可见文案 |
|---|---|---|---|
| 数据目录不可写 | 不创建临时半成品 | `INTERNAL` | “无法打开本地数据文件，请检查权限。” |
| 迁移文件名非法或编号重复 | 不执行任何迁移 | `INTERNAL` | “数据库迁移文件不完整。” |
| 已应用迁移被修改 | 拒绝启动并记录文件名 | `INTERNAL` | “数据库需要修复，请从备份恢复。” |
| 迁移 SQL 失败 | 回滚并还原备份 | `INTERNAL` | “数据库升级失败，已恢复备份。” |
| 读操作尝试写入 | 由 DuckDB 拒绝；不得吞错 | `INTERNAL` | 仅日志，不展示 SQL |
| 写事务中抛异常 | 回滚且不提交 | 原异常 | 由调用方映射 |
| 备份超过 3 份 | 删除最旧一份 | — | 不提示 |
| 完整性检查发现断链 | 返回描述，不自动修复 | — | 设置页显示“数据需要检查” |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_open_creates_schema_version_table` | `test_db.py` | 新临时库 `open()` | `schema_version == 0`，表存在 |
| `test_write_rolls_back_on_exception` | 同上 | 插入 `setting` 后抛 `ValueError` | 抛出 `ValueError`；行数为 0 |
| `test_read_uses_independent_cursor` | 同上 | 两个线程先后 `read()` | 两个 cursor 不相同，均能查询；第二次在第一次退出后进入 |
| `test_read_lock_blocks_concurrent_write` | 同上 | 线程 A 持 read 1 s，线程 B 调 write | B 在 A 释放后才进入事务；无异常 |
| `test_migrate_applies_001_and_reports_version` | `test_migrations.py` | fixture `001_ok.sql` | `applied == (1,)`，`current_version == 1` |
| `test_migrate_second_time_is_noop` | 同上 | 连续执行两次 | 第二次 `applied == ()`，版本仍 1 |
| `test_checksum_mismatch_refuses_startup` | 同上 | 修改已记录文件一个字节 | `InternalError`，`detail` 含文件名 |
| `test_lower_number_is_applied_after_higher` | 同上 | 先应用 002，再出现 001 | `applied == (1,)` |
| `test_failed_migration_restores_backup` | 同上 | `002_bad.sql` 含非法 SQL | 原文件恢复，版本仍 1 |
| `test_backup_keeps_latest_three` | `test_backup.py` | 生成 4 个不同时间戳 | 只剩后 3 个文件名 |
| `test_backup_api_rejects_unsafe_label` | 同上 | `label="../x"` | 抛 `ValueError`；不创建任何文件 |
| `test_orphan_thesis_version_is_reported` | `test_integrity.py` | 构造无 `thesis` 的版本行 | 结果含 `orphan_thesis_version` |
| `test_each_integrity_rule_has_a_violation_case` | 同上 | 16 个构造违规 fixture | 每条规则各返回 1 条；干净库返回 `[]` |
| `test_clean_database_has_no_integrity_errors` | 同上 | 只迁移 `001` | 结果 `[]` |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| `core/tests/fixtures/storage/migrations/001_ok.sql` | `CREATE TABLE sample (id INTEGER);` | 测试作者手写 |
| `core/tests/fixtures/storage/migrations/002_ok.sql` | `CREATE TABLE child (id INTEGER);` | 测试作者手写 |
| `core/tests/fixtures/storage/migrations/002_bad.sql` | `CREATE TABLE gone (;` | 测试作者手写，故意失败 |
| `core/tests/fixtures/storage/migrations/003_semicolon.sql` | 含字符串 `'a;b'` 和 `-- ;` 的 `INSERT` | 测试作者手写 |
| `core/tests/fixtures/storage/seed_integrity.sql` | 插入断链行 | 测试作者手写，不联网 |

## 9. 验收

### 9.1 命令与期望输出
```bash
cd core
uv run pytest tests/unit/storage -q
# 期望：14 passed，0 failed
uv run ruff check sentinel/storage tests/unit/storage
# 期望：exit=0
```

### 9.2 完成清单
- [ ] 第 4 节每个文件已创建，`001_core.sql` 与 [04] §3.1 逐字一致
- [ ] 第 8.1 节 14 个测试全部存在且通过
- [ ] `scripts/check.sh` 全绿
- [ ] 没有修改 `owns` 之外的路径，没有新增依赖
- [ ] `TODO-VERIFY(C-03)` 的 DuckDB 限制已由测试记录
- [ ] 已写 `docs/wp/status/C-03.md`

## 10. 给下游的交接
| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| C-04 | `Database.read()`、`Database.write()`、`schema_version` | 设置只用参数绑定，不在事务中联网 |
| D-02、D-03、D-04 | `Database.write()` 和迁移目录 | 只新增自己的 `NNN_*.sql`，不改 `001` |
| P-01、P-05、P-06、S-05 | `Database.write()`、`Database.read()`、`Database.backup()`、`check_integrity` | 账本和判定必须单事务提交；破坏性操作前先 `backup(label)` |
| E-01 | 迁移与 `demo_row` 例外 | 删除演示行前必须先备份 |

---
id: C-07
title: 组合根与进程入口：装配服务、注册处理器、启动恢复
phase: mvp0
platform: shared
lane: core
deps: [C-01, C-03, C-04, D-01, D-02, D-03, D-04, S-01, S-02, S-03, S-04, P-01, P-02, P-03, P-05, P-06, E-01]
size: M
owns: [core/sentinel/__main__.py, core/sentinel/app/, core/tests/unit/app/]
appends: []
stubs: []
---

# C-07 组合根与进程入口：装配服务、注册处理器、启动恢复

## 0. 一眼看懂

- **目标**：提供 `python -m sentinel` 入口和唯一的组合根：打开数据库、执行迁移、构造所有服务与引擎、注册 38 个业务处理器（加 C-01 的 `app.ping`/`app.shutdown` 共 40 个）、执行启动恢复，然后启动 C-01 的 RPC server。
- **完成后解锁**：C-02 的默认命令 `python -m sentinel` 可以真正启动；I-01 可以跑真实进程；E-01 的 `app/methods/demo.py` 有明确归属。
- **预计规模**：实现约 500 行，测试约 260 行；入口、容器、注册表与 7 个方法适配器。

## 1. 背景与边界

### 1.1 为什么需要它

各工作包只提供 `register_handlers(registrar, service)` 与服务类，没有任何模块负责“谁在什么时候构造它们”。如果让 C-01 直接导入业务包，传输层会反向依赖全部业务；如果让每个服务自己注册，启动顺序又会散落。组合根是唯一允许同时依赖全部业务包的地方。

### 1.2 范围内

1. `core/sentinel/__main__.py`：解析 `--data-dir`、`--resource-dir`、`--parent-pid`、`--log-level`，调用 `app.main.run()`。
2. `app/container.py`：`AppContainer.build(args)`，按固定顺序构造 `Database`、设置、密钥、HTTP、市场适配器、引擎、语义流水线、业务服务。
3. `app/registry.py`：`HandlerRegistrar` 协议与 `register_all(dispatcher, container)`，显式调用每个包导出的注册函数（settings 用 `register`，其余用 `register_handlers`）。
4. `app/methods/*.py`：每个域一个 ≤ 30 行的适配器；settings 调 C-04 `register`，markets 适配器注册 `instruments.search` 与 `prices.refresh`，其余转发 `register_handlers`；不写业务逻辑。
5. `app/lifecycle.py`：迁移、`recover_on_startup`、`app.ready` 通知、优雅关闭。
6. 测试：构造顺序、处理器数量、缺配置降级、迁移失败退出、启动恢复调用一次。

### 1.3 明确不做

| 不做 | 由谁做 |
|---|---|
| JSON-RPC 传输、取消、线程池 | C-01 |
| 业务规则、SQL、判定与账本 | 各业务工作包 |
| 前端与 Rust 桥接 | U-00、C-02 |
| 定时器、托盘、系统通知 | v1 |
| 自动扫描 | P-02 的 `scan.start` 只在用户点击后调用 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [02-技术架构.md](../../02-技术架构.md) | §6 进程与桥接、§8 启动序列、§16 分层 | 启动顺序与依赖方向 |
| [05-接口契约.md](../../05-接口契约.md) | §5.10 方法总表、§6 通知、§7 状态机 | 40 个处理器与 `app.ready` |
| [04-数据模型.md](../../04-数据模型.md) | §2 迁移、§5 设置、§3.8 扫描、§3.10 账户 | 启动时读取的设置与恢复 |
| [06-语义判定与Jev.md](../../06-语义判定与Jev.md) | §6.2 引擎选择 | 两个引擎工厂的注入 |
| [09-测试与评测.md](../../09-测试与评测.md) | §2 确定性、§4 契约测试 | 假服务与顺序断言 |

## 3. 前置条件

- C-01 已提供 `RpcServer`、`Dispatcher.register`、`CancelToken`。
- C-03 已提供 `Database`、`backup()`、`migrate()`。
- C-04 已提供 `SettingsService`、`SecretStore`、`app.bootstrap` 的处理器。
- D-01～D-04 已提供 `HttpClient`、`InstrumentService`、`SecFilingsService`、`PriceService`。
- S-01～S-04 已提供 `DecisionPipeline`、`select_engine()`、两个引擎工厂。
- P-01、P-02、P-03、P-05、P-06、E-01 已提供各自的服务与 `register_handlers`。
- 所有路径由参数注入，禁止在模块导入时读环境变量或创建数据库。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/__main__.py` | 新建 | `python -m sentinel` 入口；只解析参数并调用 `app.main.run()` |
| `core/sentinel/app/__init__.py` | 新建 | 导出 `AppContainer`、`run`、`build_container` |
| `core/sentinel/app/container.py` | 新建 | `AppContainer` 数据类与 `build(args)`；唯一构造顺序 |
| `core/sentinel/app/registry.py` | 新建 | `HandlerRegistrar` 协议、`register_all()`、方法计数校验 |
| `core/sentinel/app/lifecycle.py` | 新建 | 迁移、启动恢复、`app.ready`、关闭 |
| `core/sentinel/app/main.py` | 新建 | 组装 RPC server，`serve_forever()`，信号处理 |
| `core/sentinel/app/probe.py` | 新建 | 实现 C-04 的 `ConnectionProbe`：Jev 引擎健康、SEC 连通性、JEVDB 可用性 |
| `core/sentinel/app/methods/__init__.py` | 新建 | 7 个适配器模块的导入顺序 |
| `core/sentinel/app/methods/{settings,markets,portfolio,inbox,scan,paper,risk,demo}.py` | 新建 | 每个 ≤ 30 行，只做注册转发；markets 适配器覆盖 instruments/prices |
| `core/tests/unit/app/test_container.py` | 新建 | 构造顺序、依赖注入、缺配置分支 |
| `core/tests/unit/app/test_registry.py` | 新建 | 40 个方法全部注册、重复注册报错 |
| `core/tests/unit/app/test_lifecycle.py` | 新建 | 迁移失败退出、启动恢复一次、`app.ready` 顺序 |

## 5. 接口规格

### 5.1 公开接口

```python
@dataclass
class AppContainer:
    db: Database
    settings: SettingsService
    secret_store: SecretStore
    secrets: SecretsService
    http: HttpClient
    instruments: InstrumentService
    filings: SecFilingsService
    prices: PriceService
    pipeline: DecisionPipeline
    engine: SemanticEngine
    probe: ConnectionProbe
    portfolio: PortfolioService
    scan: ScanService
    inbox: InboxService
    paper: PaperService
    risk: RiskService
    demo: DemoService

def build_container(args: AppArgs) -> AppContainer: ...
def register_all(dispatcher: Dispatcher, c: AppContainer) -> int: ...
def run(argv: Sequence[str] | None = None) -> int: ...
```

`register_all` 返回注册的**业务**方法数，MVP-0 必须等于 38（`docs/05` 的 40 个方法减去 C-01 的 `app.ping`/`app.shutdown`）；`app.main` 在 server 构造后断言 dispatcher 总数为 40。少于或多于都抛 `InternalError`，日志列出缺失/重复方法名。

### 5.2 数据结构

| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `AppArgs` | `data_dir` | Path | 是 | 已存在或可创建 | 应用数据目录 |
| | `resource_dir` | Path | 是 | 包含 `resources/` | 价格表与日历 |
| | `parent_pid` | int \| None | 否 | > 0 | C-01 看门狗 |
| | `log_level` | str | 是 | DEBUG/INFO/WARN/ERROR | 日志级别 |
| `HandlerRegistrar` | `register` | callable | 是 | 与 C-01 同签名 | 处理器注册 |

### 5.3 常量与配置

| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `EXPECTED_BUSINESS_METHOD_COUNT` | `38` | `app/registry.py` | 业务处理器数 |
| `EXPECTED_TOTAL_METHOD_COUNT` | `40` | `app/main.py` | 加两个内置方法后的总数，与 05 §5.10 一致 |
| `STARTUP_TIMEOUT_SECONDS` | `8` | `app/main.py` | `app.ready` 前的最长启动时间 |
| `SHUTDOWN_GRACE_SECONDS` | `3` | `app/main.py` | 关闭时等待 worker |
| `METHOD_MODULES` | 8 个模块名 | `app/methods/__init__.py` | 显式注册顺序 |

## 6. 实现步骤

1. **解析参数**：`__main__.py` 只接受四个参数；未知参数、缺失 `--data-dir`、路径不可写时打印中文错误到 stderr 并退出码 2，不启动 server。
2. **日志**：调用 C-00 `logging_setup.configure(level, data_dir/"logs")`；失败直接退出码 1。
3. **数据库**：`Database(path)` → `open()` → `migrate()`；迁移失败记录 `detail` 并退出码 3。`backup()` 只在迁移内部调用。
4. **设置与密钥**：构造系统 `SecretStore`（钥匙串后端）→ `SecretsService(store, clock)`，再构造 `SettingsService`；读取设置失败时使用默认值并记录 warn；缺 Jev key 不阻止启动，只让 `app.bootstrap.configured.jevKey=false`。`platform_name` 取 `sentinel.platform.current()`，`offline` 取 `SENTINEL_OFFLINE=1`。
5. **HTTP 与数据源**：按 D-01 构造 `HttpClient`；构造 `InstrumentService`、`SecFilingsService`、`PriceService`。SEC 联系邮箱为空时仍构造，但第一次请求抛 `CONFIG_REQUIRED`。
6. **引擎与探针**：用 S-02 的 `select_engine(settings.engine, factories)` 构造；`auto` 降级时把 `EngineChange` 存入容器，`app.ready` 之后以 `engine.changed` 通知发出一次。构造 `ConnectionProbe`，它只读引擎健康与 HTTP 可达性，不发送持仓或逻辑内容。
7. **流水线**：构造 `DecisionPipeline(db, engine, model_id=settings.modelId, daily_budget=settings.dailyTokenBudget)`；不在这里跑扫描。
8. **业务服务**：按 P-01→P-05→P-06→P-03→P-02→E-01 顺序构造；`ScanService` 注入 `DecisionPipeline`、`SecFilingsService`、`InboxService`，不反向依赖 `app`。
9. **注册**：`register_all` 依次调用 8 个适配器：settings 调用 C-04 的 `register(dispatcher, settings, secrets, db, platform_name, engine, probe)`；markets 注册 `instruments.search` 与 `prices.refresh`；其余调用各包的 `register_handlers(...)`。重复方法由 C-01 抛错，组合根转成 `INTERNAL` 并退出。注册完成后断言**业务方法**计数为 38；`app.main` 构造 `RpcServer` 后断言 dispatcher 总数为 40。
10. **启动恢复**：调用 `scan.recover_on_startup()` 一次；返回修改行数写日志；不自动启动扫描。随后 `server.notify("app.ready", {...})`。
11. **运行**：`RpcServer.start()` → `serve_forever()`；捕获 `KeyboardInterrupt`，调用 `stop()`，关闭 DB，退出码 0。
12. **关闭**：`lifecycle.shutdown()` 先停 server（等待 3 s），再 `db.close()`；任何关闭异常只记录，不掩盖原退出码。

## 7. 错误与边界情况

| 情形 | 行为 | 错误码/退出码 | 用户可见文案 |
|---|---|---|---|
| 缺 `--data-dir` 或不可写 | 不打开数据库 | 退出码 2 | “无法写入应用数据目录。” |
| 迁移失败 | 不启动 server | 退出码 3 | “数据库升级失败，已尝试恢复备份。” |
| 处理器数量 ≠ 40 | 启动失败 | `INTERNAL` | “应用组件不完整，请重新安装。” |
| 引擎 `auto` 降级 | 启动成功，发一次通知 | 无错误 | “未找到 JEVDB 扩展，已改用 Jev 直连。” |
| 缺 Jev key | 启动成功，扫描前置拒绝 | `CONFIG_REQUIRED` | 设置页提示 |
| 启动恢复失败 | 启动继续，记录 warn | 无错误 | 扫描页提示“上次运行未正常结束” |
| 关闭超时 | 强制结束 worker | 退出码 0 | 无 |

## 8. 测试（先写）

### 8.1 测试清单

| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_container_builds_services_in_order` | `test_container.py` | 假 Database/Settings/Http/Engines | 构造顺序为 db→settings→http→markets→engine→pipeline→services |
| `test_missing_jev_key_still_boots` | 同上 | 设置无 key | `configured.jevKey=false`；不抛错 |
| `test_auto_engine_change_is_emitted_once` | 同上 | `select_engine` 返回 `EngineChange` | 容器记录一次；`app.ready` 后发一次 |
| `test_probe_does_not_leak_holdings` | 同上 | 假 HTTP 记录请求 | 探针请求不含持仓、逻辑或账本字段 |
| `test_register_all_registers_exactly_thirty_eight_business_methods` | `test_registry.py` | 8 个假 registrar | 计数 38；方法名集合等于 05 §5.10 减去 app.ping/app.shutdown |
| `test_missing_handler_fails_startup` | 同上 | 少注册一个方法 | `InternalError`，日志含缺失方法名 |
| `test_duplicate_handler_fails_startup` | 同上 | 两个包注册同一方法 | `ValueError` → `INTERNAL` |
| `test_migration_failure_exits_three` | `test_lifecycle.py` | `migrate()` 抛 `InternalError` | 退出码 3；未启动 server |
| `test_recover_on_startup_called_once` | 同上 | 两个遗留 running | `recover_on_startup` 调用 1 次；返回 2 |
| `test_app_ready_is_sent_after_recovery` | 同上 | 假 server | 调用顺序：migrate → recover → notify |
| `test_shutdown_closes_db_even_if_server_stop_fails` | 同上 | `stop()` 抛错 | `db.close()` 仍调用；退出码 0 |

### 8.2 Fixture

| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增 fixture | 全部使用假对象与 `tmp_path` | 测试作者编写；不联网、不调用真实模型 |

## 9. 验收

### 9.1 命令与期望输出

```bash
cd core && uv run pytest tests/unit/app -q
# 期望：11 passed，0 failed
cd .. && scripts/check.sh
# 期望：exit=0；test_layering 无违规；mypy strict 全绿
```

### 9.2 完成清单

- [ ] `python -m sentinel --help` 可用，未知参数退出码 2
- [ ] 38 个业务方法 + 2 个内置方法 = 40 全部注册；两处数量断言存在
- [ ] 构造顺序固定；业务包不反向导入 `sentinel.app`
- [ ] 迁移失败退出码 3；启动恢复只调用一次
- [ ] `app.ready` 在迁移与恢复之后发送
- [ ] 已写 `docs/wp/status/C-07.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| C-02 | 默认命令 `python -m sentinel` | 进程参数由 C-02 注入；组合根不读环境变量 |
| I-01 | 真实进程启动 | 不修改 `app/`；只通过 RPC 驱动 |
| U-00 | `app.bootstrap` | 字段由 C-04 提供，组合根只负责装配 |
| E-01 | `app/methods/demo.py` | 该文件属于本包；E-01 只提供 `METHODS` |


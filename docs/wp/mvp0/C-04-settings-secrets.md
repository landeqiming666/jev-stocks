---
id: C-04
title: 设置与密钥：settings.*、secrets.*、app.bootstrap
phase: mvp0
platform: shared
lane: core
deps: [C-01, C-03]
size: M
owns: [core/sentinel/settings/__init__.py, core/sentinel/settings/models.py, core/sentinel/settings/repository.py, core/sentinel/settings/service.py, core/sentinel/settings/rpc.py, core/sentinel/secrets/__init__.py, core/sentinel/secrets/store.py, core/sentinel/secrets/service.py, core/tests/unit/settings/, core/tests/unit/secrets/test_secrets.py]
appends: []
stubs: []
---

# C-04 设置与密钥：settings.*、secrets.*、app.bootstrap
## 0. 一眼看懂
- **目标**：实现设置读写、校验、系统钥匙串、连接测试和 `app.bootstrap`，并把这 7 个方法注册到 C-01 的分发器。
- **完成后解锁**：P-02、W-04、I-01；设置页、启动外壳和扫描前置检查可以接真实数据。
- **预计规模**：实现约 430 行，测试约 280 行；设置与密钥各 3 个模块，2 个测试目录。
## 1. 背景与边界
### 1.1 为什么需要它
设置是扫描的前置条件，密钥是唯一的敏感数据。若设置写进密钥表、或 `app.bootstrap` 临时拼字段，界面会显示过期配置；若密钥可被查询接口读回，任何前端漏洞都会直接泄露密钥。C-04 把设置当作 JSON 键值，把密钥只放进系统钥匙串，并固定 bootstrap 的 wire 形状。
### 1.2 范围内
1. 读取、校验和原子更新 `setting` 表的 8 个键。
2. `settings.get`、`settings.update`、`settings.testConnection`。
3. `secrets.set`、`secrets.clear`、`secrets.status`，密钥永不回传。
4. `app.bootstrap` 的完整 `Bootstrap` 对象和 `app.bootstrap` 处理器。
5. 用注入的连接探针实现 Jev、SEC、JEVDB 三项测试，不在本包发起网络请求。
6. 注册 7 个 RPC 处理器；参数模型使用 `extra="forbid"`。
### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| Jev 直连、JEVDB 加载、扫描和 HTTP 请求 | S-03、S-04、P-02、D-01 |
| 设置页 UI 和密钥输入框 | U-07 |
| Windows 凭据管理器实测 | W-04 |
| 修改模型 ID 或问题集版本 | 只能通过代码常量变更与 ADR-015 |
| 诊断包导出 | v1 |
| 把密钥写入数据库、日志、测试 fixture | 永远禁止 |
## 2. 必读
| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [04-数据模型.md](../../04-数据模型.md) | 3.1 `setting`、5 设置项、6 删除与保留、7 完整性 | 键、默认值、校验范围 |
| [05-接口契约.md](../../05-接口契约.md) | 3 错误、4 公共类型、5.1 生命周期、5.2 设置与密钥 | 字段和错误码 |
| [02-技术架构.md](../../02-技术架构.md) | 1 外部域名、10 存储与目录、13 安全 | `allowedDomains` 与钥匙串 |
| [09-测试与评测.md](../../09-测试与评测.md) | 2.2 确定性、5 密钥不泄露 | 测试注入与断言 |
## 3. 前置条件
- C-01 已合并：`Dispatcher.register`、`RequestContext`、`MethodSpec` 可用。
- C-03 已合并：`Database.write()`、`schema_version` 可用。
- WP-00 已锁定 `keyring`、`pydantic` 和 `tzdata`；不得新增依赖。
- 测试使用 `keyring` 的内存后端或 `MemorySecretStore`，不写真实钥匙串。
## 4. 交付物清单
| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/settings/__init__.py` | 新建 | 导出 `SettingsService`、`Settings`、`register` |
| `core/sentinel/settings/models.py` | 新建 | `Settings`、`SettingsPatch`、`Bootstrap`、`ConnectionTestResult` |
| `core/sentinel/settings/repository.py` | 新建 | `setting` 表的 JSON 读写与原子更新 |
| `core/sentinel/settings/service.py` | 新建 | 默认值、校验、bootstrap、连接测试编排 |
| `core/sentinel/settings/rpc.py` | 新建 | 7 个 RPC 处理器与 `register()` |
| `core/sentinel/secrets/__init__.py` | 新建 | 导出 `SecretStore`、`SecretsService` |
| `core/sentinel/secrets/store.py` | 新建 | `KeyringSecretStore` 与 `MemorySecretStore` |
| `core/sentinel/secrets/service.py` | 新建 | 单向写入、清除、脱敏登记、状态 |
| `core/tests/unit/settings/test_settings.py` | 新建 | 设置与 bootstrap 测试 |
| `core/tests/unit/settings/test_rpc.py` | 新建 | 7 个处理器注册与 wire 字段 |
| `core/tests/unit/secrets/test_secrets.py` | 新建 | 密钥测试 |
## 5. 接口规格
### 5.1 公开接口
```python
class SettingsRepository:
    def __init__(self, db: Database) -> None: ...
    def raw(self) -> dict[str, object]: ...
    def write_patch(self, values: Mapping[str, object], now: datetime) -> None: ...
@dataclass(frozen=True)
class EngineSnapshot:
    requested: Literal["auto", "jevdb", "jev_direct"]
    active: Literal["jevdb", "jev_direct"] | None
    jevdb_available: bool
class SettingsService:
    def __init__(self, repo: SettingsRepository, clock: Callable[[], datetime]) -> None: ...
    def get(self) -> Settings: ...
    def update(self, patch: SettingsPatch) -> Settings: ...
    def bootstrap(self, engine: EngineSnapshot, secrets: "SecretsService",
                  db: Database, platform_name: str, offline: bool) -> Bootstrap: ...
    def test_connection(self, probe: "ConnectionProbe",
                        engine: EngineSnapshot) -> ConnectionTestResult: ...
class SecretStore(Protocol):
    def get(self, account: str) -> str | None: ...
    def set(self, account: str, value: str) -> None: ...
    def delete(self, account: str) -> None: ...
class SecretsService:
    def __init__(self, store: SecretStore, clock: Callable[[], datetime]) -> None: ...
    def set_jev_key(self, value: str) -> None: ...
    def clear_jev_key(self) -> None: ...
    def status(self) -> dict[str, bool]: ...
    def get_jev_key(self) -> str | None: ...
class ConnectionProbe(Protocol):
    def check_jev(self, model_id: str) -> ProbeResult: ...
    def check_sec(self, email: str) -> ProbeResult: ...
    def check_jevdb(self) -> ProbeResult: ...
def register(dispatcher: Dispatcher, settings: SettingsService, secrets: SecretsService,
             db: Database, platform_name: str, engine: EngineSnapshot,
             probe: ConnectionProbe) -> None: ...
```
`SettingsPatch` 的字段只有 `engine`、`secContactEmail`、`dailyTokenBudget`、`firstScanLookbackDays`；`extra="forbid"`。`update` 先校验完整 patch，再在一个 `Database.write()` 中写入变化的键；未知字段、超范围值和非法邮箱都抛 `UserError("INVALID_ARGUMENT")`，`data.field` 指向第一个字段。`bootstrap` 只读，不写数据库。`get_jev_key` 仅供核心进程内部调用，不能注册成 RPC。
### 5.2 数据结构
| 结构 | 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|---|
| `Settings` | `engine` | str | 是 | `auto`/`jevdb`/`jev_direct` | 请求引擎 |
| | `modelId` | str | 是 | 固定 `jev-1.14.0` | 模型版本 |
| | `secContactEmail` | str/null | 是 | ≤120，合法邮箱或 null | SEC 联系邮箱 |
| | `dailyTokenBudget` | int | 是 | 10,000–50,000,000 | 每日 token 限额 |
| | `firstScanLookbackDays` | int | 是 | 1–30 | 首次回看天数 |
| | `demoDataLoaded` | bool | 是 | 只读 | 演示数据状态 |
| | `language` | str | 是 | 固定 `zh-CN` | 界面语言 |
| | `allowedDomains` | `DomainRule[]` | 是 | 只读，5 项 | 外联说明 |
| `Bootstrap` | `protocolVersion` | str | 是 | `1.0` | 协议版本 |
| | `appVersion` | str | 是 | `sentinel.__version__` | 应用版本 |
| | `dbSchemaVersion` | int | 是 | `db.schema_version` | 数据库版本 |
| | `platform` | str | 是 | `macos`/`windows` | 平台 |
| | `engine` | object | 是 | requested/active/modelId/jevdbAvailable | 引擎状态 |
| | `markets` | str[] | 是 | `["us"]` | 可用市场 |
| | `configured` | object | 是 | jevKey/secEmail | 配置状态 |
| | `demoDataLoaded` | bool | 是 | 来自设置 | 演示状态 |
| | `offline` | bool | 是 | `SENTINEL_OFFLINE=1` | 离线 |
| | `now` | str | 是 | 以 `Z` 结尾 | 核心时间 |
### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MODEL_ID` | `"jev-1.14.0"` | `settings/models.py` | 唯一模型版本 |
| `DEFAULT_ENGINE` | `"auto"` | `settings/service.py` | 默认引擎 |
| `DEFAULT_BUDGET` | `2_000_000` | 同上 | 默认预算 |
| `DEFAULT_LOOKBACK` | `7` | 同上 | 默认回看 |
| `KEYRING_SERVICE` | `"sentinel"` | `secrets/store.py` | 系统服务名 |
| `KEYRING_ACCOUNT` | `"typesafe_api_key"` | 同上 | 账号名 |
| `MAX_SECRET_CHARS` | `512` | `secrets/service.py` | 密钥上限 |
## 6. 实现步骤
1. **默认设置**：键不存在时返回 [04] §5 的默认值；`modelId`、`demoDataLoaded` 只从常量/数据库读取；`allowedDomains` 按 [02] §1 返回 5 条，`modelId` 缺省为 `jev-1.14.0`。
2. **读取**：一次 `db.read()` 查出全部 `setting` 行，用 `json.loads(value_json)`；JSON 损坏时抛 `InternalError("INTERNAL", detail="setting:<key>")`，不猜测默认值。
3. **校验 patch**：`engine` 只允许三个枚举；邮箱用 `^[^@\s]+@[^@\s]+\.[^@\s]+$`，去首尾空白，空串转 `null`；预算 10,000–50,000,000；回看 1–30。失败立即返回，不写任何键。
4. **原子更新**：把变化的键序列化为 `json.dumps(value, ensure_ascii=False, separators=(",",":"))`；同一事务 `INSERT ... ON CONFLICT DO UPDATE`，`updated_at` 使用同一个 `clock.now()`；提交后重新 `get()`。
5. **密钥写入**：`value.strip()` 后长度 1–512，且 `re.search(r"\s", value)` 必须为 `None`；否则 `INVALID_ARGUMENT`。调用 `store.set("typesafe_api_key", value)`，再 `register_secret(value)`；成功响应只有 `{ok:true}`。
6. **密钥清除**：`store.delete`，`clear_secrets()`；重复清除仍返回 `{ok:true}`。`status()` 只调用 `store.get` 判断非空，不把值返回给 RPC 层。
7. **连接测试**：先检查密钥和邮箱；缺失抛 `CONFIG_REQUIRED`，`data.missing` 按 `jevKey`、`secEmail` 顺序。否则依次调用 `check_jev(MODEL_ID)`、`check_sec(email)`、`check_jevdb()`，固定返回三项 `{name, ok, latencyMs, message}`；`ok = jev.ok and sec.ok and engine.active is not None`。
8. **bootstrap**：读取设置和 `secrets.status()`，构造 [05] §4 的 `Bootstrap`；数据库版本用 `db.schema_version`；平台用参数；`offline` 只由环境变量 `SENTINEL_OFFLINE == "1"` 决定；`now` 用 `clock.now()`。没有密钥时 `engine.active` 强制为 `null`。
9. **注册**：`register()` 依次注册 `app.bootstrap`（30 s）、`settings.get`、`settings.update`、`settings.testConnection`（20 s）、`secrets.set`、`secrets.clear`、`secrets.status`；重复注册不允许，参数模型全部 `extra="forbid"`。
## 7. 错误与边界情况
| 情形 | 行为 | 错误码 | 用户文案键 |
|---|---|---|---|
| 未知 patch 字段 | 整个 patch 拒绝 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 邮箱格式错误 | `data.field="secContactEmail"` | `INVALID_ARGUMENT` | `settings.email_invalid` |
| 预算或回看越界 | 不写任何键 | `INVALID_ARGUMENT` | `error.INVALID_ARGUMENT` |
| 缺少密钥或邮箱 | 不执行 probe | `CONFIG_REQUIRED` | `error.CONFIG_REQUIRED` |
| 密钥含空白或超长 | 不写钥匙串 | `INVALID_ARGUMENT` | `settings.secret_invalid` |
| 系统钥匙串不可用 | 保留旧密钥不变 | `INTERNAL` | `settings.keyring_unavailable` |
| 设置 JSON 损坏 | 不静默覆盖 | `INTERNAL` | `settings.data_corrupt` |
| JEVDB probe 失败 | 仍可 `ok=true`，仅该项 false | — | `settings.jevdb_fallback` |

## 8. 测试（先写）
### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_defaults_match_docs_04` | `test_settings.py` | 空 `setting` 表 | `engine=="auto"`、`modelId=="jev-1.14.0"`、预算 `2000000`、回看 `7` |
| `test_update_writes_only_changed_keys` | 同上 | `dailyTokenBudget=3000000` | 只有该键变化；返回预算 3,000,000 |
| `test_invalid_email_has_field` | 同上 | `secContactEmail="not-an-email"` | `INVALID_ARGUMENT`，`field=="secContactEmail"` |
| `test_unknown_patch_field_is_rejected` | 同上 | `{"modelId":"x"}` | `INVALID_ARGUMENT`，没有任何写入 |
| `test_budget_out_of_range_is_rejected` | 同上 | `10000` 与 `50000001` | 后者 `INVALID_ARGUMENT` |
| `test_secret_is_never_returned` | `test_secrets.py` | `set_jev_key("<secret>")` 后 `status()` | `{"jevKey":True}`，响应不含 `<secret>` |
| `test_secret_rejects_whitespace` | 同上 | `"sk test"`（密钥内部空白） | `INVALID_ARGUMENT`，钥匙串没有写入；首尾空白按 05 §5.2 先 strip 后校验 |
| `test_bootstrap_fields_match_contract` | `test_settings.py` | 已配置、`engine=auto/active=jev_direct`、db version 1 | 10 个字段与 [05] §4 示例名 `ready` 一致 |
| `test_bootstrap_unconfigured_has_no_active_engine` | 同上 | 无密钥 | `configured.jevKey is False`，`engine.active is None` |
| `test_connection_ok_when_jevdb_missing` | 同上 | Jev 412 ms、SEC 236 ms、JEVDB false | `ok is True`，检查顺序 `Jev,SEC,JEVDB` |
| `test_connection_false_when_jev_fails` | 同上 | Jev 401、SEC ok | `ok is False`，Jev 项 `ok=False` |
| `test_register_installs_seven_methods` | `test_rpc.py` | 调用 `register()` | dispatcher 方法集合等于 7 个名字 |
### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无新增文件 | `Database` 用 `tmp_path`；钥匙串用 `MemorySecretStore` | 测试内构造 |
| `FakeProbe` | `check_jev`/`check_sec`/`check_jevdb` 返回固定 `ProbeResult` | 测试内类，不联网 |
## 9. 验收
### 9.1 命令与期望输出
```bash
cd core
uv run pytest tests/unit/settings tests/unit/secrets -q
# 期望：12 passed，0 failed
uv run ruff check sentinel/settings sentinel/secrets
# 期望：exit=0
```
### 9.2 完成清单
- [ ] 第 4 节每个文件已创建
- [ ] 第 8.1 节 12 个测试全部存在且通过
- [ ] `settings.get` 和 `app.bootstrap` 不返回任何密钥明文
- [ ] `Bootstrap` 字段与 [05] §4 的 10 个字段逐一对应
- [ ] 没有修改 `owns` 之外的路径，没有新增依赖
- [ ] 已写 `docs/wp/status/C-04.md`
## 10. 给下游的交接
| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| P-02 | `SettingsService.get()`、`SecretsService.status()`、`SettingsService.bootstrap()` | 扫描前先检查 `CONFIG_REQUIRED` |
| S-03、S-04 | `SecretsService.get_jev_key()` | 只在创建引擎时调用，不记录返回值 |
| W-04 | `KeyringSecretStore` | `sentinel/typesafe_api_key` 的读写行为必须与 macOS 一致 |
| U-07 | 7 个 RPC 方法与 `allowedDomains` | 密钥只显示“已保存”，不显示值 |
| I-01 | `register()` | 装配根负责把 `SettingsService` 与真实 `EngineSnapshot` 接上 |

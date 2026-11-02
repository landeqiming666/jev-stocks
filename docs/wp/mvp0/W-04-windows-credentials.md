---
id: W-04
title: Windows 凭据管理器验证
phase: mvp0
platform: windows
lane: windows
deps: [W-01, C-04]
size: S
owns: [core/sentinel/secrets/windows_backend.py, core/tests/unit/secrets/test_windows_backend.py]
appends: []
stubs: []
---

# W-04 Windows 凭据管理器验证

## 0. 一眼看懂

- **目标**：证明 Jev 密钥使用 Windows Credential Locker 持久保存，重启和跨进程读取正常，删除后消失，且密钥不进入日志、数据库或错误信息。
- **完成后解锁**：W-05。
- **预计规模**：约 260 行，后端适配 90 行、测试 170 行。

## 1. 背景与边界

### 1.1 为什么需要它
`keyring` 的跨平台 API 不代表实际落到 Windows 凭据管理器；测试环境的内存后端会让单元测试全绿，但用户重启后密钥丢失。必须单独验证真实 WinVault 后端。

### 1.2 范围内
1. `WindowsCredentialBackend`：固定 service/account、强制 WinVault、CRUD 和探针。
2. Windows 上的真实凭据往返、跨进程读取、删除和日志/数据库泄漏检查。
3. 失败时的明确错误和人工凭据管理器截图。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 修改 C-04 的 `secrets.set/clear/status` 契约 | C-04 |
| 修改共享 `SecretStore` 或消息体系 | C-04；如缺注入点先提变更申请 |
| 保存 SEC 邮箱或 Jev 密钥明文 | 禁止 |
| 测试真实 Jev 认证 | G0-JEV |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [05-接口契约.md](../../05-接口契约.md) | 5.2 设置与密钥 | 单向写入与返回 |
| [02-技术架构.md](../../02-技术架构.md) | 10 数据目录、11 日志、13 安全 | 存储与脱敏 |
| [09-测试与评测.md](../../09-测试与评测.md) | 2.2 确定性、5 安全与隔离 | 假密钥与内存后端 |
| [01-产品需求.md](../../01-产品需求.md) | US-05、WM-4 | Windows 验收 |
| [W-01-windows-platform-layer.md](W-01-windows-platform-layer.md) | 5.4 PowerShell 编码 | Windows 测试运行方式 |

## 3. 前置条件

- C-04 已提供 `CredentialBackend` 协议，并允许 `SecretStore(backend=...)` 注入；未提供时停止并提接口变更申请。
- Windows Python 环境已安装 `keyring`，`keyring.backends.Windows.WinVaultKeyring` 可导入。
- 测试账户使用唯一后缀；每个测试 `finally` 删除凭据。
- 测试只使用 `test-key-do-not-use-*`，禁止真实密钥。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/secrets/windows_backend.py` | 新建 | WinVault 适配、CRUD、可用性探针 |
| `core/tests/unit/secrets/test_windows_backend.py` | 新建 | Windows 真实凭据测试 |

`core/sentinel/secrets/` 的包初始化由 C-04 负责；本包不得创建或修改 `__init__.py`。

## 5. 接口规格

### 5.1 公开接口
```python
class CredentialBackendUnavailable(RuntimeError): ...
class CredentialBackendError(RuntimeError): ...

@dataclass(frozen=True)
class CredentialProbeResult:
    backend: str; service: str; account: str
    write_ok: bool; read_ok: bool; delete_ok: bool

class WindowsCredentialBackend:
    SERVICE = "sentinel"
    ACCOUNT = "typesafe_api_key"

    def __init__(self, *, service: str = SERVICE, account: str = ACCOUNT) -> None: ...
    def set(self, value: str) -> None: ...
    def get(self) -> str | None: ...
    def delete(self) -> None: ...
    def exists(self) -> bool: ...
    def probe(self) -> CredentialProbeResult: ...
```
构造时延迟导入 `WinVaultKeyring`，模块本身可在 macOS 导入。`set` 拒绝空串、超过 512 字符、含 CR/LF 的值；异常只保留错误类型与 Win32 错误码，不保留 secret。`probe` 使用唯一临时 account，验证写读删后恢复默认 account。

### 5.2 数据结构
| 字段 | 类型 | 必填 | 约束 | 含义 |
|---|---|---|---|---|
| `service` | str | 是 | 默认 `sentinel`，非空 | 凭据服务名 |
| `account` | str | 是 | 默认 `typesafe_api_key`，非空 | 凭据账户名 |
| `backend` | str | 是 | 固定 `Windows Credential Locker` | 实际后端 |
| `writeOk/readOk/deleteOk` | bool | 是 | 三项均 true 才健康 | 探针结果 |
| `secret` | str | 否 | 1–512，无 CR/LF | 仅函数局部变量 |

### 5.3 常量与配置
| 名称 | 值 | 位置 | 含义 |
|---|---|---|---|
| `SERVICE` | `"sentinel"` | `windows_backend.py` | 与 C-04 一致 |
| `ACCOUNT` | `"typesafe_api_key"` | `windows_backend.py` | 与设置契约一致 |
| `MAX_SECRET_CHARS` | `512` | `windows_backend.py` | 上限 |
| `TEST_PREFIX` | `"sentinel-test-"` | 测试 | 唯一测试账户 |
| `PROBE_TIMEOUT_S` | `10` | 测试 | 单次系统调用超时 |

## 6. 实现步骤

1. 先写全部测试，并用内存后端运行，确认测试能识别“不是 WinVault”的失败。
2. `WindowsCredentialBackend.__init__` 延迟导入 `WinVaultKeyring`；导入失败抛 `CredentialBackendUnavailable("WinVault backend is unavailable")`。
3. 实例化后检查类名包含 `WinVaultKeyring` 且 `priority > 0`；否则视为后端错误。
4. `set` 校验值后调用 `backend.set_password(service, account, value)`；不缓存值。
5. `get` 返回 `backend.get_password(...)`；无记录返回 `None`；异常包装为 `CredentialBackendError`，不把 secret 拼进 message。
6. `delete` 在不存在时视为成功；`exists` 用 `get() is not None`，不得把值写入日志。
7. `probe` 生成 `sentinel-test-<ULID>` account，写 `test-key-do-not-use-<ULID>`，读回比较，删除后确认 `None`，在 `finally` 再删一次。
8. 测试通过 C-04 的 `SecretStore(backend=WindowsCredentialBackend())` 做一次 `secrets.set`；任何返回都不得包含密钥。
9. 用 `subprocess.run([sys.executable, "-c", script], env={...})` 在新进程读取；脚本只比较并用 0/1 退出，不打印值。
10. 触发一次 `CredentialBackendError`，断言 `str(exc)`、traceback、JSON 日志均不含假密钥。
11. 若数据目录存在 `core.jsonl` 或 `sentinel.duckdb`，递归搜索假密钥，命中即失败。
12. 人工打开“控制面板 → 凭据管理器 → Windows 凭据”，在设置假凭据后截图，删除后再截图；状态文件记录路径。

## 7. 错误与边界情况

| 情形 | 行为 | 错误 | 用户可见文案（messages 键） |
|---|---|---|---|
| 非 Windows 导入模块 | 允许导入，不初始化 | — | 不适用 |
| WinVault 不可用 | 不落内存后端 | `CredentialBackendUnavailable` | C-04 映射 `error.INTERNAL` |
| 凭据被系统策略禁用 | 保留 Win32 错误码 | `CredentialBackendError` | `error.INTERNAL`，带错误编号 |
| 值为空或超过 512 | 不调用系统 API | `ValueError` | C-04 `error.INVALID_ARGUMENT` |
| 删除不存在条目 | 成功 | — | 不显示错误 |
| 读取到非字符串 | 删除并报错，不返回 | `CredentialBackendError` | `error.INTERNAL` |
| 测试中断 | `finally` 清理测试 account | — | 不适用 |

## 8. 测试（先写）

### 8.1 测试清单
| 测试名 | 文件 | 输入 | 期望 |
|---|---|---|---|
| `test_winvault_is_active_backend` | `test_windows_backend.py` | 默认构造 | 类名含 `WinVaultKeyring`，priority > 0 |
| `test_set_get_delete_roundtrip` | 同上 | 假密钥 | 读回完全相等；删除后 `None` |
| `test_secret_survives_new_process` | 同上 | 新 Python 进程 | 子进程退出 0，不打印 secret |
| `test_delete_removes_credential` | 同上 | 写入后删除 | `exists()` false |
| `test_no_secret_in_logs_or_database` | 同上 | 触发一次后端错误 | 日志和临时 DuckDB 均不含 secret |
| `test_error_message_never_contains_secret` | 同上 | 注入抛错 backend | message 与 `repr` 均不含 secret |
| `test_service_and_account_are_exact` | 同上 | 默认配置 | `sentinel` / `typesafe_api_key` |
| `test_probe_reports_all_steps_true` | 同上 | 真实 WinVault | 三 bool 全 true，临时条目已删除 |

### 8.2 Fixture
| 路径 | 内容与来源 | 怎么得到 |
|---|---|---|
| 无磁盘 secret fixture | `test-key-do-not-use-<ULID>` 运行时生成 | 不写入仓库 |
| `tmp_path/core.jsonl` | 一条脱敏日志 | 测试构造 |
| `tmp_path/sentinel.duckdb` | 空库/设置表 | 测试构造 |

## 9. 验收

### 9.1 命令与期望输出
```powershell
cd core
uv run pytest tests\unit\secrets\test_windows_backend.py -q -m windows
# 期望：8 passed；0 failed
uv run python -c "from sentinel.secrets.windows_backend import WindowsCredentialBackend; print(WindowsCredentialBackend().probe())"
# 期望：backend=Windows Credential Locker；write/read/delete 均 True
scripts\check.ps1
# 期望：失败 0
```

### 9.2 完成清单
- [ ] 8 个测试全部存在，先失败证据已记录
- [ ] 凭据跨新进程可读，删除后不可读
- [ ] 日志、数据库、异常输出中无假密钥
- [ ] 凭据管理器前后截图已保存
- [ ] 未修改 C-04 的 RPC 或共享接口
- [ ] 已写 `docs/wp/status/W-04.md`

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| W-05 | `probe()`、跨进程测试 | 真实密钥不得用于自动测试 |
| C-04 维护者 | 后端注入点 | 若接口缺失只提变更申请，不在本包补共享代码 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| `keyring` 选择内存后端 | 测试重启后条目丢失 | 强制 WinVault；仍不可用则标 WM-4 fail |
| 凭据管理器策略禁用 | `cmdkey` 或 keyring 拒绝 | 记录环境限制，改用有权限的 Windows 机器重测 |
| 测试账户残留 | Credential Locker 出现 `sentinel-test-*` | `finally` 清理；状态文件附 `cmdkey /list` 复核 |

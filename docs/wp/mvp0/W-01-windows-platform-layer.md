---
id: W-01
title: Windows 平台层实现
phase: mvp0
platform: windows
lane: windows
deps: [WP-00, W-00]
size: M
owns: [core/sentinel/platform/windows.py, apps/desktop/src-tauri/src/platform/windows.rs, apps/desktop/src-tauri/tauri.windows.conf.json, apps/desktop/src/styles/platform-windows.css, scripts/check.ps1, scripts/setup.ps1, scripts/dev.ps1, scripts/doctor.ps1, scripts/_py.ps1, scripts/tests/test_ps1_wrappers.py, core/tests/platform/test_windows_platform.py, core/tests/platform/__init__.py]
appends: [docs/wp/windows-dev-notes.md]
---

# W-01 Windows 平台层实现

C-02 已追加 `Platform::open_external`，默认 Unsupported。Windows 车道实现时应在自己的 `windows.rs` 覆盖该方法并验证安全打开 HTTPS；Mac 本批未声称 Windows 外链接缝已完成。通用钥匙串原子测试文件由 C-04 所有，不再由 W-01 独占整个 `core/tests/platform/`。

## 0. 一眼看懂

- **目标**：接手 WP-00 留下的 8 个 Windows 占位文件，把它们实现成真正可用的版本，让 Windows 上 `scripts\check.ps1` 全绿、`scripts\dev.ps1` 能弹出窗口。
- **完成后解锁**：W-02（对等验证）、W-03（JEVDB 的 MSVC 构建）、W-04（凭据管理器验证）。
- **预计规模**：约 350 行（Python 约 120、Rust 约 70、PowerShell 约 90、测试约 150，部分重叠）。
- **谁做**：Windows 车道的那一个人。**本工作包在 macOS 上无法验证**，所有标 `TODO-VERIFY(W-01)` 的写法必须在 Windows 上实测，写错就改，并把最终写法记入状态文件。

## 1. 背景与边界

### 1.1 为什么需要它
[ADR-016](../../decisions.md) 规定平台差异只能在平台层。WP-00 为 Windows 留了占位，让工程在两个系统上都能编译。W-01 把占位变成真实现。

### 1.2 范围内
1. `windows.py` 的五个函数。
2. `windows.rs` 的五个方法。
3. `tauri.windows.conf.json`、`platform-windows.css` 的最终内容。
4. 五个 PowerShell 脚本。
5. Windows 专属的测试。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 修改 `platform/__init__.py` 或 `Platform` trait 的接口 | 禁止；需要改走变更申请 |
| 修改共享代码 | 提交最小修复 + 复现测试，并走变更申请（见 [10](../../10-协作与工作包规范.md) 第 9 节） |
| NSIS 安装包、托盘、自启 | v1 的 W-10、W-11 |
| JEVDB 构建 | W-03 |
| 凭据管理器的验证 | W-04（`keyring` 本身是共享代码，W-04 只验证它在 Windows 上的行为） |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [WP-00-skeleton.md](WP-00-skeleton.md) | 5.2 平台层 Python 接口、5.9 `Platform` trait、5.10 `check.py`、5.14 隔离检查 | 你要实现的接口和行为定义 |
| [02-技术架构.md](../../02-技术架构.md) | 9 平台层 | 差异表 |
| `docs/wp/status/W-00.md`（由 W-00 产出，此前不存在） | 失败分类表中的 A 类 | 你要清零的清单 |
| `docs/wp/windows-dev-notes.md`（由 W-00 产出，此前不存在） | 执行策略小节 | 决定 `.ps1` 的用法说明 |

## 3. 前置条件

- W-00 已完成（它的状态文件与开发笔记存在）。
- Windows 机器上 `py -3 scripts\check.py` 至少能启动（即使有 A 类失败）。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/sentinel/platform/windows.py` | 覆盖占位 | 五个函数的 Windows 实现 |
| `apps/desktop/src-tauri/src/platform/windows.rs` | 覆盖占位 | `Platform` trait 的 Windows 实现 |
| `apps/desktop/src-tauri/tauri.windows.conf.json` | 覆盖占位 | Windows 专属 Tauri 配置 |
| `apps/desktop/src/styles/platform-windows.css` | 覆盖占位 | Windows 专属样式变量 |
| `scripts/_py.ps1` | 新建 | 找到 Python ≥ 3.9 的辅助函数 |
| `scripts/check.ps1` `setup.ps1` `dev.ps1` `doctor.ps1` | 覆盖占位 | 各自转调同名 `.py` |
| `core/tests/platform/test_windows_platform.py` | 新建 | `windows.py` 的测试 |
| `core/tests/platform/__init__.py` | 新建 | 空文件（使目录成为包，conftest 的平台标记才能生效） |
| `scripts/tests/test_ps1_wrappers.py` | 新建 | 包装脚本的测试 |
| `docs/wp/windows-dev-notes.md` | 追加 | 追加“PowerShell 脚本用法”和“已知坑”两小节 |
| `docs/wp/status/W-01.md` | 新建 | 完成报告 |

## 5. 接口规格

### 5.1 `windows.py`

签名与 [WP-00 的 5.2](WP-00-skeleton.md) 完全一致，行为如下：

| 函数 | 行为 |
|---|---|
| `name()` | 返回 `"windows"` |
| `default_data_dir()` | 读环境变量 `LOCALAPPDATA`，返回 `Path(LOCALAPPDATA) / "Sentinel"`；变量缺失时返回 `Path.home() / "AppData" / "Local" / "Sentinel"`。**不创建目录**。用 Local 而不是 Roaming，因为数据库文件不应该随域账户漫游 |
| `is_process_alive(pid)` | `pid <= 0` 返回 `False`。用 `ctypes.WinDLL("kernel32", use_last_error=True)` 调 `OpenProcess(0x1000, False, pid)`（`PROCESS_QUERY_LIMITED_INFORMATION`）。句柄为空：`ctypes.get_last_error()` 是 5（拒绝访问）→ `True`，其他 → `False`。句柄有效：`GetExitCodeProcess`，退出码等于 259（`STILL_ACTIVE`）→ `True`，否则 `False`；最后必须 `CloseHandle`。所有 `argtypes`/`restype` 必须显式声明，否则 64 位句柄会被截断 |
| `file_lock(path)` | 上下文管理器：父目录不存在则创建；以 `"a+b"` 打开；`msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)` 锁定从偏移 0 开始的 1 个字节；`OSError` 转成 `AlreadyRunning`（保留原异常为 `__cause__`）；退出时 `seek(0)` 再 `msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)`，然后关闭。**不删除锁文件** |
| `harden_permissions(path)` | 路径不存在抛 `FileNotFoundError`。否则只保留当前用户的完全控制：先 `whoami /user /fo csv /nh` 取当前用户 SID（第二列），再调用 `icacls <path> /inheritance:r /grant:r *<SID>:F`（目录用 `*<SID>:(OI)(CI)F`）。`icacls` 退出码非 0 抛 `OSError` 并带上它的输出。`TODO-VERIFY(W-01)`：`icacls` 参数在你的系统上实测；若写法不同，以实测为准并记入状态文件 |

`AlreadyRunning` 从 `sentinel.platform` 导入（`from sentinel.platform import AlreadyRunning`），**不要**在这个文件里重新定义。注意循环导入：`__init__.py` 在导入 `windows` 之前就已经定义了 `AlreadyRunning`，所以放在函数内部导入即可。

### 5.2 `windows.rs`

```rust
pub struct Windows;
impl Platform for Windows { /* 五个方法 */ }
```

| 方法 | 行为 |
|---|---|
| `name` | `"windows"` |
| `init_script` | 与 macOS 同结构，值为 `windows` |
| `configure_window` | `.decorations(true)`：使用原生标题栏。不设置 `TitleBarStyle`，也不隐藏标题 |
| `prepare_core_command` | `use std::os::windows::process::CommandExt;` 然后 `cmd.creation_flags(0x0800_0000)`（`CREATE_NO_WINDOW`），避免启动核心进程时弹出控制台窗口 |
| `kill_process_tree` | 用 `std::process::Command::new("taskkill").args(["/PID", &pid.to_string(), "/T", "/F"])` 并同样加 `CREATE_NO_WINDOW`，等待它结束；然后 `child.kill()`，忽略“已结束”的错误，最后 `child.wait()`。原因：开发模式的核心进程是 `uv run` 启动的 `python`，只杀 `uv` 会留下孤儿进程 |

`#[cfg(test)]` 单元测试放在同文件：`init_script_sets_windows_platform`（断言字符串包含 `"windows"`）。

### 5.3 配置与样式

`tauri.windows.conf.json` 保持 WP-00 的内容 `{ "bundle": { "targets": ["nsis"] } }`，只验证它在 `pnpm tauri dev` 下不报错；v1 的 W-10 再扩展。

`platform-windows.css` 保持 WP-00 的三个变量。若实测发现 Microsoft YaHei UI 在 WebView2 下的字重或行高与原型差异明显，**只在这个文件里**覆盖变量，并在状态文件里附前后截图。

### 5.4 PowerShell 脚本

**统一约束**

1. 文件编码 UTF-8 **带 BOM**，换行 CRLF（Windows PowerShell 5.1 对无 BOM 的 UTF-8 脚本会按系统代码页解析中文）。`.editorconfig` 已对 `*.ps1` 设为 `crlf`。
2. 每个脚本以 `$ErrorActionPreference = "Stop"` 开头；脚本末尾用 `exit $LASTEXITCODE` 原样返回被调用程序的退出码。
3. 用法说明（`-?` 之外）写在脚本顶部注释里，含执行策略的处理办法（来自 W-00 的实测结论）。

**`_py.ps1`**（被其他四个脚本用 `. "$PSScriptRoot\_py.ps1"` 引入）导出两个函数：

| 函数 | 行为 |
|---|---|
| `Get-SentinelPython` | 按顺序尝试 `py -3`、`python`、`python3`；对每个候选运行 `-c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"`，退出码 0 即选定，返回“可执行文件加前置参数”的数组。都不行则 `throw "找不到 Python >= 3.9。请安装 Python 并确保 py 或 python 在 PATH 中。"` |
| `Invoke-SentinelPython -Script <名> -Arguments <数组>` | 调用 `Get-SentinelPython`，运行 `"$PSScriptRoot\<名>"` 并传入全部参数，然后 `exit $LASTEXITCODE`。**参数必须逐个传递，不得拼接成一个字符串**（路径含空格） |

`TODO-VERIFY(W-01)`：PowerShell 数组展开（splatting）写法在 5.1 与 7 下都要实测。

**四个包装脚本**（`check.ps1`、`setup.ps1`、`dev.ps1`、`doctor.ps1`）：

```powershell
# 用法见文件顶部注释
. "$PSScriptRoot\_py.ps1"
Invoke-SentinelPython -Script "check.py" -Arguments $args
```

其他三个只换脚本名。每个文件 ≤ 15 行（含注释）。

### 5.5 `check.py` 在 Windows 上的要求（验证项，不是修改项）
WP-00 的 `check.py` 用 `shutil.which` 解析命令。Windows 上 `pnpm` 解析为 `pnpm.CMD`，用列表形式传给 `subprocess.run` 应当可以执行。**如果不行，这是共享代码的问题**：提交最小修复（一两行）+ 一个用假 `which` 返回 `.CMD` 路径的复现测试，并按协议提变更申请，**不要**改 `check.py` 的接口。

## 6. 实现步骤

1. **先写测试**（8.1 的全部用例），运行确认失败（`NotImplementedError`、脚本占位的非 0 退出码）。贴进状态文件。
2. **`windows.py`**：按 5.1 逐个实现，每实现一个就跑对应的测试，直到全绿。
3. **`windows.rs`**：实现五个方法；`cd apps\desktop\src-tauri && cargo test && cargo fmt --check && cargo clippy --all-targets -- -D warnings`。
4. **`_py.ps1` 与四个包装脚本**：先写 `doctor.ps1`（最简单），在 PowerShell 5.1 与 7（若装了）下各运行一次；再写其余三个。
5. **启动验证**：`scripts\dev.ps1`，应弹出原生标题栏的窗口，标题“投资逻辑哨兵”，开发者工具里 `document.documentElement.dataset.platform === "windows"`。关闭窗口后，**任务管理器里不应残留 `python.exe`、`uv.exe`、`node.exe`**（这里验证 `kill_process_tree`；但 C-02 之前核心进程还没有被启动，所以此项用手工运行 `uv run python -c "import time; time.sleep(60)"` 代替，见 8.1 的 Rust 手工项）。
6. **整体检查**：`scripts\check.ps1`，A 类失败必须清零；B 类项各有变更申请，不要求清零，但必须在状态文件列出。
7. **笔记**：向 `windows-dev-notes.md` 追加两个小节。
8. **状态文件**：按 [10](../../10-协作与工作包规范.md) 第 6 节。

## 7. 错误与边界情况

| 情形 | 行为 |
|---|---|
| `file_lock` 的路径已被同一进程的另一个调用持有 | 抛 `AlreadyRunning`（同进程内也互斥，这是测试依赖的行为） |
| `is_process_alive` 查询别的用户的进程 | `OpenProcess` 拒绝访问，返回 `True` |
| `harden_permissions` 的路径含空格或中文 | 必须正常工作；`icacls` 参数用列表传递，不拼字符串 |
| `whoami` 不可用 | 抛 `OSError("无法获取当前用户")` |
| PowerShell 找不到 Python | `Get-SentinelPython` 抛出中文错误，脚本退出码非 0 |
| 执行策略拦截 `.ps1` | 这是用法问题，不是缺陷；顶部注释已写明办法 |
| 仓库路径含空格 | 所有包装脚本必须正常工作 |

## 8. 测试（先写）

### 8.1 测试清单

**`core/tests/platform/test_windows_platform.py`**（整个文件标记 `pytestmark = pytest.mark.windows`）

| 测试名 | 输入 | 期望 |
|---|---|---|
| `test_name_is_windows` | — | `platform.name() == "windows"` |
| `test_default_data_dir_uses_localappdata` | `monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))` | `default_data_dir() == tmp_path / "Sentinel"`，且目录没有被创建 |
| `test_default_data_dir_falls_back_without_localappdata` | `monkeypatch.delenv("LOCALAPPDATA")` | 路径以 `AppData\Local\Sentinel` 结尾 |
| `test_is_process_alive_for_current_process` | `os.getpid()` | `True` |
| `test_is_process_alive_false_after_exit` | 启动 `python -c "pass"` 子进程并 `wait()` | 用其 pid 调用返回 `False` |
| `test_is_process_alive_false_for_invalid_pids` | `0`、`-1` | 都返回 `False` |
| `test_file_lock_is_exclusive_within_process` | 持有 `file_lock(p)` 时再进入 `file_lock(p)` | 抛 `AlreadyRunning`；退出外层后再进入成功 |
| `test_file_lock_is_exclusive_across_processes` | 子进程 `python -c` 持有同一个锁并 sleep 5 秒 | 主进程 `file_lock(p)` 抛 `AlreadyRunning` |
| `test_file_lock_creates_parent_directory` | `p = tmp_path / "a" / "b" / "x.lock"` | 成功，父目录被创建 |
| `test_harden_permissions_removes_broad_groups` | 对 `tmp_path / "d"` 调用后运行 `icacls` 读取 | 输出中不含 `Everyone`、`BUILTIN\Users`、`Authenticated Users`，且含当前用户 |
| `test_harden_permissions_missing_path_raises` | 不存在的路径 | `FileNotFoundError` |
| `test_harden_permissions_handles_spaces_and_unicode` | 目录名 `"含 空格 目录"` | 成功 |

**`apps/desktop/src-tauri/src/platform/windows.rs`**（`#[cfg(test)]`）

| 测试名 | 期望 |
|---|---|
| `init_script_sets_windows_platform` | `Windows.init_script().contains("windows")` |

**手工项（Rust，状态文件里附截图或输出）**

| 项 | 步骤 | 期望 |
|---|---|---|
| `kill_process_tree` 不留孤儿进程 | 在一个临时的 Rust 测试二进制或 `lib.rs` 的临时代码里，用 `prepare_core_command` + `Command::new("uv").args(["run","python","-c","import time; time.sleep(60)"])` 启动，随后调用 `kill_process_tree`。**临时代码不得提交** | 任务管理器里 `python.exe` 与 `uv.exe` 都消失，且没有弹出控制台窗口 |

**`scripts/tests/test_ps1_wrappers.py`**（用 `unittest.skipUnless(os.name == "nt", …)`。**注意**：这个测试文件在 `scripts/` 下，属于隔离检查的白名单，允许判断平台）

| 测试名 | 输入 | 期望 |
|---|---|---|
| `test_doctor_ps1_runs_and_mentions_uv` | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\doctor.ps1` | 退出码为 0 或 1（取决于机器缺不缺工具），输出包含 `uv` |
| `test_check_ps1_list_prints_all_steps` | `… check.ps1 --list` | 退出码 0，输出含 `docs`、`py-test`、`web-lint`、`rust-clippy` |
| `test_wrapper_passes_arguments_with_spaces` | `… check.ps1 --only docs`，工作目录含空格 | 退出码 0 |
| `test_wrapper_exit_code_is_propagated` | `… check.ps1 --only no-such-step` | 退出码非 0（`check.py` 对未知步骤名应报错，如果 WP-00 的实现没有，记为 B 类问题） |
| `test_every_ps1_wrapper_has_a_sh_pair` | 扫描 `scripts/` | 除下划线开头的辅助脚本外，每个 `.ps1` 都有同名 `.sh` |

### 8.2 Fixture
无。

## 9. 验收

### 9.1 命令与期望输出

```powershell
# 在 Windows 11 x64，仓库路径含空格
scripts\setup.ps1
# 期望：退出码 0；core\uv.lock、apps\desktop\pnpm-lock.yaml 未被改动（git status 干净）

scripts\check.ps1
# 期望：每行 PASS 或 SKIP；汇总 "失败 0"（B 类项已有变更申请的，允许在状态文件里列为"已知失败"，但不得是 A 类）

cd core
uv run pytest -q tests\platform
# 期望：12 passed

cd ..\apps\desktop\src-tauri
cargo test
# 期望：init_script_sets_windows_platform ... ok

cd ..\..\..
scripts\dev.ps1
# 期望：弹出原生标题栏窗口；dataset.platform 为 "windows"
```

### 9.2 完成清单
- [ ] 第 4 节每个文件都已创建或覆盖，`owns` 之外没有改动（`appends` 只追加了笔记）
- [ ] 8.1 的全部自动化测试都存在，状态文件里有“先失败”的证据
- [ ] 手工项（`kill_process_tree`）已完成并附证据
- [ ] 所有标 `TODO-VERIFY(W-01)` 的写法都已实测，最终写法记入状态文件
- [ ] `.ps1` 文件为 UTF-8 带 BOM、CRLF
- [ ] 在 PowerShell 5.1 与 7（若已装）下都运行过 `doctor.ps1`
- [ ] 没有修改 `platform/__init__.py`、`platform/mod.rs` 或任何共享代码
- [ ] 已写 `docs/wp/status/W-01.md`；发现的共享代码问题各有变更申请
- [ ] 已更新 `docs/wp/windows-matrix.md` 中 WP-00 与 W-01 的行

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| C-01 | `platform.file_lock`、`platform.is_process_alive` | 在 Windows 上行为与 macOS 一致 |
| C-02 | `Platform::prepare_core_command`、`kill_process_tree`、`init_script` | 核心进程启动不弹控制台窗口，退出不留孤儿 |
| W-02、W-03、W-04 | 可用的 `check.ps1`、`dev.ps1` | — |
| v1 W-10 | `tauri.windows.conf.json` | 在此基础上扩展 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| `msvcrt.locking` 在某些文件系统（网络盘、OneDrive 同步目录）上行为异常 | 锁测试偶发失败 | 测试一律用本地临时目录；笔记里提醒不要把数据目录放在同步盘 |
| PowerShell 5.1 与 7 行为不同 | 同一脚本在两处结果不同 | 以 5.1 为准（Windows 自带），7 作为额外验证 |
| `icacls` 权限设置后当前用户反而不能访问 | 之后的读写失败 | 立即还原（`icacls <path> /reset`），改为只移除 `Users` 与 `Everyone` 的授权，并在状态文件解释 |

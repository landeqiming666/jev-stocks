# Windows 开发笔记

- 日期：2026-11-02（Asia/Shanghai）
- 工作包：W-00
- 验证基线：`5b79539708557884c925138daa4776d1b2321c7c`
- 工程路径：`<工作区>/JEV Stocks`，包含中文父目录和空格。
- 结果与失败分类见 [W-00 完成报告](status/W-00.md)；整体状态见 [Windows 对等矩阵](windows-matrix.md)。

本文的 `<工作区>` 表示本地工作区根目录。工具与原始日志保存在工程仓库之外的 `<工作区>/tools/w00`、`<工作区>/tmp/w00-evidence`，未将个人绝对路径或主机名写入交付文档。

## 1. 机器信息

| 项目 | 本次实测 |
|---|---|
| 操作系统 | Windows 11 家庭中文版，25H2 |
| 系统版本 | build 26200.9711 |
| CPU | Intel Core Ultra 9 275HX |
| 架构 | AMD64 / x86_64 |
| 系统可见内存 | 32,900,652 KiB，约 31.38 GiB |
| 磁盘 | NVMe SSD，标称 1 TB |
| WebView2 运行时 | 156.0.4314.58 |

以上是本机事实，不代表其他 Windows 机器已经通过相同检查。

## 2. 工具链

### 2.1 版本与来源

| 工具 | 实际版本 | 本次安装方式或来源 |
|---|---|---|
| Git for Windows | 2.45.1.windows.1 | 既有安装；本次未安装，原安装方式未追溯 |
| Python 脚本解释器 | 3.11.9 | 既有 Python 与 `py` 启动器；`py -3` 实际选择此版本 |
| uv | 0.13.0 | 既有安装；本次未安装，原安装方式未追溯 |
| 项目 Python | 3.12.15 | `uv sync` 按项目要求创建 `core/.venv`；下载与缓存使用局部目录 |
| Node.js | 26.12.1 | [Node 官方 Windows x64 ZIP](https://nodejs.org/dist/v26.12.1/node-v26.12.1-win-x64.zip)，解压到 `tools/w00/node-v26.12.1-win-x64` |
| pnpm | 12.16.1 | 使用上述 Node 附带的 npm，从 [npm 官方 registry](https://registry.npmjs.org/pnpm) 安装到局部 prefix `tools/w00/pnpm` |
| rustup | 1.29.2 | [Rust 官方 MSVC 安装器](https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe)；工具目录均位于 `tools/w00` |
| rustc | 1.99.1 | rustup stable，目标 `x86_64-pc-windows-msvc` |
| cargo | 1.99.1 | 与上述 Rust 工具链一同安装 |
| rustfmt / clippy | 已安装，检查通过 | rustup 安装时显式添加这两个组件 |
| Visual Studio Build Tools | 2022，17.14.44 | [Microsoft 官方安装器](https://aka.ms/vs/17/release/vs_BuildTools.exe)，已核验微软数字签名 |
| MSVC | 14.44.35207 | Build Tools 的 C++ 工具链 |
| Windows SDK | 10.0.26100.0 | 与 C++ 工作负载安装 |
| Ninja | 1.13.0.git.kitware.jobserver-pipe-1 | 本次命令环境中可用，未单独安装 |
| CMake | 未在本次 PATH 中找到 | W-00 不使用；JEVDB 构建留待对应工作包验证 |

Node ZIP 的 SHA-256 已与同版本官方 `SHASUMS256.txt` 核对：

```text
b3efd5c70cba3308ed46e7e699a9b8aac075bbc6b027fcb39c84c31acc25e2b4
```

本次实际使用的安装命令如下，路径已用工作区占位符表示：

```powershell
# pnpm：使用 tools/w00 中 Node 附带的 npm.cmd
npm.cmd install --prefix "<工作区>/tools/w00/pnpm" --registry=https://registry.npmjs.org pnpm@12.16.1

# Rust：安装前已设置局部 CARGO_HOME 与 RUSTUP_HOME
rustup-init.exe -y --no-modify-path --profile minimal --default-host x86_64-pc-windows-msvc --default-toolchain stable --component rustfmt --component clippy

# Visual Studio Build Tools：官方安装器，安装 C++ 工作负载及推荐组件
vs_BuildTools.exe --quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --nocache
```

Node ZIP、Rust 安装器和 VS 安装器下载过程中曾出现未完成下载；补齐后检查文件长度，Node 另核对官方校验值，再继续安装。安装记录保存在本机 `tools/w00/bootstrap-log.jsonl`；该日志包含本地路径，不作为仓库公开附件。

### 2.2 局部环境

本次在命令进程内将下列目录加入 PATH，优先使用项目验证所需版本：

- `tools/w00/node-v26.12.1-win-x64`
- `tools/w00/pnpm/node_modules/.bin`
- `tools/w00/cargo/bin`

没有修改用户或系统 PATH。Rust 使用 `--no-modify-path`；`CARGO_HOME`、`RUSTUP_HOME`、uv Python 下载目录、uv/npm 缓存均指向 `tools/w00` 下的局部目录。环境初始化保存在本机 `tools/w00/session.ps1`，不属于产品脚本。

`doctor.py` 的实际结果为退出码 0，但 pnpm 版本显示“未知”。直接调用已解析的 `pnpm.CMD` 路径可以得到 `12.16.1`；裸命令的 Python 子进程复现见第 6 节。因此本次不以 doctor 的“OK”列单独判断工具是否可运行。

### 2.3 依赖实测

`py -3 scripts/setup.py` 退出码 0，完成 `uv sync`、`pnpm install --frozen-lockfile`、`cargo fetch`，总耗时 157.500 秒。

项目 Python 中实际安装并成功导入：

| 包 | 版本 | 最小验证 |
|---|---|---|
| DuckDB | 1.4.3 | 内存连接执行 `SELECT 1` 得到 `[(1,)]` |
| typesafe-sdk | 0.7.5 | 导入成功 |
| selectolax | 1.0.2 | Lexbor 解析 `<p>hello</p>`，正文为 `hello` |
| NumPy | 2.5.4 | 导入成功 |
| keyring | 25.7.0 | 包已安装；本轮未验证 Windows 凭据管理器读写 |

这证明当前锁定依赖可以在本机安装和完成上述最小检查。JEVDB 扩展构建与模型真实调用不在本轮实测范围内。

## 3. PowerShell 执行策略

`Get-ExecutionPolicy -List` 的实测结果：

| Scope | ExecutionPolicy |
|---|---|
| MachinePolicy | Undefined |
| UserPolicy | Undefined |
| Process | Undefined |
| CurrentUser | Undefined |
| LocalMachine | RemoteSigned |

本次通过 `powershell.exe -NoProfile -File scripts/doctor.ps1` 测试现有包装器，脚本被正常执行，没有遭执行策略拦截；退出码 1 来自脚本内的 W-01 占位错误。Windows PowerShell 输出中这段中文出现乱码，单独列入下游编码处理事项。

本轮没有更改执行策略，也没有使用策略绕过参数。其他来源下载的脚本是否带有阻止标记，需针对该文件另行验证，不能由本次结果推断。

## 4. 路径与编码

### 4.1 含空格和中文路径

所有工程命令均在 `<工作区>/JEV Stocks` 内执行；其父目录包含中文。依赖安装、Python 测试、前端 lint/typecheck/test/build、Rust 格式检查和 clippy 均在该路径完成。

首次桌面开发构建在同一路径完成，并运行了 `sentinel-desktop.exe`。本轮未发现可归因于空格或中文目录名的路径解析失败。

### 4.2 实际编码环境

- `chcp`：936。
- PowerShell 输出编码：UTF-8。
- 本次命令环境设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`。
- 日志采集按 UTF-8 保存；上述变量仅设置在命令环境中，没有修改系统区域设置。

Python 检查与 Node 原型回归在这个环境中通过。代码页 936 与 Python UTF-8 模式是不同设置，报告保留两者。现有 Windows PowerShell 包装器仍出现中文乱码，说明 Python 环境变量不能替代包装器自身的编码处理。

## 5. 杀软与性能

实测 Windows Defender 防病毒与实时保护均开启。本轮未关闭保护、未添加排除项。

| 操作 | 耗时或结果 |
|---|---|
| Visual Studio Build Tools 安装 | 313.319 秒，退出码 0 |
| Rust 安装 | 26.594 秒，退出码 0 |
| 局部 pnpm 安装 | 17.234 秒，退出码 0 |
| `scripts/setup.py` | 157.500 秒，退出码 0 |
| `uv run pytest -q` | 命令总耗时 4.078 秒；pytest 报告 0.27 秒 |
| 首次记录的 `cargo clippy --all-targets -- -D warnings` | 36.515 秒，退出码 0 |
| `scripts/check.py` | 15.516 秒；13 通过、1 失败、3 跳过 |
| 首次桌面开发构建 | Cargo 报告 45.15 秒后运行程序 |

以上包含当时缓存和网络状态的影响，未开展开关实时保护的对照实验，无法把耗时归因于 Defender。

桌面进程启动后，窗口清单中确认出现标题“投资逻辑哨兵”，确认时间不晚于本次开发进程被停止的 158.609 秒，满足五分钟内出现窗口的要求。本轮未完成窗口内容的视觉核验，也未采集内容截图。观察后主动停止了本次启动的开发进程树；采集器因此记录的结束码 1 不代表首次编译失败。

## 6. 已知坑与处理办法

### 6.1 平台占位尚未实现（A 类）

**现象**：Windows 平台名返回 `windows`；`default_data_dir`、`is_process_alive`、`file_lock`、`harden_permissions` 四个方法均抛 `NotImplementedError("W-01")`。

**原因**：WP-00 有意交付 Windows 占位实现。

**办法**：按 W-01 补齐，W-00 已记录调用结果。当前 pytest 为 `7 passed, 5 skipped`，五项跳过的是 macOS 测试，不能据此认定 Windows 平台功能已通过。

### 6.2 Windows mypy 检查 POSIX 分支失败（B 类）

**现象**：统一检查的 `py-types` 失败，`sentinel/platform/posix.py` 的 `fcntl.flock`、`LOCK_EX`、`LOCK_NB`、`LOCK_UN` 共报告五处 `attr-defined` 错误。其他统一检查为 13 项通过、3 项按条件跳过。

**原因**：Windows 类型检查仍检查 POSIX 专用模块，对该平台的 `fcntl` 属性定义不成立。运行时按平台选择实现与静态检查覆盖范围是两回事。

**办法**：交共享代码维护者处理，保留跨平台实现；本轮不修改代码或放宽检查。见 [CR：Windows mypy 平台问题](cr/CR-20261102-windows-mypy-platform.md)。

### 6.3 doctor 对 pnpm.CMD 的检测不完整（B 类）

**现象**：`shutil.which("pnpm")` 返回局部 `pnpm.CMD` 的完整路径；直接 `subprocess.run(["pnpm", "--version"])` 抛 `FileNotFoundError: [WinError 2]`，而使用已解析的完整路径调用正常。doctor 显示 pnpm“未知”，仍标记 OK 并返回 0。

**原因**：doctor 检测到文件后，启动时仍传裸命令，没有复用解析出的 `.CMD` 路径；检测结果也没有区分“找到文件”与“运行成功”。

**办法**：本轮实际命令使用已解析的完整路径，保证验证使用 pnpm 12.16.1；doctor 的修正交共享维护者，见 [CR：doctor 的 pnpm.CMD 检测](cr/CR-20261102-doctor-pnpm-cmd.md)。

### 6.4 开发监听器触及 Rust 编译产物时出现 EBUSY（B 类候选）

**现象**：`pnpm tauri dev` 编译期间，文件监听器对 `src-tauri/target/debug/build` 和 `src-tauri/target/debug/deps` 下部分 `.dll`、`.pdb`、`.exe` 输出 `EBUSY: resource busy or locked, watch`。随后 Cargo 正常完成编译并运行桌面程序。

**原因**：日志确认监听范围触及正在使用的 Rust 编译产物；具体需要调整的监听配置由共享维护者复核。

**办法**：记录为非致命开发警告，不将它写成启动失败。见 [CR：Vite 监听 target 产物](cr/CR-20261102-vite-target-watch.md)。

### 6.5 PowerShell 包装器的中文乱码（A 类占位交接）

**现象**：`doctor.ps1` 可以执行，预期退出码为 1，但“W-01 尚未实现”在 Windows PowerShell 输出中乱码。

**原因**：现有包装器为尚待 W-01 接手的占位文件；本轮确认其输出存在编码问题，未进一步更改文件编码或宿主设置。

**办法**：W-01 实现包装器时一并验证中文错误输出。当前环境使用 Python 入口完成工程检查。

### 6.6 初次下载不完整（C 类）

**现象**：官方大文件下载曾在未达到预期长度时结束。

**原因**：下载链路中断；不是工程路径或依赖接口错误。

**办法**：下载器记录失败并继续补齐，成功后核对长度；Node ZIP 与官方 SHA-256 匹配后解压。实测安装和后续检查均使用完整文件。

### 6.7 暂未覆盖的能力

当前记录没有验证 Windows 凭据管理器读写、完整子进程树退出、安装包、JEVDB 构建或真实模型调用。这些结果留给 W-01 及后续对应工作包填写；现有骨架检查不替代这些验收。


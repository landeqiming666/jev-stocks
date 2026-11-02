---
id: W-00
title: Windows 环境摸底与对等矩阵
phase: mvp0
platform: windows
lane: windows
deps: [WP-00]
size: S
status: doing
owns: [docs/wp/windows-matrix.md, docs/wp/windows-dev-notes.md]
---

# W-00 Windows 环境摸底与对等矩阵

## 0. 一眼看懂

- **目标**：在 Windows 机器上把 WP-00 的产物完整跑一遍，**如实记录每一个失败**，并建立“对等矩阵”。这个工作包**不修复任何东西**，它的产出是给 W-01 和协调者的事实清单。
- **完成后解锁**：W-01（Windows 平台层实现）。
- **预计规模**：两个文档文件加一份状态文件；没有代码。预计半天到一天，主要时间花在装工具链上。

## 1. 背景与边界

> 2026-11-02 已由 ADR-021 解禁。当前只做环境事实记录；`W-01`～`W-05` 仍未派发。

### 1.1 为什么需要它
WP-00 是在 macOS 上写的，Windows 一侧只有可编译的占位文件。没人知道 `uv sync` 能不能装上 `typesafe-sdk`、`selectolax`、`duckdb==1.4.3` 的 Windows 版本，也不知道 `pnpm tauri dev` 在 Windows 上缺什么。先摸清，再动手。

### 1.2 范围内
1. 在 Windows 11 x64 上安装开发工具链，把装法和版本记下来。
2. 用 **Python 脚本直接**运行 WP-00 的各项检查（因为 `.ps1` 此时还是占位）。
3. 把所有失败原样记录并分类。
4. 创建对等矩阵文件，登记 WP-00 一行。
5. 创建 Windows 开发笔记，记下坑。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 修复任何失败 | W-01（平台层）或变更申请（共享代码） |
| 写 `.ps1` 脚本 | W-01 |
| 构建 JEVDB | W-03 |
| 安装包 | v1 的 W-10 |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [decisions.md](../../decisions.md) | ADR-016、ADR-021 | 平台分工、W-00 解禁范围与后续闸门 |
| [10-协作与工作包规范.md](../../10-协作与工作包规范.md) | 9 Windows 车道协议 | 你的工作方式 |
| [02-技术架构.md](../../02-技术架构.md) | 2 开发环境、9 平台层 | 要装什么、平台层是什么 |
| [WP-00-skeleton.md](WP-00-skeleton.md) | 4 交付物、9.1 验收命令 | 你要验证的东西 |

## 3. 前置条件

- WP-00 已合并到 `main`（2026-11-02 起满足）。
- 一台 Windows 11 x64 机器，有管理员权限（安装 Visual Studio 生成工具需要）。**记录系统版本，不要假设**。
- 能访问 GitHub、PyPI、npm、crates.io。

## 4. 交付物清单

| 路径 | 动作 | 职责 |
|---|---|---|
| `docs/wp/windows-matrix.md` | 新建 | 对等矩阵，格式见 5.1 |
| `docs/wp/windows-dev-notes.md` | 新建 | Windows 开发笔记，格式见 5.2 |
| `docs/wp/status/W-00.md` | 新建 | 完成报告，另含第 5.3 节的失败分类表 |

## 5. 接口规格

### 5.1 `docs/wp/windows-matrix.md`

```markdown
# Windows 对等矩阵

> 维护人：Windows 车道。每次 Mac 一侧合并 `platform: shared` 的工作包后，在一个工作日内更新。
> 结果取值：通过 / 失败 / 未验证。失败必须写原因，并链接到变更申请或修复分支。

| 工作包 | main 上的提交 | 验证日期 | Windows 结果 | 说明与链接 |
|---|---|---|---|---|
| WP-00 | `<7 位哈希>` | 2026-MM-DD | 失败 | 见 status/W-00.md 第 N 项 |
```

### 5.2 `docs/wp/windows-dev-notes.md` 必含的小节

| 小节 | 内容 |
|---|---|
| 机器信息 | Windows 版本和 build 号、CPU 架构、内存、磁盘类型 |
| 工具链 | 每个工具的名称、版本、**实际使用的安装命令或安装包来源**（见 6.2 的参考，须核实） |
| PowerShell 执行策略 | `Get-ExecutionPolicy -List` 的输出；脚本被拦截时的处理办法（见 6.3） |
| 路径与编码 | 仓库路径含空格是否有问题；控制台编码（`chcp` 输出）；`PYTHONUTF8` 是否生效 |
| 杀软与性能 | Windows Defender 是否明显拖慢 `uv sync`、`pnpm install`、`cargo build`，记下耗时 |
| 已知坑 | 逐条记录，每条格式“现象 → 原因 → 办法” |

### 5.3 状态文件里的失败分类表

对每个失败项一行：

| # | 命令 | 现象（原文输出的关键 5 行以内） | 类别 | 谁处理 |
|---|---|---|---|---|
| 1 | `py -3 scripts\check.py` | … | A | W-01 |

类别：

| 类 | 含义 | 处理 |
|---|---|---|
| A | 平台层缺失（占位文件未实现） | W-01 |
| B | 共享代码在 Windows 上有问题（路径、编码、行尾、依赖缺轮子等） | 提变更申请（类型“平台问题”），见 [10](../../10-协作与工作包规范.md) 第 9 节 |
| C | 环境与工具（缺工具、版本、权限、杀软） | 记入开发笔记，不需要改代码 |

## 6. 实现步骤

### 6.1 准备
1. 记录 `winver`、`systeminfo | findstr /B /C:"OS" /C:"System Type" /C:"Total Physical Memory"` 的输出。
2. 克隆仓库到**含空格的路径**（例如 `C:\work\JEV Stocks`），这是故意的：真实用户和这个仓库的路径都含空格。

### 6.2 安装工具链
参考命令如下。`TODO-VERIFY(W-00)`：这些包标识符和命令是参考写法，**以各工具的官方文档为准**，实际用了什么就记什么。

| 工具 | 要求 | 参考 |
|---|---|---|
| Git for Windows | 任意较新版本 | `winget install --id Git.Git -e` |
| Python | 3.9 以上，且有 `py` 启动器；**只用来运行 `scripts\*.py`** | python.org 安装包，勾选 “py launcher” |
| uv | 能安装并管理 CPython 3.12 | `winget install --id astral-sh.uv -e` |
| Node.js | 主版本与仓库 `.node-version` 一致 | `winget install OpenJS.NodeJS.LTS`，或按需选版本 |
| pnpm | 与 `package.json` 的 `packageManager` 一致 | `npm install -g pnpm` |
| Rust | 目标 `x86_64-pc-windows-msvc` | rustup 官方安装器；工具链选 MSVC，不要选 GNU |
| C++ 生成工具 | Visual Studio 生成工具（含“使用 C++ 的桌面开发”工作负载） | 官方安装器 |
| WebView2 运行时 | Windows 11 自带；记录版本 | 注册表或 Edge 版本页 |

### 6.3 逐条运行并记录
**每条命令都要记录退出码和关键输出**，失败不要跳过：

```powershell
py -3 scripts\doctor.py
py -3 scripts\setup.py
py -3 scripts\check.py
cd core
uv run pytest -q
cd ..\apps\desktop
pnpm lint
pnpm typecheck
pnpm test
pnpm build
cd src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cd ..
pnpm tauri dev    # 观察 5 分钟内能否弹出窗口；记录首次编译耗时
```

预期会失败的项（W-01 修）：`test_platform_*` 里调用 `windows.py` 的用例、`windows.rs` 里的占位逻辑、`.ps1` 占位脚本。**这些归 A 类，不要“顺手修掉”。**

### 6.4 PowerShell 执行策略
运行 `Get-ExecutionPolicy -List`，把输出贴进笔记。然后尝试直接运行 `.\scripts\doctor.ps1`（占位脚本，会输出 “W-01 尚未实现” 并非 0 退出）：

- 若被执行策略拦截，记录原文报错，并记录你用来绕过的办法（例如 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\doctor.ps1`，或为当前用户设置 `RemoteSigned`）。`TODO-VERIFY(W-00)`：在你的机器上实测哪种办法有效。
- 这条结论会被 W-01 写进 `.ps1` 脚本的用法说明里。

### 6.5 对等矩阵与状态文件
1. 创建 `windows-matrix.md`，登记 WP-00 一行（结果“失败”，除非 A/B 类失败为零，这几乎不可能）。
2. 填写状态文件，包含完整失败分类表。
3. 把 B 类每一项各写一个变更申请草稿到 `docs/wp/cr/`（类型“平台问题”，现象与命令输出齐全，**方案一栏可留空**）。

## 7. 错误与边界情况

| 情形 | 行为 |
|---|---|
| 某个工具装不上 | 如实记录现象和尝试过的办法，类别 C；不要换成别的工具 |
| `uv sync` 因为缺 Windows 轮子失败 | 类别 B，记下包名与版本；这是重要信息，会影响 JEVDB 之外的所有依赖决策 |
| 仓库路径含空格导致脚本失败 | 类别 B；这是缺陷而不是“请换个路径” |
| 命令输出乱码 | 记录 `chcp`、`$OutputEncoding`、`[Console]::OutputEncoding`；类别 B 或 C |
| 失败太多记不过来 | 先全部跑完，再统一整理；每条保留命令和退出码 |

## 8. 测试（先写）

本工作包没有自动化测试，验收是“证据完整”。先写的是**检查清单**：开始前在状态文件顶部把第 9.2 节的清单复制进去，做完一项勾一项。

## 9. 验收

### 9.1 命令
```powershell
py -3 scripts\check_docs.py
# 期望：错误 0（对等矩阵和笔记里的链接、文档名都有效）
```

### 9.2 完成清单
- [ ] `docs/wp/windows-matrix.md` 已创建，WP-00 一行齐全
- [ ] `docs/wp/windows-dev-notes.md` 含 5.2 的六个小节，每个工具都有版本和实际安装方式
- [ ] 状态文件里 6.3 的每条命令都有退出码和关键输出
- [ ] 每个失败项都有类别（A / B / C）
- [ ] 每个 B 类项都有一份变更申请草稿
- [ ] PowerShell 执行策略的实测结论已写入笔记
- [ ] 没有修改任何 `owns` 之外的文件，也没有修复任何失败

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| W-01 | 状态文件里的 A 类清单、笔记里的执行策略结论和工具版本 | W-01 的目标就是让 A 类清零 |
| 协调者 | B 类变更申请 | 决定谁修、怎么修 |
| W-02 及以后 | 对等矩阵文件 | 持续维护 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| Windows 上 `duckdb==1.4.3` 没有对应的轮子 | `uv sync` 报找不到可用版本 | 这会影响整个 Windows 车道，立即通知协调者；JEVDB 与 DuckDB 版本是绑定的，不得擅自换版本 |
| 公司或学校的电脑限制安装 | 无管理员权限 | 记录限制，改用个人电脑；开发笔记里写明 |

---
id: WP-00
title: 仓库骨架与工具链
phase: mvp0
platform: shared
lane: core
deps: []
size: M
status: done
owns: [.gitignore, .editorconfig, .node-version, THIRD_PARTY.md, core/pyproject.toml, core/uv.lock, core/.python-version, core/sentinel/__init__.py, core/sentinel/platform/__init__.py, core/sentinel/platform/posix.py, core/tests/conftest.py, core/tests/unit/test_smoke.py, core/tests/unit/test_layering.py, apps/desktop/package.json, apps/desktop/pnpm-lock.yaml, apps/desktop/tsconfig.json, apps/desktop/vite.config.ts, apps/desktop/vitest.config.ts, apps/desktop/eslint.config.js, apps/desktop/index.html, apps/desktop/src/styles/platform-macos.css, apps/desktop/src-tauri/Cargo.toml, apps/desktop/src-tauri/Cargo.lock, apps/desktop/src-tauri/build.rs, apps/desktop/src-tauri/tauri.conf.json, apps/desktop/src-tauri/tauri.macos.conf.json, apps/desktop/src-tauri/capabilities/default.json, apps/desktop/src-tauri/icons/, apps/desktop/src-tauri/src/main.rs, apps/desktop/src-tauri/src/platform/mod.rs, apps/desktop/src-tauri/src/platform/macos.rs, scripts/check.py, scripts/setup.py, scripts/dev.py, scripts/doctor.py, scripts/make_placeholder_icon.py, scripts/check.sh, scripts/setup.sh, scripts/dev.sh, scripts/doctor.sh, scripts/check_platform_isolation.py, scripts/tests/test_check_platform_isolation.py, scripts/tests/test_check_runner.py, scripts/tests/test_doctor.py]
appends: []
stubs: [core/sentinel/platform/windows.py, apps/desktop/src-tauri/src/platform/windows.rs, apps/desktop/src-tauri/tauri.windows.conf.json, apps/desktop/src/styles/platform-windows.css, apps/desktop/src/main.tsx, apps/desktop/src/Hello.tsx, apps/desktop/src/Hello.test.tsx, apps/desktop/src-tauri/src/lib.rs, scripts/check.ps1, scripts/setup.ps1, scripts/dev.ps1, scripts/doctor.ps1]
---

# WP-00 仓库骨架与工具链

## 0. 一眼看懂

- **目标**：做出能被其他所有工作包依赖的工程底座：三套技术栈（Python、前端、Rust/Tauri）各有一个能编译、能测试的最小入口；全部白名单依赖一次装齐并锁定版本；`scripts/check.*` 一条命令跑全部检查；平台层的接口和 macOS 实现就位，Windows 一侧留下可编译的占位文件。
- **完成后解锁**：几乎所有工作包（C-00、G0-JEV、G0-JEVDB、G1-US、D-01、U-00、W-00 等）。
- **预计规模**：新增约 45 个文件，手写代码加测试约 900 行（不含锁文件和图标）。这是 MVP-0 里最大的一个工作包，因为所有人都等它。**宁可多花半天，把它做对**。
- **这是唯一允许修改依赖清单的工作包**（[02](../../02-技术架构.md) 第 4 节）。

## 1. 背景与边界

### 1.1 为什么需要它
十几个工作包会并行开发。如果没有统一的目录、统一的依赖、统一的检查命令，每个人都会各自发明一套，合并时必然冲突。WP-00 把这些先定死。

### 1.2 范围内
1. 仓库根文件：忽略规则、编辑器配置、Node 版本、第三方许可证清单。根 `README.md` 是产品介绍，**不得覆盖**。
2. Python 工程 `core/`：`pyproject.toml`（依赖、ruff、mypy、pytest 配置）、锁文件、`sentinel` 包的最小入口、平台层（接口 + macOS 实现 + Windows 占位）、冒烟测试、分层规则测试。
3. 前端工程 `apps/desktop/`：`package.json`（依赖和脚本）、锁文件、TypeScript / Vite / Vitest / ESLint 配置、一个能渲染的 `Hello` 组件及其测试。
4. Tauri 工程 `apps/desktop/src-tauri/`：`Cargo.toml`、锁文件、`tauri.conf.json`、能打开一个空窗口的 `lib.rs`、平台层（trait + macOS 实现 + Windows 占位）、占位图标。
5. 脚本：`scripts/check.py`、`setup.py`、`dev.py`、`doctor.py`、`make_placeholder_icon.py`、`check_platform_isolation.py`，以及 `.sh` 包装；它们的单元测试。
6. Windows 一侧的 8 个占位文件（头部 `stubs`），保证 Windows 车道一开工就能编译。

### 1.3 明确不做
| 不做 | 由谁做 |
|---|---|
| 任何业务代码（`ids.py`、`clock.py`、`errors.py`、日志、RPC） | C-00、C-01 |
| 核心进程的启动、桥接、CSP 最终值、`rpc_send` 命令 | C-02 |
| 应用外壳、路由、设计令牌、RpcClient | U-00 |
| Windows 的真实实现、`.ps1` 的真实内容 | W-01 |
| CI 工作流文件（团队暂无远端仓库） | 以后按需 |
| `scripts/gen_ts_types.py`（契约 → TypeScript 类型） | C-05 |
| `contracts/` 全部 JSON、`scripts/gen_proto_mock.py`、`scripts/check_contracts.py` | C-06 |
| `scripts/check_contrast.py`、`scripts/check_proto.py`、`scripts/proto_render.js`、`design/prototype/` | **已由文档作者交付，WP-00 不得修改**；`check.py` 的步骤表已引用它们 |
| `scripts/check_docs.py` 及其测试 | 已存在，**不得修改** |

## 2. 必读

| 文档 | 小节 | 为什么要读 |
|---|---|---|
| [00-术语与约定.md](../../00-术语与约定.md) | 3.2 代码命名、3.4 工作包 ID、5 环境变量 | 命名与环境变量 |
| [02-技术架构.md](../../02-技术架构.md) | 2 开发环境、3 技术选型、4 依赖白名单、9 平台层、16 仓库结构与分层规则 | 本工作包要落地的内容 |
| [decisions.md](../../decisions.md) | ADR-010、ADR-016 | 全局 CSS、平台隔离 |

## 3. 前置条件

- macOS，已安装 `uv`、`node`、`npm`、`rustc`、`cargo`、`git`（本机已验证，见 [02](../../02-技术架构.md) 2.1）。**`pnpm` 未安装**：第 6 节第 1 步安装。
- 能访问 PyPI、npm、crates.io。
- 当前仓库还没有任何提交。**协调者应先做一次初始提交**（见 [10](../../10-协作与工作包规范.md) 第 3 节），WP-00 在 worktree 里开发。
- 仓库路径含空格（`JEV Stocks`）。**所有脚本和测试必须能处理含空格的路径**。

## 4. 交付物清单

### 4.1 仓库根

| 路径 | 动作 | 职责 |
|---|---|---|
| `.gitignore` | 新建 | 见 5.3 |
| `.editorconfig` | 新建 | `root = true`；`utf-8`；`end_of_line = lf`；`insert_final_newline = true`；`indent_style = space`；Python / Rust 4 空格，TS / JSON / CSS / MD 2 空格；`*.ps1` 与 `*.bat` 用 `crlf`，因为 PowerShell 5 对 LF 脚本的行为不稳定 |
| `.node-version` | 新建 | 写本机已验证可用的 Node **主版本号**，一行，如 `26`。若 `pnpm install` 或 `vite build` 在该版本下报错，改用 Node 22 LTS（`brew install node@22`）并在状态文件记录 |
| `README.md` | 不改 | 已存在，是产品介绍；开发快速开始后续由协调者追加，不属于本包 |
| `THIRD_PARTY.md` | 新建 | 白名单每个包一行：名称、版本、许可证。许可证从包元数据读取（`uv pip show`、`pnpm licenses list`、`cargo metadata`），**不凭记忆填写**。无法确定的写 `UNKNOWN` 并在状态文件列出。同时解决 [02](../../02-技术架构.md) 里的 `TODO-VERIFY(WP-00)` |

### 4.2 Python（`core/`）

| 路径 | 动作 | 职责 |
|---|---|---|
| `core/pyproject.toml` | 新建 | 见 5.1 |
| `core/uv.lock` | 生成 | `uv lock` 的结果，提交 |
| `core/.python-version` | 新建 | 内容 `3.12` |
| `core/sentinel/__init__.py` | 新建 | 只含 `__version__ = "0.1.0"` |
| `core/sentinel/platform/__init__.py` | 新建 | 平台层接口与选择逻辑，见 5.2 |
| `core/sentinel/platform/posix.py` | 新建 | macOS 实现（本机用） |
| `core/sentinel/platform/windows.py` | 新建（占位） | 见 5.2，头部 `stubs` 由 W-01 接手 |
| `core/tests/conftest.py` | 新建 | 平台标记自动跳过，见 8.1 |
| `core/tests/unit/test_smoke.py` | 新建 | 冒烟测试 |
| `core/tests/unit/test_layering.py` | 新建 | 分层规则测试，见 5.4 |

不需要创建 `core/sentinel/__main__.py`：C-07 创建。

### 4.3 前端（`apps/desktop/`）

| 路径 | 动作 | 职责 |
|---|---|---|
| `package.json` | 新建 | 见 5.5 |
| `pnpm-lock.yaml` | 生成 | 提交 |
| `tsconfig.json` | 新建 | `strict: true`、`noUncheckedIndexedAccess: true`、`jsx: "react-jsx"`、`target: "ES2022"`、`moduleResolution: "bundler"`、`noEmit: true`、`include: ["src", "e2e", "vite.config.ts", "vitest.config.ts"]`、路径别名 `@/*` → `src/*` |
| `vite.config.ts` | 新建 | React 插件；`server: { port: 1420, strictPort: true }`；`clearScreen: false`；`resolve.alias` 与 tsconfig 的 `@` 一致；`build.target: "safari15"`（WKWebView 与 WebView2 都能跑；Windows 车道若发现 WebView2 要调整，走变更申请） |
| `vitest.config.ts` | 新建 | `environment: "jsdom"`；`include: ["src/**/*.test.{ts,tsx}"]`；与 vite 同样的别名 |
| `eslint.config.js` | 新建 | 扁平配置：`@eslint/js` recommended + `typescript-eslint` recommended + `react-hooks`（`rules-of-hooks: error`、`exhaustive-deps: error`）；额外规则 `no-restricted-syntax` 禁止字符串字面量匹配 `^#[0-9a-fA-F]{3,8}$` 的内联颜色（ADR-010） |
| `index.html` | 新建 | `<html lang="zh-CN">`；`<div id="root">`；`<script type="module" src="/src/main.tsx">` |
| `src/main.tsx` | 新建 | 渲染 `<Hello />` 到 `#root` |
| `src/Hello.tsx` | 新建 | 导出 `Hello`：渲染 `<h1>投资逻辑哨兵</h1>`（U-00 会删除它） |
| `src/Hello.test.tsx` | 新建 | 见 8.1 |
| `src/styles/platform-macos.css` | 新建 | 只含一个规则块：`[data-platform="macos"] { --titlebar-inset-left: 72px; --font-cjk: "PingFang SC"; --kbd-mod: "⌘"; }` 加一行注释 |
| `src/styles/platform-windows.css` | 新建（占位） | 同样三个变量：`--titlebar-inset-left: 0px; --font-cjk: "Microsoft YaHei UI"; --kbd-mod: "Ctrl";`，由 W-01 接手 |

### 4.4 Tauri（`apps/desktop/src-tauri/`）

| 路径 | 动作 | 职责 |
|---|---|---|
| `Cargo.toml` | 新建 | 见 5.6 |
| `Cargo.lock` | 生成 | 提交 |
| `build.rs` | 新建 | 标准的 `tauri_build::build()` |
| `tauri.conf.json` | 新建 | 见 5.7 |
| `tauri.macos.conf.json` | 新建 | `{ "bundle": { "targets": ["app", "dmg"], "macOS": { "minimumSystemVersion": "13.0" } } }` |
| `tauri.windows.conf.json` | 新建（占位） | `{ "bundle": { "targets": ["nsis"] } }`，由 W-01 接手 |
| `capabilities/default.json` | 新建 | 只含 `core:default`，窗口 `main`。**不得添加其他权限**（[02](../../02-技术架构.md) 第 13 节） |
| `icons/` | 生成 | 由 `scripts/make_placeholder_icon.py` 生成 1024×1024 纯色 PNG，再运行 `pnpm tauri icon <png>` 生成全套 |
| `src/main.rs` | 新建 | 标准头部 `#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]`，`fn main() { sentinel_lib::run() }` |
| `src/lib.rs` | 新建 | 见 5.8 |
| `src/platform/mod.rs` | 新建 | trait 与 `current()`，见 5.9 |
| `src/platform/macos.rs` | 新建 | macOS 实现 |
| `src/platform/windows.rs` | 新建（占位） | 可编译的最小实现，W-01 接手 |

### 4.5 脚本（`scripts/`）

| 路径 | 动作 | 职责 |
|---|---|---|
| `check.py` | 新建 | 一键检查，见 5.10 |
| `setup.py` | 新建 | 安装依赖，见 5.11 |
| `dev.py` | 新建 | 启动开发模式，见 5.12 |
| `doctor.py` | 新建 | 打印工具链版本，见 5.13 |
| `make_placeholder_icon.py` | 新建 | 用标准库（`zlib`、`struct`）写一个 1024×1024 纯色（`#1A1C20`）RGBA PNG，参数 `--out PATH` |
| `check_platform_isolation.py` | 新建 | 平台隔离检查，见 5.14 |
| `check.sh` `setup.sh` `dev.sh` `doctor.sh` | 新建 | 每个 ≤ 5 行，见 5.15；可执行位 `chmod +x` |
| `check.ps1` `setup.ps1` `dev.ps1` `doctor.ps1` | 新建（占位） | 每个只含一行 `Write-Error "W-01 尚未实现"; exit 1`，W-01 接手 |
| `tests/test_check_runner.py` | 新建 | `check.py` 的测试 |
| `tests/test_check_platform_isolation.py` | 新建 | 隔离检查的测试 |
| `tests/test_doctor.py` | 新建 | `doctor.py` 的测试 |

## 5. 接口规格

### 5.1 `core/pyproject.toml`

```toml
[project]
name = "sentinel"
version = "0.1.0"
description = "Thesis Sentinel core process"
requires-python = ">=3.12,<3.13"
dependencies = [
  "duckdb==1.4.3",
  "typesafe-sdk",
  "httpx",
  "selectolax",
  "numpy",
  "keyring",
  "pydantic>=2",
  "tzdata",
]

[dependency-groups]
dev = ["pytest", "pytest-timeout", "jsonschema", "ruff", "mypy"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["sentinel"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["typesafe_sdk.*", "keyring.*", "selectolax.*", "duckdb.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
timeout = 30
addopts = "-ra"
markers = [
  "macos: 只在 macOS 上运行",
  "windows: 只在 Windows 上运行",
  "integration: 需要网络或真实密钥，默认不运行",
]
```

只写白名单里的包，**不加版本上界**（锁文件负责固定版本），唯一例外是 `duckdb==1.4.3`。装好后 `uv.lock` 里 `duckdb` 必须是 1.4.3。

### 5.2 平台层 Python 接口

`core/sentinel/platform/__init__.py` 导出（签名固定，W-01 与 C-01 依赖它）：

```python
from pathlib import Path
from typing import ContextManager, Literal

class AlreadyRunning(Exception):
    """文件锁已被另一个核心进程持有。"""

def name() -> Literal["macos", "windows"]: ...
def default_data_dir() -> Path: ...
def is_process_alive(pid: int) -> bool: ...
def file_lock(path: Path) -> ContextManager[None]: ...
def harden_permissions(path: Path) -> None: ...
```

选择逻辑：模块加载时用 `sys.platform` 判断（**这是整个核心代码里唯一允许出现 `sys.platform` 的地方之一**）：`"darwin"` → 导入 `.posix` 并把上面五个名字绑定到它的同名函数；`"win32"` → 导入 `.windows`；其他 → 抛 `RuntimeError("不支持的平台: <sys.platform>")`。

`posix.py`（macOS 实现，每个函数的行为）：

| 函数 | 行为 |
|---|---|
| `name()` | 返回 `"macos"` |
| `default_data_dir()` | `Path.home() / "Library" / "Application Support" / "Sentinel"`，不创建目录 |
| `is_process_alive(pid)` | `pid <= 0` 返回 `False`；`os.kill(pid, 0)` 成功返回 `True`；抛 `ProcessLookupError` 返回 `False`；抛 `PermissionError` 返回 `True`（进程存在但属于别的用户） |
| `file_lock(path)` | 上下文管理器：以 `"a+"` 打开 `path`（父目录不存在则创建），`fcntl.flock(fd, LOCK_EX \| LOCK_NB)`；`BlockingIOError` 转成 `AlreadyRunning`；退出时释放并关闭。**不删除锁文件** |
| `harden_permissions(path)` | 目录设 `0o700`，文件设 `0o600`；路径不存在则抛 `FileNotFoundError` |

`windows.py`（占位，W-01 重写）：每个函数 `raise NotImplementedError("W-01")`，**但 `name()` 返回 `"windows"`**，保证模块可导入。

### 5.3 `.gitignore` 必含的行

```text
.DS_Store
.kiro/backup/
.dev-data/
node_modules/
dist/
target/
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.duckdb
*.duckdb.wal
eval/reports/
playwright-report/
test-results/
.env
.env.*
```

**不得**忽略 `uv.lock`、`pnpm-lock.yaml`、`Cargo.lock`、`.kiro/notes/`。

### 5.4 分层规则测试（`core/tests/unit/test_layering.py`）

把 [02](../../02-技术架构.md) 第 16 节的规则编码为：

```python
ALWAYS_ALLOWED = {"ids", "clock", "errors", "messages", "logging_setup"}
LAYER_RULES: dict[str, set[str]] = {
    "domain": set(),
    "storage": {"domain"},
    "http": {"domain"},
    "security": {"domain"},
    "platform": {"domain"},
    "markets": {"domain", "storage", "http"},
    "semantic": {"domain", "storage", "http"},
    "quant": {"domain", "storage", "markets", "rpc"},
    "trading": {"domain", "storage", "markets", "rpc"},
    "portfolio": {"domain", "storage", "markets", "rpc"},
    "rpc": {"domain"},
    "settings": {"domain", "storage", "security", "secrets"},
    "secrets": {"domain", "security", "platform"},
    "scan": {"domain", "storage", "markets", "semantic", "rpc"},
    "app": {"*"},
    "evaluation": {"*"},
    "demo": {"*"},
}

def imported_layers(source: str, module_path: str) -> set[str]: ...
```

`imported_layers(source, module_path)`：用 `ast` 解析 `source`，返回它依赖的 `sentinel` 顶层子包名集合。`module_path` 是点分模块路径（如 `sentinel.storage.db`），用来解析相对导入（`from ..domain import x` 在 `sentinel.storage.db` 里指向 `sentinel.domain`）。规则：

1. `import sentinel.X.Y` → `X`；`from sentinel.X import Y` → `X`；`from sentinel import X` → `X`（`X` 是名字且是已知层或 ALWAYS_ALLOWED 才计入）。
2. 相对导入按 `level` 向上回溯后同样处理。
3. 非 `sentinel` 的导入忽略。
4. 导入的名字不在 `LAYER_RULES` 的键也不在 `ALWAYS_ALLOWED` 里（例如顶层的 `__main__`）则忽略。

### 5.5 `apps/desktop/package.json`

- `name`: `"sentinel-desktop"`，`private: true`，`type: "module"`，`packageManager: "pnpm@<安装后的版本>"`，`engines.node` 与 `.node-version` 的主版本一致。
- `scripts`（名字固定，`check.py` 依赖它们）：

| 脚本 | 命令 |
|---|---|
| `dev` | `vite` |
| `build` | `tsc --noEmit && vite build` |
| `lint` | `eslint .` |
| `typecheck` | `tsc --noEmit` |
| `test` | `vitest run` |
| `e2e` | `playwright test` |
| `tauri` | `tauri` |

- `dependencies` 与 `devDependencies` **完全按** [02](../../02-技术架构.md) 4.2 的表，不含 `lightweight-charts`（v1 才加）。

### 5.6 `Cargo.toml`

- `[package]`：`name = "sentinel-desktop"`，`version = "0.1.0"`，`edition = "2021"`。
- `[lib]`：`name = "sentinel_lib"`，`crate-type = ["staticlib", "cdylib", "rlib"]`。
- `[build-dependencies]`：`tauri-build`。
- `[dependencies]`：只有 [02](../../02-技术架构.md) 4.3 表里的 crate；**v1 才用的**（`tauri-plugin-dialog`、`tauri-plugin-autostart`、`tauri-plugin-opener`）**现在不加**。

### 5.7 `tauri.conf.json`

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "Sentinel",
  "version": "0.1.0",
  "identifier": "org.thesissentinel.desktop",
  "build": {
    "beforeDevCommand": "pnpm dev",
    "devUrl": "http://localhost:1420",
    "beforeBuildCommand": "pnpm build",
    "frontendDist": "../dist"
  },
  "app": { "windows": [], "security": { "csp": null } },
  "bundle": {
    "active": true,
    "icon": ["icons/32x32.png", "icons/128x128.png", "icons/128x128@2x.png", "icons/icon.icns", "icons/icon.ico"]
  }
}
```

- `windows` 为空数组：窗口在 `lib.rs` 里由平台层创建（这样 `tauri.<平台>.conf.json` 不需要重复整个窗口数组，因为 JSON Merge Patch 会整体替换数组）。
- `csp` 先留 `null`，**C-02 负责设置最终值**；本工作包不得声称 CSP 已完成。

### 5.8 `src/lib.rs`（参考实现，编译细节可调整，但 `platform::Platform` 的接口不得改变）

```rust
mod platform;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_focus();
            }
        }))
        .setup(|app| {
            let p = platform::current();
            let builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("投资逻辑哨兵")
                .inner_size(1280.0, 820.0)
                .min_inner_size(1024.0, 700.0)
                .initialization_script(&p.init_script());
            p.configure_window(builder).build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### 5.9 `src/platform/mod.rs`

```rust
use tauri::{Manager, Runtime, WebviewWindowBuilder};

pub trait Platform: Sync {
    fn name(&self) -> &'static str;
    fn init_script(&self) -> String;
    fn configure_window<'a, R: Runtime, M: Manager<R>>(
        &self,
        builder: WebviewWindowBuilder<'a, R, M>,
    ) -> WebviewWindowBuilder<'a, R, M>;
    fn prepare_core_command(&self, cmd: &mut std::process::Command);
    fn kill_process_tree(&self, child: &mut std::process::Child);
}

#[cfg(target_os = "macos")]
mod macos;
#[cfg(windows)]
mod windows;

#[cfg(target_os = "macos")]
pub fn current() -> &'static dyn Platform { &macos::MacOs }
#[cfg(windows)]
pub fn current() -> &'static dyn Platform { &windows::Windows }
#[cfg(not(any(target_os = "macos", windows)))]
compile_error!("不支持的平台：只支持 macOS 与 Windows");
```

**注意**：带泛型方法的 trait 不是对象安全的，`&dyn Platform` 会编译失败。遇到这个问题，把 `configure_window` 改成接收并返回一个具体类型（`WebviewWindowBuilder<'a, tauri::Wry, tauri::AppHandle>` 或让 `current()` 返回 `impl Platform`），**保持方法名与语义不变**，并把最终签名写进状态文件的“与文档不一致”一栏，由协调者同步 [02](../../02-技术架构.md) 第 9 节。

`macos.rs` 的行为：

| 方法 | 行为 |
|---|---|
| `name` | `"macos"` |
| `init_script` | 返回 `document.documentElement.dataset.platform = "macos";`（脚本在首次绘制前执行；若此时 `documentElement` 尚不可用，用 `document.addEventListener("DOMContentLoaded", …)` 兜底并也立即尝试一次） |
| `configure_window` | `.title_bar_style(TitleBarStyle::Overlay).hidden_title(true)` |
| `prepare_core_command` | 不做事 |
| `kill_process_tree` | 先 `child.kill()`，再忽略 `ESRCH`；macOS 上核心进程没有子进程，直接结束即可 |

### 5.10 `scripts/check.py`

```python
@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]              # argv；"{python}" 会被替换为 sys.executable
    cwd: str                        # 相对仓库根
    requires: list[str]             # 相对仓库根的路径，任何一个不存在则 SKIP
    needs_flag: str | None = None   # 如 "e2e"：只有传了 --e2e 才运行

STEPS: list[Step] = [...]           # 顺序见下表

def run_steps(
    steps: list[Step], root: Path, only: list[str] | None = None,
    flags: set[str] | None = None, runner=subprocess.run,
    which=shutil.which, out=print,
) -> int: ...                       # 0：全部 PASS 或 SKIP；1：有 FAIL

def main(argv: list[str] | None = None) -> int: ...
```

`STEPS`（顺序固定）：

| name | command | cwd | requires |
|---|---|---|---|
| `docs` | `{python} scripts/check_docs.py` | `.` | `docs` |
| `isolation` | `{python} scripts/check_platform_isolation.py` | `.` | `scripts/check_platform_isolation.py` |
| `scripts-test` | `{python} -m unittest discover -s scripts/tests` | `.` | `scripts/tests` |
| `contrast` | `{python} scripts/check_contrast.py` | `.` | `scripts/check_contrast.py` |
| `proto` | `{python} scripts/check_proto.py` | `.` | `scripts/check_proto.py` |
| `generated-ts` | `{python} scripts/gen_ts_types.py --check` | `.` | `scripts/gen_ts_types.py` |
| `generated-proto` | `{python} scripts/gen_proto_mock.py --check` | `.` | `scripts/gen_proto_mock.py` |
| `py-lint` | `uv run ruff check .` | `core` | `core/pyproject.toml` |
| `py-format` | `uv run ruff format --check .` | `core` | `core/pyproject.toml` |
| `py-types` | `uv run mypy sentinel` | `core` | `core/pyproject.toml` |
| `py-test` | `uv run pytest -q` | `core` | `core/pyproject.toml` |
| `web-lint` | `pnpm lint` | `apps/desktop` | `apps/desktop/package.json` |
| `web-types` | `pnpm typecheck` | `apps/desktop` | `apps/desktop/package.json` |
| `web-test` | `pnpm test` | `apps/desktop` | `apps/desktop/package.json` |
| `rust-fmt` | `cargo fmt --check` | `apps/desktop/src-tauri` | `apps/desktop/src-tauri/Cargo.toml` |
| `rust-clippy` | `cargo clippy --all-targets -- -D warnings` | `apps/desktop/src-tauri` | `apps/desktop/src-tauri/Cargo.toml` |
| `e2e`（`needs_flag="e2e"`） | `pnpm e2e` | `apps/desktop` | `apps/desktop/playwright.config.ts` |

`run_steps` 的行为：

1. 对每个步骤按顺序处理，输出一行状态：`PASS <name>`、`FAIL <name> (<原因>)`、`SKIP <name> (<原因>)`。
2. 被 `only` 排除 → `SKIP … (未选中)`；`needs_flag` 没给 → `SKIP … (需要 --<flag>)`；`requires` 缺任何一个 → `SKIP … (缺少 <路径>)`。
3. `command[0]` 用 `which` 解析（Windows 上 `pnpm` 是 `pnpm.cmd`，所以**不要**自己拼后缀）。找不到 → `FAIL … (找不到命令 <名>，运行 scripts/doctor.py 查看缺什么)`，**不抛异常**。
4. 用列表形式调用 `runner(argv, cwd=…)`，**不使用 shell**，所以含空格的路径无需引号。退出码非 0 → `FAIL … (退出码 N)`。
5. 一个步骤失败后**继续**运行后面的步骤；全部结束后输出汇总一行 `通过 X · 失败 Y · 跳过 Z`；有失败返回 1。
6. 命令行：`--only NAME`（可重复）、`--e2e`、`--list`（只打印步骤名和 requires 的存在情况）。

### 5.11 `scripts/setup.py`

依次运行（目录或文件不存在则 `SKIP`，同样用 `which` 解析，不使用 shell）：

1. `uv sync`（cwd `core`）
2. `pnpm install --frozen-lockfile`（cwd `apps/desktop`）
3. `cargo fetch`（cwd `apps/desktop/src-tauri`）

任一失败：打印失败步骤和一句“先运行 `scripts/doctor.py`”，返回 1。

### 5.12 `scripts/dev.py`

1. 若环境变量 `SENTINEL_DATA_DIR` 未设置，设为 `<仓库根>/.dev-data` 并创建目录，打印 `开发数据目录: <路径>`。**开发时绝不触碰真实的用户数据目录。**
2. 若 `SENTINEL_CORE_CMD` 未设置，不设置（Rust 侧有默认值，见 [02](../../02-技术架构.md) 6.1）。
3. 运行 `pnpm tauri dev`（cwd `apps/desktop`），把退出码原样返回。

### 5.13 `scripts/doctor.py`

```python
TOOLS = [
  # (名称, 版本命令, 是否必需, 安装提示)
  ("git",   ["git", "--version"],     True,  "安装 Xcode 命令行工具或 git-scm.com"),
  ("python3", [sys.executable, "--version"], True, "运行脚本需要 Python >= 3.9"),
  ("uv",    ["uv", "--version"],      True,  "https://docs.astral.sh/uv/"),
  ("node",  ["node", "--version"],    True,  "版本需与 .node-version 的主版本一致"),
  ("pnpm",  ["pnpm", "--version"],    True,  "npm install -g pnpm"),
  ("rustc", ["rustc", "--version"],   True,  "https://rustup.rs"),
  ("cargo", ["cargo", "--version"],   True,  "https://rustup.rs"),
  ("cmake", ["cmake", "--version"],   False, "G0-JEVDB 构建 JEVDB 时需要"),
  ("ninja", ["ninja", "--version"],   False, "G0-JEVDB 构建 JEVDB 时需要"),
]
def collect(run=subprocess.run, which=shutil.which) -> list[ToolStatus]: ...
def format_table(statuses: list[ToolStatus]) -> str: ...
def main(argv=None) -> int: ...   # 缺少任何"必需"工具返回 1
```

输出列：`工具 | 版本 | 必需 | 状态`；缺失的工具在表后单独列出安装提示。额外一行检查 `.node-version` 与 `node --version` 的主版本是否一致，不一致标 `WARN`（不算失败）。

### 5.14 `scripts/check_platform_isolation.py`

```python
@dataclass(frozen=True)
class Finding:
    path: str      # 相对仓库根，用 /
    line: int
    message: str

def scan(root: Path) -> list[Finding]: ...
def main(argv=None) -> int: ...    # 有发现则打印并返回 1
```

规则：

1. 只扫描扩展名为 `.py .rs .ts .tsx .js .jsx` 的文件；跳过目录 `.git node_modules target dist .venv __pycache__ .kiro docs design contracts`，以及路径含 `/generated/` 的文件。
2. **平台层白名单**（这些路径下允许出现平台判断）：`core/sentinel/platform/`、`apps/desktop/src-tauri/src/platform/`、`core/tests/platform/`、`scripts/`。
3. 禁止的模式（每行逐一匹配，正则）：

| 语言 | 模式 |
|---|---|
| Python | `\bsys\.platform\b`、`\bos\.name\b`、`\bplatform\.(system\|win32_ver\|mac_ver)\b`、`from\s+sys\s+import\s+.*\bplatform\b` |
| Rust | `\bcfg!?\s*\(\s*(target_os\|windows\|unix\|target_family)`、`#\[cfg\(.*target_os` |
| TS / JS | `\bprocess\.platform\b`、`\bnavigator\.platform\b`、`\bnavigator\.userAgent(Data)?\b` |

4. **成对脚本**：`scripts/` 下每个 `X.sh` 必须有 `X.ps1`，反之亦然，否则报 `缺少成对脚本: X.ps1`（或 `X.sh`）。**文件名以下划线开头的辅助脚本（如 W-01 的 `_py.ps1`）不要求成对**。
5. 文件无法按 UTF-8 解码 → 报错，不静默跳过。

注意：`core/sentinel/platform/__init__.py` 里的 `sys.platform` 在白名单内，是允许的。

### 5.15 `.sh` 包装（`check.sh`）

```sh
#!/usr/bin/env sh
exec python3 "$(dirname "$0")/check.py" "$@"
```

其余三个同样结构，只换文件名。

## 6. 实现步骤

1. **环境**：`python3 scripts/doctor.py` 还没有，先手工确认 `uv --version`、`node --version`、`cargo --version`。运行 `npm install -g pnpm`，记录 `pnpm --version`。
2. **根文件**：创建 4.1 的文件。`.node-version` 先写 `node --version` 的主版本。
3. **脚本先行（TDD）**：先写 8.1 里 `scripts/tests/` 的三个测试文件并运行确认失败，再实现 `check.py`、`check_platform_isolation.py`、`doctor.py`、`setup.py`、`dev.py`、`make_placeholder_icon.py` 和 `.sh` 包装。
4. **Python 工程**：创建 `core/pyproject.toml`、`.python-version`，运行 `cd core && uv sync`，确认 `uv.lock` 生成且 `duckdb` 为 1.4.3。再写 `sentinel/__init__.py`、平台层、`conftest.py`、两个测试，先让测试失败再让它通过。
5. **前端工程**：创建 `package.json` 等配置，运行 `cd apps/desktop && pnpm install`，确认生成 `pnpm-lock.yaml`。写 `Hello.test.tsx`（先失败）→ `Hello.tsx` → `main.tsx`。运行 `pnpm lint && pnpm typecheck && pnpm test && pnpm build`。
6. **Tauri 工程**：创建 4.4 的文件。`python3 scripts/make_placeholder_icon.py --out /tmp/sentinel-icon.png`，然后 `cd apps/desktop && pnpm tauri icon /tmp/sentinel-icon.png`。运行 `cargo fmt` 和 `cargo clippy --all-targets -- -D warnings`（cwd `src-tauri`），修到零警告。
7. **占位文件**：创建头部 `stubs` 列出的 8 个文件。`windows.rs` 在 Windows 上必须能**编译**（行为是最小空实现），在 macOS 上不参与编译。
8. **许可证清单**：写 `THIRD_PARTY.md`。
9. **整体检查**：运行 `scripts/check.sh`，必须全绿（步骤 `contrast`、`generated-*`、`e2e` 因文件不存在显示 `SKIP`）。
10. **人工冒烟（唯一的人工步骤）**：运行 `scripts/dev.sh`，应该弹出标题为“投资逻辑哨兵”的窗口，内容是“投资逻辑哨兵”标题，顶部为 macOS 覆盖式标题栏；在开发者工具里确认 `document.documentElement.dataset.platform === "macos"`。关闭窗口后终端里的进程退出。把截图路径写进状态文件。
11. **提交**：按 [10](../../10-协作与工作包规范.md) 写状态文件。

## 7. 错误与边界情况

| 情形 | 行为 |
|---|---|
| `pnpm`、`uv`、`cargo` 不在 PATH | `check.py` 对应步骤 `FAIL`，提示运行 `doctor.py`；不抛异常 |
| 仓库路径含空格 | 所有脚本用列表形式调用子进程；有专门的测试（8.1 第 7 条） |
| `uv sync` 装不上 `typesafe-sdk` 或 `selectolax` | 停下，写变更申请（类型“需要新依赖”或“做不到”），**不要**换成别的包 |
| Node 26 下前端工具链报错 | 按 4.1 `.node-version` 一行的说明降到 Node 22 并记录 |
| `check_platform_isolation.py` 扫到 `scripts/` 之外的平台判断 | 报 `path:line: 平台判断只允许出现在平台层: <命中的文本>`，返回 1 |
| `cargo clippy` 在 Windows 占位文件上有警告 | 该文件在 macOS 上不参与编译，所以不影响本工作包；Windows 车道在 W-00 记录 |
| 带泛型方法的 trait 不是对象安全 | 见 5.9 的说明 |

## 8. 测试（先写）

### 8.1 测试清单

**`scripts/tests/test_check_runner.py`**（用假的 `runner` 和 `which`，不真的执行命令）

| 测试名 | 输入 | 期望 |
|---|---|---|
| `test_skips_step_when_required_path_missing` | 一个步骤 `requires=["nope"]` | 输出含 `SKIP`；返回 0；`runner` 没被调用 |
| `test_runs_step_and_reports_pass` | `requires` 存在，`runner` 返回码 0 | 输出含 `PASS`；返回 0 |
| `test_failure_does_not_stop_later_steps_and_returns_1` | 第一步返回码 1，第二步返回码 0 | 第二步仍被调用；返回 1；汇总行含 `失败 1` |
| `test_only_filter_runs_selected_steps` | 三个步骤，`only=["b"]` | 只有 `b` 被调用，其余 `SKIP`（未选中） |
| `test_optional_step_requires_flag` | `needs_flag="e2e"`，`flags=set()` | `SKIP`；`flags={"e2e"}` 时被运行 |
| `test_missing_executable_is_failure_with_hint` | `which` 对 `pnpm` 返回 `None` | 输出含 `FAIL` 与 `doctor`；不抛异常；返回 1 |
| `test_paths_with_spaces_are_passed_as_single_argv_items` | `root` 是含空格的临时目录，`cwd` 含空格 | `runner` 收到的 `cwd` 完整等于该路径；`argv` 里没有被拆分的片段；没有 `shell=True` |
| `test_python_placeholder_is_replaced` | `command=["{python}", "x.py"]` | `runner` 收到的 `argv[0] == sys.executable` |
| `test_list_flag_prints_steps_without_running` | `--list` | 输出含每个步骤名；`runner` 没被调用 |

**`scripts/tests/test_check_platform_isolation.py`**（在临时目录里造文件树）

| 测试名 | 输入 | 期望 |
|---|---|---|
| `test_python_sys_platform_outside_platform_layer_is_reported` | `core/sentinel/app/x.py` 含 `import sys\nif sys.platform == "win32": pass` | 1 条发现，`path` 为 `core/sentinel/app/x.py`，`line` 为 2 |
| `test_sys_platform_inside_platform_layer_is_allowed` | 同样内容放在 `core/sentinel/platform/__init__.py` | 0 条 |
| `test_rust_cfg_target_os_outside_platform_layer_is_reported` | `apps/desktop/src-tauri/src/lib.rs` 含 `#[cfg(target_os = "macos")]` | 1 条 |
| `test_rust_cfg_inside_platform_layer_is_allowed` | 同样内容放在 `…/src/platform/mod.rs` | 0 条 |
| `test_ts_process_platform_is_reported` | `apps/desktop/src/x.ts` 含 `process.platform` | 1 条 |
| `test_ts_navigator_user_agent_is_reported` | 含 `navigator.userAgent` | 1 条 |
| `test_generated_and_vendor_dirs_are_ignored` | `node_modules/a.js`、`apps/desktop/src/rpc/generated/a.ts` 含违规内容 | 0 条 |
| `test_unpaired_shell_script_is_reported` | `scripts/a.sh` 存在而 `scripts/a.ps1` 不存在 | 1 条，消息含 `a.ps1` |
| `test_paired_scripts_pass` | 两个都在 | 0 条 |
| `test_underscore_helper_scripts_are_exempt_from_pairing` | 只有 `scripts/_py.ps1`，没有 `_py.sh` | 0 条 |
| `test_unpaired_ps1_script_is_reported` | `scripts/b.ps1` 存在而 `scripts/b.sh` 不存在 | 1 条，消息含 `b.sh` |
| `test_non_utf8_file_is_reported_not_skipped` | 写入字节 `b"\xff\xfe"` 的 `.py` | 1 条，消息含 `UTF-8` |
| `test_clean_tree_passes_and_main_returns_0` | 无违规 | `main` 返回 0 |

**`scripts/tests/test_doctor.py`**

| 测试名 | 输入 | 期望 |
|---|---|---|
| `test_missing_required_tool_returns_1` | `which("pnpm")` 为 `None` | `main` 返回 1；输出含 `pnpm` 与安装提示 |
| `test_missing_optional_tool_returns_0` | 只缺 `cmake` | 返回 0 |
| `test_node_major_mismatch_is_warning_only` | `.node-version` 为 `22`，`node --version` 输出 `v26.1.0` | 输出含 `WARN`；返回 0 |

**`core/tests/unit/test_smoke.py`**

| 测试名 | 期望 |
|---|---|
| `test_package_is_importable_and_versioned` | `sentinel.__version__ == "0.1.0"` |
| `test_duckdb_version_is_pinned` | `duckdb.__version__ == "1.4.3"` |
| `test_platform_name_is_macos_here` | 在本机上 `sentinel.platform.name() == "macos"`（标记 `@pytest.mark.macos`） |
| `test_new_york_timezone_handles_dst_boundaries` | `ZoneInfo("America/New_York")` 不抛异常（Windows 缺 `tzdata` 时这里会失败）。用 `datetime(…, tzinfo=timezone.utc).astimezone(ny).utcoffset()` 检查四个时刻：`2026-03-08 06:59 UTC` → −5 小时；`2026-03-08 07:00 UTC` → −4 小时（夏令时开始）；`2026-11-01 05:59 UTC` → −4 小时；`2026-11-01 06:00 UTC` → −5 小时（夏令时结束） |
| `test_posix_is_process_alive` | 当前进程 `os.getpid()` 返回 `True`；一个刚结束的子进程 PID 返回 `False`；`0` 与 `-1` 返回 `False`（`@pytest.mark.macos`） |
| `test_posix_file_lock_is_exclusive` | 在临时目录，第一个 `file_lock(p)` 持有期间，第二个抛 `AlreadyRunning`；释放后第二个可以获得（`@pytest.mark.macos`） |
| `test_posix_harden_permissions_sets_modes` | 目录 `0o700`，文件 `0o600`；不存在的路径抛 `FileNotFoundError`（`@pytest.mark.macos`） |
| `test_posix_default_data_dir_is_under_application_support` | 路径以 `Library/Application Support/Sentinel` 结尾（`@pytest.mark.macos`） |

**`core/tests/unit/test_layering.py`**

| 测试名 | 输入 | 期望 |
|---|---|---|
| `test_imported_layers_handles_absolute_and_relative_imports` | 源码含 `from sentinel.storage import db` 与 `from ..domain import models`，`module_path="sentinel.http.client"` | 返回 `{"storage", "domain"}` |
| `test_imported_layers_ignores_third_party_and_always_allowed` | 源码含 `import numpy`、`from sentinel.errors import X` | 返回空集合（`errors` 属于 ALWAYS_ALLOWED，不计入层依赖） |
| `test_repository_respects_layer_rules` | 扫描真实的 `core/sentinel/` | 没有违规；失败时消息列出 `文件 → 违规依赖` |
| `test_domain_layer_has_no_internal_dependencies` | 构造 `sentinel.domain.x` 导入 `sentinel.storage` | 被判定为违规（用函数直接测，不写文件） |

**`apps/desktop/src/Hello.test.tsx`**

| 测试名 | 期望 |
|---|---|
| `renders the product name as a heading` | 渲染 `<Hello />` 后，`screen.getByRole("heading", { level: 1 }).textContent === "投资逻辑哨兵"` |

**`core/tests/conftest.py`**：`pytest_collection_modifyitems` 里读取 `sentinel.platform.name()`，对标记 `macos` / `windows` 但不匹配当前平台的用例添加 `skip`，原因写 `只在 <平台> 上运行`。**不得**在这个文件里使用 `sys.platform`。

### 8.2 Fixture
无。

## 9. 验收

### 9.1 命令与期望输出

```bash
# 1. 脚本自身的测试
python3 -m unittest discover -s scripts/tests -v
# 期望：包含 check_docs、check_runner、platform_isolation、doctor 的全部用例，最后一行 OK

# 2. 工具链
python3 scripts/doctor.py
# 期望：表格里 git、python3、uv、node、pnpm、rustc、cargo 都有版本号；退出码 0

# 3. 安装
scripts/setup.sh
# 期望：无 FAIL；core/uv.lock、apps/desktop/pnpm-lock.yaml、apps/desktop/src-tauri/Cargo.lock 都存在

# 4. Python
cd core && uv run pytest -q
# 期望：全部通过；macOS 标记的用例在本机上运行而非 skipped

grep -A1 'name = "duckdb"' uv.lock
# 期望：紧跟的一行含 version = "1.4.3"

# 5. 前端
cd apps/desktop && pnpm lint && pnpm typecheck && pnpm test && pnpm build
# 期望：全部成功；vitest 显示 1 passed

# 6. Rust
cd apps/desktop/src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings
# 期望：无输出，退出码 0

# 7. 一键检查
scripts/check.sh
# 期望：每行 PASS 或 SKIP；汇总 "失败 0"；SKIP 的只有 contrast、generated-ts、generated-proto、e2e

# 8. 平台隔离（故意破坏再恢复）
echo 'import sys; sys.platform' > core/sentinel/zz_tmp.py && python3 scripts/check_platform_isolation.py; echo "exit=$?"; rm core/sentinel/zz_tmp.py
# 期望：打印 core/sentinel/zz_tmp.py:1 的发现，exit=1；删除文件后再运行 exit=0
```

### 9.2 完成清单
- [ ] 第 4 节每个文件都已创建，`owns` 之外没有任何改动
- [ ] 第 8.1 节每个测试都存在，且状态文件里有“先失败”的证据
- [ ] 9.1 的 8 条命令全部通过
- [ ] `duckdb` 在锁文件中为 1.4.3
- [ ] `THIRD_PARTY.md` 每个包都有许可证，`UNKNOWN` 的已在状态文件列出
- [ ] 人工冒烟：窗口弹出，`data-platform` 为 `macos`，截图已附
- [ ] 8 个 Windows 占位文件存在
- [ ] 已写 `docs/wp/status/WP-00.md`，其中“实际接口与工作包 5.1 的差异”一栏如实填写（尤其是 5.9 的 trait 对象安全问题）

## 10. 给下游的交接

| 下游工作包 | 它会使用 | 约定 |
|---|---|---|
| 所有 Python 工作包 | `core/pyproject.toml`、`uv run pytest`、`@pytest.mark.macos/windows/integration` | 不得修改依赖；新依赖走变更申请 |
| C-00、C-01 | `core/sentinel/__init__.py`、`platform.file_lock`、`platform.is_process_alive`、`platform.AlreadyRunning` | 签名见 5.2 |
| U-00 | `package.json` 脚本、`vite.config.ts`、`Hello.*`、`index.html` | U-00 接手并删除 `Hello.*` |
| C-02 | `lib.rs`、`platform::current()`、`capabilities/default.json`、`tauri.conf.json` 中的 `csp: null` | C-02 负责设置最终 CSP |
| W-01 | 8 个占位文件、`platform` 接口 | 头部 `stubs` 列出，W-01 的 `owns` 覆盖它们 |
| 所有工作包 | `scripts/check.sh` | 完成定义里要求它全绿 |

## 11. 风险与回退

| 风险 | 征兆 | 回退 |
|---|---|---|
| `typesafe-sdk` 或 `selectolax` 在 Python 3.12 / arm64 上装不上 | `uv sync` 报错 | 变更申请；不得自行换包 |
| Node 26 与 Vite、Tauri CLI 不兼容 | `pnpm build` 或 `pnpm tauri` 报错 | 降到 Node 22 LTS |
| `Platform` trait 不是对象安全 | 编译报错 `the trait cannot be made into an object` | 按 5.9 的说明调整，并记录 |
| `pnpm tauri icon` 生成的图标不满足 `tauri.conf.json` 的路径 | 打包时报找不到图标 | 以实际生成的文件名为准，同步修改 `bundle.icon` |

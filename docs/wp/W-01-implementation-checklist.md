# W-01 测试与实现清单

这是 2026-11-02 的准备记录。2026-11-04 的本机实施和验收见 [W-01 完成报告](status/W-01.md)。

- 状态：本地准备；等待 W-00 审核通过后实施。
- 日期：2026-11-02。
- 分支：`codex/w01-preparation`，基于 W-00 交付提交 `ed699cc`。
- 产品基线：`5b79539708557884c925138daa4776d1b2321c7c`。
- 本轮授权工作时限：北京时间 22:44:33—23:44:33；到点停止。
- 本轮不上传，生产平台实现保持原样。

## 1. 开始实现前的条件

- [ ] 已取得 W-00 审核通过记录，记录审核人、日期与结论。
- [ ] 测试目录命名冲突已有决定：[pytest CR](cr/CR-20261102-w01-pytest-package.md)。
- [ ] ACL 目标和参考步骤已统一：[ACL CR](cr/CR-20261102-w01-acl-contract.md)。
- [ ] 存活判定与 259 边界已有决定：[进程 CR](cr/CR-20261102-w01-process-state.md)。
- [ ] 未知检查步骤归共享入口处理：[检查入口 CR](cr/CR-20261102-w01-unknown-check-step.md)。

W-00 审核通过后，可先做无歧义的目录、锁与包装器部分；有未决语义的函数等待相应决定，不自行更改共享接口。已有 W-00 的 mypy、doctor 和开发监听 CR 继续保留，不在 wrapper 中掩盖。

## 2. 已准备的测试

| 范围 | 准备物 | 当前基线结果 | 用途 |
|---|---|---|---|
| Python 平台行为 | `core/tests/platform/test_windows_platform.py` | 临时 importlib 模式：1 通过 / 18 失败 | 12 项原清单及非空锁、异常释放、文件 ACL、259、越界 PID等边界 |
| 默认 pytest 验收命令 | 同目录的空 `__init__.py` | 收集退出 2 | 单独暴露与标准库 platform 重名的问题 |
| PowerShell 包装器 | `scripts/tests/test_ps1_wrappers.py` | 7 方法中 1 通过 / 6 失败；双宿主 subTest 共20项失败断言 | 路径、参数、退出码、四个包装器、BOM/CRLF及共享入口 |
| Rust 平台生命周期 | 临时 `rust-probe` | 2 通过 / 1 失败 | 平台脚本、已退出子进程、受控孙进程清理 |
| Rust 无控制台启动 | 临时隐藏控制台探针 | 退出101，子进程仍继承控制台 | 避免“父进程本来无控制台”造成假通过 |
| 原生 API 实验 | `api_assays.py` | 实验断言通过 | 验证规范中的 ACL、259、等待权限、锁偏移问题 |

Python 的18项失败来自未实现平台行为；跨进程用例会因锁持有子进程提前退出而报告握手失败。它们是实施前红灯，不是完成验收。默认导入的收集失败另记，不混入19项行为用例。

### 2.1 夹具约束

- Python 的文件与 ACL 操作只作用于 pytest 自己创建的临时对象。
- ACL 按 SID 读取；预置显式广泛授权后再测试，实际读写验证可用性；finally 恢复目标原 DACL。
- 锁持有子进程采用握手和有界回收，失败也结束自己创建的子进程。
- Rust 只跟踪自己启动的根 PID 和孙 PID；持有进程句柄防止观察期间 PID 复用，初始化失败也有清理守卫。
- Rust 等待显式区分正常退出、超时与查询错误；不把查询错误当“已退出”。
- PowerShell 测试使用包装器的临时副本和受控 Python 目标，不会运行真实 setup 安装或启动真实 dev GUI。
- 原生标题栏、样式和 `dataset.platform` 仍留到实现后的窗口验收。

## 3. 实施顺序

### 第一步：测试目录组织

1. 应用协调者选定的导入方案。
2. 运行原 `uv run pytest -q tests/platform`，确认能收集所有用例。
3. 保留当前红灯记录；不得将 Windows 用例改为跳过来消除失败。

### 第二步：Python 路径与文件锁

涉及 `core/sentinel/platform/windows.py`：

- `name` 返回 windows。
- `default_data_dir` 只返回路径；LOCALAPPDATA 优先，缺失时走 home/AppData/Local；不创建目录。
- `file_lock` 创建父目录并以 a+b 打开；**获取锁前与释放前都 seek(0)**。
- 锁区固定为第0字节；允许空文件锁区超出EOF，不写占位字节、不截断内容。
- 获锁失败关闭本次句柄，保留异常因果；没有获锁时不尝试解锁。
- 正常退出及 with 体异常都释放锁；保留锁文件。
- 本地与跨进程互斥、异常后再获取、已有非空文件和外部第0字节竞争均通过。

### 第三步：进程存活

- ctypes 的 HANDLE 使用指针宽度，所有 argtypes/restype 显式设置。
- 无效/越界 PID 不应截断成有效的别的 PID。
- OpenProcess 拒绝访问按确定的保守规则处理。
- 已退出259边界按CR决定处理；如果等待进程对象，访问掩码同时包含所需等待权限。
- 不读取失败查询留下的无效输出；成功打开的句柄在每条路径恰好关闭一次。
- 运行当前进程、普通退出、259退出和DWORD越界用例。

### 第四步：ACL

- 先确定“严格当前用户专用”或“清除指定广泛主体”的目标。
- whoami失败与icacls失败应有明确错误，不宣称权限已经收紧。
- 文件和目录参数逐项传递，支持中文与空格；目录继承标志按目标设置。
- 验证显式授权和实际读写；明确只处理目标自身还是递归已有子项。
- 仅在临时目标完成测试后再进入产品目录的启动联调。
- 不把 `icacls /reset` 作为“当前用户专用”的成功结果；它只可恢复受控测试夹具。

### 第五步：PowerShell 包装器

涉及 `scripts/_py.ps1` 和四个包装器：

- 探测顺序 py -3、python、python3，真实检查版本≥3.9。
- 返回扁平“可执行路径+前置参数”数组；单元素候选的前置参数为空。
- 在 `$PSScriptRoot` 定位目标Python脚本，参数逐项传递。
- 原样返回0、7等真实退出码；共享检查失败不得被改为成功。
- 每个包装器≤15行；UTF-8 BOM、CRLF，中文提示不乱码。
- WinPS5.1与已安装的PowerShell7均验证。
- 空字符串和嵌入引号的跨宿主完整透传另行验证，当前测试未证明支持。
- 详细草稿在准备包 `support/powershell-implementation-checklist.md`。

### 第六步：Rust 生命周期

涉及 `apps/desktop/src-tauri/src/platform/windows.rs`：

- 保持原 Platform trait，不改共享签名。
- 平台初始化脚本保留首次绘制前与DOMContentLoaded的windows标记。
- 窗口明确启用原生decorations。
- prepare_core_command设置CREATE_NO_WINDOW，用隐藏控制台父进程探针验证子进程确实没有控制台。
- kill_process_tree仅针对传入Child的PID树：结束子树、处理已退出情况、回收根进程句柄。
- 用受控父/孙进程证明不会留下孙进程，不以全机所有python/uv/node消失作为标准。
- 把要求的 `init_script_sets_windows_platform` 放入本文件单元测试。
- 临时探针只读引入当前模块；实现完成后重新跑，而非把探针代码当产品实现。

### 第七步：配置、整体验收与交接

- 保持Windows NSIS配置和原三项样式变量；没有视觉证据时不随意改样式。
- setup.ps1完成依赖安装，锁文件保持不变。
- check.ps1整体检查；A类失败清零，B类按已审CR如实列出。
- 运行Rust测试、fmt、clippy与平台隔离检查。
- 启动dev.ps1，验证原生标题栏、平台标记，记录本次进程树关闭结果。
- 向开发笔记追加两节，完成W-01状态报告与对等矩阵。
- 工作包头部与完成清单的文件归属在正式交付前复核，尤其是对等矩阵更新范围。
- 本地提交后等待评审，不合并main。

## 4. 推荐验证命令

先在工作区启用既有局部工具环境：

```powershell
. ./tools/w00/session.ps1
```

在项目core目录：

```powershell
uv run pytest -q tests/platform
# 当前预期：收集失败；导入方案确定后应可执行。
uv run pytest -q tests/platform --import-mode=importlib
# 当前准备诊断：1通过、18失败；不能替代上条的正式验收。
uv run ruff check tests/platform
uv run ruff format --check tests/platform
```

在仓库根目录：

```powershell
py -3 -m unittest discover -s scripts/tests -p test_ps1_wrappers.py -v
py -3 scripts/check_platform_isolation.py
py -3 scripts/check_docs.py --strict
```

Rust临时探针在工作区运行，设置项目Python与原有target目录后：

```powershell
cargo test --offline --manifest-path tmp/w01-preparation/rust-probe/Cargo.toml --lib -- --test-threads=1
py -3 tmp/w01-preparation/run_hidden_console_probe.py
```

需要重建控制台探针时先执行对应 `cargo build --offline --bin creation_flags_probe`，并指定同一manifest-path与CARGO_TARGET_DIR。所有探针都属于准备材料，不进入生产模块。

## 5. 本轮停点

当前没有W-00审核通过记录。停在测试、实验和实现清单阶段；收到通过结论后才修改平台实现。四份新CR是待讨论草案，不代表已经采纳。时限到点即停止，不因等待审核延长运行。

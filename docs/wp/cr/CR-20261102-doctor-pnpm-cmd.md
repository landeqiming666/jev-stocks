# CR-20261102-doctor-pnpm-cmd

- 提出者（工作包 ID）：W-00
- 类型：平台问题
- 基线：`5b79539708557884c925138daa4776d1b2321c7c`
- 状态：待协调者评审

## 现象与复现

按官方 npm 方式安装 `pnpm@12.16.1` 后，PATH 中可找到 `pnpm.CMD`，完整路径执行返回版本 `12.16.1`，前端 lint/typecheck/test/build 均通过。

运行 `py -3 scripts\doctor.py` 却显示：

```text
pnpm | 未知 | 是 | OK
```

doctor 退出码为 0。相同环境下的最小复现：

```python
import shutil
import subprocess
print(shutil.which("pnpm"))  # 找到 .../node_modules/.bin/pnpm.CMD
subprocess.run(["pnpm", "--version"], check=True)
# FileNotFoundError: [WinError 2] 系统找不到指定的文件。
```

[doctor.py](../../../scripts/doctor.py) 检查了 `shutil.which`，但调用时没有使用其解析出的完整路径；异常又被转为“未知”，`present` 仍为真。因此体检无法可靠区分“文件存在”和“能正常执行”。同仓库的 setup/check 已使用解析后的可执行路径。

## 依据

- [W-00](../mvp0/W-00-windows-survey.md)：工具版本应有真实输出；共享脚本问题按 B 类交接。
- [统一脚本入口](../../02-技术架构.md#23-统一入口)。

## 方案与影响

1. doctor 使用 `which` 返回的实际路径执行命令，并将启动异常、非零退出码与正常版本输出分别标记；补 Windows CMD 包装器和非零退出的回归用例。影响 doctor 与其测试。
2. 统一共享脚本中的命令解析和探测逻辑，让 doctor/setup/check/dev 使用相同规则；同时保留存在性与可运行性两个状态。影响数个共享入口，改动较大。

W-00 未应用任何修复；验证工具版本时另行执行了解析后的完整路径。

- 阻塞的工作包：doctor 工具链结论的可靠性；不阻塞已验证的前端构建。
- 决定：待协调者填写。


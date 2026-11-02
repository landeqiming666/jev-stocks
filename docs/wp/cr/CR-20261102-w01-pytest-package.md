# CR-20261102-w01-pytest-package

- 提出者：W-01 测试准备。
- 类型：文档错误 / 平台测试组织。
- 状态：草案，待协调者决定；未修改共享配置。

## 现象

按 W-01 §4 创建 `core/tests/platform/__init__.py` 后，原验收命令
`uv run pytest -q tests/platform` 在收集阶段退出 2：

```text
ModuleNotFoundError: No module named 'platform.test_windows_platform'; 'platform' is not a package
```

`core/tests` 本身没有 `__init__.py`，默认 prepend 导入把子目录当作顶层 `platform` 包，与已加载的 Python 标准库模块重名。

在不修改配置的情况下，临时加 `--import-mode=importlib` 可以收集用例，并暴露真实的 W-01 占位失败。该诊断命令不等于原验收命令已经通过。

## 依据与方案

- [W-01](../mvp0/W-01-windows-platform-layer.md) §4、§8、§9。
- [pytest 导入模式](https://docs.pytest.org/en/stable/explanation/pythonpath.html#import-modes)。

1. 删除 W-01 对该空 `__init__.py` 的要求，让测试目录不成为名为 `platform` 的顶层包。pytest 的父目录 conftest 和平台标记不要求测试必须是 Python 包。影响 W-01 文件清单与该空文件。
2. 协调者统一采用 importlib 模式，或把 `core/tests` 设为明确的测试包。影响共享 pytest 配置或 `core/tests/__init__.py`，需评估其他测试的导入。

- 建议：优先采用最小目录组织调整；在决定前保留已观测的两种命令结果。
- 关闭条件：原验收命令能收集 Windows 测试；macOS 平台标记仍正确跳过；既有测试无导入回归。
- 决定：待填写。

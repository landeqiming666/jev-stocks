"""分层规则测试：把 02-技术架构.md 第 16 节的依赖方向编码为可执行检查。"""

from __future__ import annotations

import ast
from pathlib import Path

ALWAYS_ALLOWED = {"ids", "clock", "errors", "messages", "logging_setup"}

LAYER_RULES: dict[str, set[str]] = {
    "logging_setup": {"security"},
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
    "rpc": {"domain", "platform"},
    "settings": {"domain", "storage", "security", "secrets"},
    "secrets": {"domain", "security", "platform"},
    "scan": {"domain", "storage", "markets", "semantic", "rpc"},
    "app": {"*"},
    "evaluation": {"*"},
    "demo": {"*"},
}


def _relative_base(module_path: str, level: int) -> list[str]:
    """把相对导入的 level 回溯成绝对模块前缀。

    __init__.py 以 sentinel.pkg.__init__ 传入，因此模块自身总能按“所在包”处理。
    """
    package = module_path.split(".")[:-1]
    if level <= 1:
        return package
    return package[: -(level - 1)]


def imported_layers(source: str, module_path: str) -> set[str]:
    """返回 source 依赖的 sentinel 顶层子包名集合。"""
    tree = ast.parse(source)
    layers: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "sentinel" and len(parts) > 1:
                    layers.add(parts[1])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = _relative_base(module_path, node.level)
                if node.module:
                    parts = parts + node.module.split(".")
            else:
                parts = (node.module or "").split(".")
            if not parts or parts[0] != "sentinel":
                continue
            if len(parts) > 1:
                layers.add(parts[1])
            else:
                for alias in node.names:
                    if alias.name in LAYER_RULES or alias.name in ALWAYS_ALLOWED:
                        layers.add(alias.name)

    return {layer for layer in layers if layer in LAYER_RULES and layer not in ALWAYS_ALLOWED}


def violations(source: str, module_path: str) -> set[str]:
    """返回当前层不允许依赖的层名。同层内部导入不算违规。"""
    current = module_path.split(".")[1]
    allowed = LAYER_RULES.get(current, set())
    if "*" in allowed:
        return set()
    return imported_layers(source, module_path) - allowed - {current}


def test_imported_layers_handles_absolute_and_relative_imports() -> None:
    source = "from sentinel.storage import db\nfrom ..domain import models\n"
    assert imported_layers(source, "sentinel.http.client") == {"storage", "domain"}


def test_imported_layers_ignores_third_party_and_always_allowed() -> None:
    source = "import numpy\nfrom sentinel.errors import X\n"
    assert imported_layers(source, "sentinel.domain.models") == set()


def test_repository_respects_layer_rules() -> None:
    package_root = Path(__file__).resolve().parents[2] / "sentinel"
    problems: list[str] = []
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(package_root).with_suffix("")
        module_path = "sentinel." + ".".join(relative.parts)
        bad = violations(path.read_text(encoding="utf-8"), module_path)
        if bad:
            problems.append(f"{path} → {', '.join(sorted(bad))}")
    assert not problems, "\n".join(problems)


def test_domain_layer_has_no_internal_dependencies() -> None:
    source = "from sentinel.storage import db\n"
    assert violations(source, "sentinel.domain.x") == {"storage"}


def test_logging_can_import_redaction_but_not_business_services() -> None:
    assert (
        violations("from .security.redact import redact_obj\n", "sentinel.logging_setup") == set()
    )
    assert violations("from .storage import Database\n", "sentinel.logging_setup") == {"storage"}


def test_business_layers_can_use_foundation_logging() -> None:
    assert (
        imported_layers("from sentinel.logging_setup import get_logger\n", "sentinel.rpc.server")
        == set()
    )
    assert (
        violations("from sentinel.platform import is_process_alive\n", "sentinel.rpc.server")
        == set()
    )

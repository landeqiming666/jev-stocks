#!/usr/bin/env python3
"""文档一致性检查。仅用标准库，兼容 Python 3.9。

用法：
    python3 scripts/check_docs.py            普通模式：状态为“待重写”的文档只给警告
    python3 scripts/check_docs.py --strict   严格模式：状态为“待重写”的文档算错误

当前检查项：
    1. 链接：Markdown 相对链接指向的文件和 #锚点必须存在（代码块内的链接忽略）。
    2. 文档名：正文里出现的 `NN-名称.md` 必须是 docs/ 下真实存在的文件。
    3. 状态：docs/ 下每份文档头部必须有“状态：已定稿 / 待重写”。
    4. 工作包：docs/wp/{mvp0,v1}/*.md 的头部字段、ID 唯一、依赖存在且无环。

新增检查时：写一个 (root, files, report, strict) -> None 的函数，追加到 CHECKS。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import unquote

SKIP_DIRS = {"node_modules", "target", "dist", "__pycache__", "build"}

FrontMatter = Dict[str, Union[str, List[str]]]


@dataclass
class Report:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def iter_markdown(root: Path) -> List[Path]:
    """列出 root 下全部 .md 文件，跳过隐藏目录和构建产物目录。"""
    found: List[Path] = []
    for current, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS
        )
        for name in sorted(filenames):
            if name.endswith(".md"):
                found.append(Path(current) / name)
    return found


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


_FENCE = re.compile(r"^\s*(```+|~~~+)")


def mask_fences(text: str) -> str:
    """把围栏代码块整体替换为空行，保持行号不变。"""
    out: List[str] = []
    fence: Optional[str] = None
    for line in text.split("\n"):
        m = _FENCE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)[0]
                out.append("")
            else:
                out.append(line)
        else:
            out.append("")
            if m and m.group(1)[0] == fence:
                fence = None
    return "\n".join(out)


_INLINE_CODE = re.compile(r"`[^`\n]*`")


def mask_inline_code(text: str) -> str:
    return _INLINE_CODE.sub(lambda m: " " * len(m.group()), text)


_LINK_TARGET = re.compile(r"\]\([^)\s]*\)")


def mask_link_targets(text: str) -> str:
    """把 ](...) 的目标部分替换为空白，避免和“文档名”检查重复报错。"""
    return _LINK_TARGET.sub(lambda m: "]" + " " * (len(m.group()) - 1), text)


# --------------------------------------------------------------------------
# 锚点
# --------------------------------------------------------------------------

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_HTML_ANCHOR = re.compile(r"""(?:id|name)\s*=\s*["']([^"']+)["']""")


def slugify(heading: str) -> str:
    """按 GitHub 规则生成锚点：去格式符、转小写、去标点、空格变连字符。"""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = text.replace("`", "").replace("*", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def collect_anchors(text: str) -> Set[str]:
    anchors: Set[str] = set()
    seen: Dict[str, int] = {}
    for line in mask_fences(text).split("\n"):
        m = _HEADING.match(line)
        if m:
            slug = slugify(m.group(1))
            count = seen.get(slug, 0)
            anchors.add(slug if count == 0 else "%s-%d" % (slug, count))
            seen[slug] = count + 1
        for a in _HTML_ANCHOR.findall(line):
            anchors.add(a.lower())
    return anchors


# --------------------------------------------------------------------------
# 检查 1：链接
# --------------------------------------------------------------------------

_LINK = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def check_links(root: Path, files: List[Path], report: Report, strict: bool) -> None:
    anchor_cache: Dict[Path, Set[str]] = {}

    def anchors_of(path: Path) -> Set[str]:
        if path not in anchor_cache:
            anchor_cache[path] = collect_anchors(read(path))
        return anchor_cache[path]

    for source in files:
        text = mask_inline_code(mask_fences(read(source)))
        for lineno, line in enumerate(text.split("\n"), 1):
            for m in _LINK.finditer(line):
                target = m.group("target")
                if _SCHEME.match(target):
                    continue
                path_part, _, anchor = target.partition("#")
                path_part, anchor = unquote(path_part), unquote(anchor)
                if path_part == "":
                    dest = source
                elif path_part.startswith("/"):
                    dest = root / path_part.lstrip("/")
                else:
                    dest = (source.parent / path_part).resolve()
                where = "%s:%d" % (rel(root, source), lineno)
                if not dest.exists():
                    report.errors.append("%s: 链接目标不存在: %s" % (where, target))
                    continue
                if anchor and dest.is_file() and dest.suffix == ".md":
                    if anchor.lower() not in anchors_of(dest):
                        report.errors.append("%s: 锚点不存在: %s" % (where, target))


# --------------------------------------------------------------------------
# 检查 2：文档名引用
# --------------------------------------------------------------------------

_DOC_REF = re.compile(r"(?<![\w/.\-])(?:docs/)?(\d{2}-[\w\-]+\.md)")


def check_doc_names(root: Path, files: List[Path], report: Report, strict: bool) -> None:
    docs_dir = root / "docs"
    for source in files:
        text = mask_link_targets(mask_fences(read(source)))
        for lineno, line in enumerate(text.split("\n"), 1):
            for m in _DOC_REF.finditer(line):
                name = m.group(1)
                if not (docs_dir / name).is_file():
                    report.errors.append(
                        "%s:%d: 引用了不存在的文档 %s" % (rel(root, source), lineno, name)
                    )


# --------------------------------------------------------------------------
# 检查 3：状态标记
# --------------------------------------------------------------------------

_STATUS = re.compile(r"状态[：:]\s*(已定稿|待重写)")


def check_status(root: Path, files: List[Path], report: Report, strict: bool) -> None:
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        report.notes.append("没有 docs/ 目录，跳过状态检查")
        return
    for path in sorted(docs_dir.glob("*.md")):
        head = "\n".join(read(path).split("\n")[:15])
        m = _STATUS.search(head)
        name = rel(root, path)
        if not m:
            report.errors.append(
                '%s: 缺少状态标记（头部需含"状态：已定稿"或"状态：待重写"）' % name
            )
        elif m.group(1) == "待重写":
            message = '%s: 状态仍为"待重写"，内容是旧稿或占位，不可据此开发' % name
            (report.errors if strict else report.warnings).append(message)


# --------------------------------------------------------------------------
# 检查 4：工作包
# --------------------------------------------------------------------------

WP_REQUIRED = ("id", "title", "phase", "platform", "lane", "deps", "size", "owns")
WP_PHASES = ("mvp0", "v1")
WP_SIZES = {"mvp0": ("S", "M"), "v1": ("S", "M", "L")}
WP_PLATFORMS = ("shared", "macos", "windows")
WP_LANES = ("core", "data", "semantic", "ui", "integration", "windows")

_FRONT = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)


def parse_front_matter(text: str) -> Optional[FrontMatter]:
    """解析头部。只支持单行 `key: value` 与 `key: [a, b]`。无头部返回 None。"""
    m = _FRONT.match(text)
    if not m:
        return None
    data: FrontMatter = {}
    for raw in m.group(1).split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            raise ValueError("头部格式错误: %r" % raw)
        value = value.strip()
        if value.startswith("["):
            if not value.endswith("]"):
                raise ValueError("列表缺少右括号: %r" % raw)
            data[key.strip()] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            data[key.strip()] = value
    return data


def _find_cycles(graph: Dict[str, List[str]]) -> List[List[str]]:
    """返回图中的环（每个环只报告一次）。"""
    cycles: List[List[str]] = []
    state: Dict[str, int] = {}  # 1 = 访问中，2 = 已完成
    stack: List[str] = []

    def visit(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if state.get(nxt) == 1:
                cycles.append(stack[stack.index(nxt):] + [nxt])
            elif state.get(nxt) is None:
                visit(nxt)
        stack.pop()
        state[node] = 2

    for node in sorted(graph):
        if state.get(node) is None:
            visit(node)
    return cycles


def _approved_large_package(root: Path, wp_id: str, meta: FrontMatter) -> bool:
    approval = str(meta.get("size_approval", ""))
    if not re.fullmatch(r"cr/[A-Za-z0-9_-]+\.md", approval):
        return False
    folder = (root / "docs" / "wp" / "cr").resolve()
    path = (root / "docs" / "wp" / approval).resolve()
    if folder not in path.parents:
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return bool(
        re.search(r"\b" + re.escape(wp_id) + r"\b", text)
        and "已批准" in text
        and "规模" in text
    )


def check_work_packages(root: Path, files: List[Path], report: Report, strict: bool) -> None:
    wp_root = root / "docs" / "wp"
    paths: List[Path] = []
    for phase in WP_PHASES:
        folder = wp_root / phase
        if folder.is_dir():
            paths += [p for p in sorted(folder.glob("*.md")) if p.name != "README.md"]
    if not paths:
        report.notes.append("docs/wp/ 下还没有工作包，跳过工作包检查")
        return

    by_id: Dict[str, Tuple[Path, FrontMatter]] = {}
    for path in paths:
        name = rel(root, path)
        try:
            meta = parse_front_matter(read(path))
        except ValueError as exc:
            report.errors.append("%s: %s" % (name, exc))
            continue
        if meta is None:
            report.errors.append("%s: 缺少头部（以 --- 开始和结束的字段块）" % name)
            continue
        missing = [k for k in WP_REQUIRED if k not in meta]
        if missing:
            report.errors.append("%s: 头部缺少字段: %s" % (name, ", ".join(missing)))
            continue
        wp_id = str(meta["id"])
        if wp_id in by_id:
            report.errors.append(
                "工作包 ID 重复: %s (%s, %s)" % (wp_id, rel(root, by_id[wp_id][0]), name)
            )
            continue
        by_id[wp_id] = (path, meta)

        if not (path.name == wp_id + ".md" or path.name.startswith(wp_id + "-")):
            report.errors.append('%s: 文件名必须以工作包 ID "%s" 开头' % (name, wp_id))
        phase = str(meta["phase"])
        if phase not in WP_PHASES:
            report.errors.append("%s: phase 必须是 %s 之一" % (name, "/".join(WP_PHASES)))
        elif path.parent.name != phase:
            report.errors.append(
                "%s: phase 为 %s，但文件位于 %s 目录" % (name, phase, path.parent.name)
            )
        elif str(meta["size"]) not in WP_SIZES[phase] and not (
            phase == "mvp0" and str(meta["size"]) == "L" and _approved_large_package(root, wp_id, meta)
        ):
            report.errors.append(
                '%s: size 必须是 %s 之一，当前为 "%s"'
                % (name, "/".join(WP_SIZES[phase]), meta["size"])
            )
        for key in ("deps", "owns", "appends", "stubs"):
            if key in meta and not isinstance(meta[key], list):
                report.errors.append("%s: %s 必须写成 [a, b] 形式" % (name, key))
        platform, lane = str(meta["platform"]), str(meta["lane"])
        if platform not in WP_PLATFORMS:
            report.errors.append("%s: platform 必须是 %s 之一" % (name, "/".join(WP_PLATFORMS)))
        if lane not in WP_LANES:
            report.errors.append("%s: lane 必须是 %s 之一" % (name, "/".join(WP_LANES)))
        if platform == "windows" and lane != "windows":
            report.errors.append("%s: platform 为 windows 时 lane 必须是 windows" % name)
        if lane == "windows" and platform != "windows":
            report.errors.append("%s: lane 为 windows 时 platform 必须是 windows" % name)

    graph: Dict[str, List[str]] = {}
    for wp_id, (path, meta) in by_id.items():
        deps = meta["deps"] if isinstance(meta["deps"], list) else []
        graph[wp_id] = list(deps)
        for dep in deps:
            if dep not in by_id:
                report.errors.append(
                    "%s: %s 依赖不存在的工作包 %s" % (rel(root, path), wp_id, dep)
                )
            elif meta["phase"] == "mvp0" and by_id[dep][1]["phase"] != "mvp0":
                report.errors.append(
                    "%s: %s (mvp0) 不得依赖 %s 工作包 %s"
                    % (rel(root, path), wp_id, by_id[dep][1]["phase"], dep)
                )
            if (
                dep in by_id
                and meta["platform"] != "windows"
                and by_id[dep][1]["platform"] == "windows"
            ):
                report.errors.append(
                    "%s: %s (%s) 不得依赖 Windows 工作包 %s，Windows 车道不能阻塞 Mac"
                    % (rel(root, path), wp_id, meta["platform"], dep)
                )
    for cycle in _find_cycles(graph):
        report.errors.append("依赖成环: " + " -> ".join(cycle))
    _check_ownership(root, by_id, graph, report)


def _norm_path(path: str) -> str:
    return path[2:] if path.startswith("./") else path


def _covers(owner_path: str, path: str) -> bool:
    """owner_path 是同一个路径，或是 path 所在的目录（以 / 结尾）。"""
    owner_path, path = _norm_path(owner_path), _norm_path(path)
    return owner_path == path or (owner_path.endswith("/") and path.startswith(owner_path))


def _transitive_deps(graph: Dict[str, List[str]], start: str) -> Set[str]:
    seen: Set[str] = set()
    stack = list(graph.get(start, []))
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(graph.get(node, []))
    return seen


def _check_ownership(
    root: Path,
    by_id: Dict[str, Tuple[Path, FrontMatter]],
    graph: Dict[str, List[str]],
    report: Report,
) -> None:
    """owns 互不重叠；appends 的文件必须有拥有者，且追加方要（传递）依赖拥有方。"""

    def paths(meta: FrontMatter, key: str) -> List[str]:
        value = meta.get(key, [])
        return list(value) if isinstance(value, list) else []

    ids = sorted(by_id)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            for pa in paths(by_id[a][1], "owns"):
                for pb in paths(by_id[b][1], "owns"):
                    if _covers(pa, pb) or _covers(pb, pa):
                        report.errors.append(
                            'owns 冲突: %s 的 "%s" 与 %s 的 "%s" 重叠' % (a, pa, b, pb)
                        )
    for wp_id in ids:
        for target in paths(by_id[wp_id][1], "appends"):
            owners = [
                other
                for other in ids
                if any(_covers(p, target) for p in paths(by_id[other][1], "owns"))
            ]
            if not owners:
                report.errors.append(
                    "%s 追加的文件 %s 没有拥有者（必须出现在某个工作包的 owns 里）" % (wp_id, target)
                )
                continue
            owner = owners[0]
            if owner != wp_id and owner not in _transitive_deps(graph, wp_id):
                report.errors.append(
                    "%s 追加 %s，必须依赖它的拥有者 %s" % (wp_id, target, owner)
                )
    # stubs：骨架工作包先建占位文件，由另一个工作包（通常是别的车道）接手并拥有
    for wp_id in ids:
        own_paths = paths(by_id[wp_id][1], "owns")
        for target in paths(by_id[wp_id][1], "stubs"):
            if any(_covers(p, target) for p in own_paths):
                report.errors.append(
                    "%s 的 stubs 里的 %s 不能同时出现在自己的 owns 里" % (wp_id, target)
                )
                continue
            takers = [
                other
                for other in ids
                if other != wp_id
                and any(_covers(p, target) for p in paths(by_id[other][1], "owns"))
            ]
            if not takers:
                report.errors.append(
                    "%s 创建的占位文件 %s 没有接手的工作包（必须出现在某个工作包的 owns 里）"
                    % (wp_id, target)
                )
            for taker in takers:
                if wp_id not in _transitive_deps(graph, taker):
                    report.errors.append(
                        "%s 接手 %s，必须依赖创建占位文件的 %s" % (taker, target, wp_id)
                    )


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------

CHECKS: List[Callable[[Path, List[Path], Report, bool], None]] = [
    check_links,
    check_doc_names,
    check_status,
    check_work_packages,
]


def run_checks(root: Path, strict: bool = False) -> Report:
    root = Path(root).resolve()
    report = Report()
    files = iter_markdown(root)
    for check in CHECKS:
        check(root, files, report, strict)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="检查文档一致性")
    parser.add_argument("--root", help="仓库根目录，默认是 scripts/ 的上一级")
    parser.add_argument("--strict", action="store_true", help='把"待重写"当作错误')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]

    report = run_checks(root, strict=args.strict)
    for note in report.notes:
        print("[说明] " + note)
    for warning in report.warnings:
        print("[警告] " + warning)
    for error in report.errors:
        print("[错误] " + error)
    print("检查完成: 错误 %d, 警告 %d" % (len(report.errors), len(report.warnings)))
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""检查 HTML 原型 design/prototype/ 是否遵守 docs/03-界面设计规范.md 的约定。仅用标准库，兼容 Python 3.9。

静态检查（CSS / JS 源码）：
  - 十六进制颜色只能出现在 tokens.css；
  - 禁止 outline: none；禁止无限循环动画；
  - CSS 类名前缀只能是 c- l- p- u- is- has-（proto.css 另允许 proto-）；
  - var(--x) 引用的变量必须已定义（tokens.css 或同一文件里）；
  - JS 里引用的契约示例（res/err/ex 的方法名与示例名）必须存在于 data/mock.js。
渲染检查（需要 node）：用 scripts/proto_render.js 渲染全部（页面，状态），逐个检查 HTML：
  - 标签闭合、id 唯一、aria-controls / aria-labelledby 指向存在的元素；
  - 按钮、链接、表单控件有可访问名称；svg 图标 aria-hidden；role="img" 的 svg 有 aria-label；
  - 内联 style 只能设置自定义属性（--x: …）；
  - 使用的类名前缀合法，且在 CSS 里有定义；
  - 禁用词（建议买入、置信度等）。

用法：python3 scripts/check_proto.py [--no-render]
退出码：全部通过为 0；有问题为 1；原型目录不存在时跳过并返回 0。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "design" / "prototype"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
ALLOWED_PREFIXES = ("c-", "l-", "p-", "u-", "is-", "has-")
# 允许没有 CSS 规则的“钩子类”：只用来给测试、脚本或设计稿标记结构，不承载样式。
# 新增的类如果没有样式又不在这里登记，就会被检查出来（防止漏写样式）。
HOOK_CLASSES = {
    "p-today", "p-today--empty", "p-holdings", "p-trading", "p-risk", "p-scan", "p-v1",   # 页面根
    "c-drawer",                                                                         # 抽屉根（样式在 l-drawer 与 c-drawer__*）
    "c-field__help",                                                                    # 帮助文字（样式沿用 c-field__meta）
    "c-tag--none",                                                                      # 默认标签就是 none 外观
}
FORBIDDEN_WORDS = ["建议买入", "建议卖出", "必涨", "抄底", "牛股", "置信度", "AI 精准预测"]
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------

def _strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _selectors(css: str) -> List[str]:
    """提取选择器部分（花括号之前的文本），跳过 @规则的参数。"""
    out: List[str] = []
    for m in re.finditer(r"([^{}]+)\{", css):
        head = m.group(1).strip()
        if head.startswith("@") or not head:
            continue
        out.append(head)
    return out


def defined_variables(css: str) -> Set[str]:
    return set(re.findall(r"(--[\w\-]+)\s*:", _strip_css_comments(css)))


def css_classes(css: str) -> Set[str]:
    found: Set[str] = set()
    for sel in _selectors(_strip_css_comments(css)):
        sel = re.sub(r"\[[^\]]*\]", "", sel)           # 去掉属性选择器
        sel = re.sub(r"\([^)]*\)", "", sel)            # 去掉 :not(...) 之类
        found.update(re.findall(r"\.([A-Za-z_][\w\-]*)", sel))
    return found


def check_css_text(css: str, name: str, defined: Optional[Set[str]] = None) -> List[str]:
    problems: List[str] = []
    clean = _strip_css_comments(css)
    is_tokens = name.endswith("tokens.css")
    is_proto = name.endswith("proto.css")
    if not is_tokens:
        # 在声明里找十六进制颜色（排除选择器与属性选择器里的 #）
        body = re.sub(r"\[[^\]]*\]", "", clean)
        for decl in re.findall(r"\{([^{}]*)\}", body):
            for m in HEX.finditer(decl):
                problems.append("%s: 出现十六进制颜色 %s（颜色只能在 tokens.css 定义）" % (name, m.group()))
    if re.search(r"outline\s*:\s*none", clean):
        problems.append("%s: 出现 outline: none（禁止取消焦点环）" % name)
    if re.search(r"animation[^;}]*infinite", clean):
        problems.append("%s: 出现无限循环动画（禁止持续循环动画）" % name)
    if "shimmer" in clean.lower():
        problems.append("%s: 出现 shimmer（骨架屏禁止闪烁动画）" % name)
    for cls in sorted(css_classes(css)):
        if cls.startswith(ALLOWED_PREFIXES):
            continue
        if cls.startswith("proto-") and is_proto:
            continue
        if cls.startswith("proto-"):
            problems.append("%s: 类名 .%s 的前缀 proto- 只允许出现在 proto.css" % (name, cls))
        else:
            problems.append("%s: 类名 .%s 不符合前缀约定（c- l- p- u- is- has-）" % (name, cls))
    if defined is not None:
        own = defined_variables(css)
        for var in sorted(set(re.findall(r"var\(\s*(--[\w\-]+)\s*(,|\))", clean))):
            if var[1] == ",":
                continue
            if var[0] not in defined and var[0] not in own:
                problems.append("%s: 引用了未定义的变量 %s" % (name, var[0]))
    return problems


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: List[Tuple[str, dict]] = []
        self.problems: List[str] = []
        self.ids: Dict[str, int] = {}
        self.refs: List[Tuple[str, str]] = []          # (属性名, 目标 id)
        self.labels_for: Set[str] = set()
        self.classes: Set[str] = set()
        self.text_stack: List[List[str]] = []          # 每个打开的元素累积的文字
        self.has_name_stack: List[bool] = []
        self.checks: List[Tuple[str, dict, str, bool]] = []   # (tag, attrs, text, has_aria_name)
        self.in_label = 0

    def handle_starttag(self, tag: str, attrs_list: list) -> None:
        attrs = {k: (v if v is not None else "") for k, v in attrs_list}
        if "id" in attrs:
            self.ids[attrs["id"]] = self.ids.get(attrs["id"], 0) + 1
        for ref in ("aria-controls", "aria-labelledby", "aria-describedby"):
            if attrs.get(ref):
                for target in attrs[ref].split():
                    self.refs.append((ref, target))
        if tag == "label" and attrs.get("for"):
            self.labels_for.add(attrs["for"])
        for cls in attrs.get("class", "").split():
            self.classes.add(cls)
        if "style" in attrs:
            for decl in [d for d in attrs["style"].split(";") if d.strip()]:
                if not decl.strip().startswith("--"):
                    self.problems.append('内联样式只允许设置自定义属性（--x），发现: style="%s"' % attrs["style"])
                    break
        if tag == "svg":
            if attrs.get("role") == "img" and not attrs.get("aria-label"):
                self.problems.append('svg role="img" 缺少 aria-label')
            elif attrs.get("role") != "img" and attrs.get("aria-hidden") != "true":
                self.problems.append("svg 图标缺少 aria-hidden=\"true\"（装饰性图标不应被读屏读出）")
        if tag in VOID:
            self._void(tag, attrs)
            return
        self.stack.append((tag, attrs))
        self.text_stack.append([])

    def _void(self, tag: str, attrs: dict) -> None:
        if tag in ("input", "select", "textarea"):
            t = attrs.get("type", "text")
            if t in ("hidden", "radio", "checkbox"):
                return
            self.checks.append((tag, attrs, "", bool(attrs.get("aria-label") or attrs.get("aria-labelledby"))))

    def handle_startendtag(self, tag: str, attrs_list: list) -> None:
        self.handle_starttag(tag, attrs_list)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.text_stack:
            for bucket in self.text_stack:
                bucket.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if not self.stack:
            self.problems.append("多余的结束标签 </%s>" % tag)
            return
        if self.stack[-1][0] != tag:
            self.problems.append("标签不匹配：期望 </%s>，遇到 </%s>" % (self.stack[-1][0], tag))
            # 尝试恢复：弹出到匹配处
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    del self.text_stack[i:]
                    break
            return
        t, attrs = self.stack.pop()
        text = "".join(self.text_stack.pop()).strip()
        if t in ("button", "a", "textarea", "select"):
            self.checks.append((t, attrs, text, bool(attrs.get("aria-label") or attrs.get("aria-labelledby"))))

    def close(self) -> None:
        super().close()
        for tag, _ in self.stack:
            self.problems.append("标签 <%s> 未闭合" % tag)


def check_html(html: str, name: str) -> List[str]:
    c = _Collector()
    c.feed(html)
    c.close()
    problems = list(c.problems)
    for i, n in c.ids.items():
        if n > 1:
            problems.append("重复的 id: %s（%d 处）" % (i, n))
    for attr, target in c.refs:
        if target not in c.ids:
            problems.append("%s 指向不存在的元素 #%s" % (attr, target))
    for tag, attrs, text, aria in c.checks:
        if tag == "button" and not (text or aria):
            problems.append("按钮没有可访问名称: <button class=\"%s\">" % attrs.get("class", ""))
        if tag == "a" and attrs.get("href") is not None and not (text or aria):
            problems.append("链接没有可访问名称: <a href=\"%s\">" % attrs.get("href"))
        if tag in ("input", "textarea", "select"):
            if not (aria or (attrs.get("id") and attrs["id"] in c.labels_for)):
                problems.append("表单控件没有标签: <%s id=\"%s\">" % (tag, attrs.get("id", "")))
    for cls in sorted(c.classes):
        if not cls.startswith(ALLOWED_PREFIXES) and not cls.startswith("proto-"):
            problems.append("类名 %s 不符合前缀约定" % cls)
    plain = re.sub(r"<[^>]+>", " ", html)
    for word in FORBIDDEN_WORDS:
        if word in plain:
            problems.append("出现禁用词“%s”" % word)
    return ["%s: %s" % (name, p) for p in problems]


def check_classes_defined(html_classes: Set[str], css_defined: Set[str]) -> List[str]:
    missing = sorted(c for c in html_classes if c not in css_defined and c not in HOOK_CLASSES and not c.startswith(("is-", "has-")))
    return ["HTML 使用了 CSS 里没有定义的类: %s" % ", ".join(missing)] if missing else []


# --------------------------------------------------------------------------
# 契约示例引用
# --------------------------------------------------------------------------

def find_example_refs(js: str) -> List[Tuple[str, str]]:
    refs = set()
    for m in re.finditer(r"\b(?:res|err|ex)\(\s*'([\w.]+)'\s*,\s*'([\w\-]+)'\s*\)", js):
        refs.add((m.group(1), m.group(2)))
    return sorted(refs)


def missing_examples(refs: List[Tuple[str, str]], available: Set[str]) -> List[str]:
    return ["%s/%s" % r for r in refs if "%s/%s" % r not in available]


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------

def _all_html_classes(pages: Dict[str, str]) -> Set[str]:
    s: Set[str] = set()
    for html in pages.values():
        c = _Collector()
        c.feed(html)
        s |= c.classes
    return s


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not PROTO.is_dir():
        print("[说明] 没有找到 design/prototype/，跳过原型检查")
        return 0
    problems: List[str] = []

    css_files = sorted((PROTO / "css").glob("*.css"))
    tokens = PROTO / "css" / "tokens.css"
    defined = defined_variables(tokens.read_text(encoding="utf-8")) if tokens.is_file() else set()
    css_defined: Set[str] = set()
    for f in css_files:
        text = f.read_text(encoding="utf-8")
        css_defined |= css_classes(text)
        problems += check_css_text(text, "css/" + f.name, defined)
    print("[CSS] 检查 %d 个文件" % len(css_files))

    mock_js = PROTO / "data" / "mock.js"
    available: Set[str] = set()
    if mock_js.is_file():
        raw = mock_js.read_text(encoding="utf-8")
        data = json.loads(raw[raw.index("window.MOCK = ") + len("window.MOCK = "):].rstrip().rstrip(";"))
        available = {"%s/%s" % (m, n) for m, v in data["examples"].items() for n in v}
    js_text = ""
    for f in sorted((PROTO / "js").glob("*.js")):
        js_text += f.read_text(encoding="utf-8") + "\n"
    miss = missing_examples(find_example_refs(js_text), available)
    problems += ["JS 引用了不存在的契约示例: %s" % m for m in miss]
    print("[JS] 引用的契约示例全部存在" if not miss else "[JS] 有 %d 个契约示例不存在" % len(miss))

    if "--no-render" not in argv:
        node = shutil.which("node")
        if not node:
            print("[说明] 没有找到 node，跳过渲染检查")
        else:
            proc = subprocess.run([node, str(ROOT / "scripts" / "proto_render.js")], capture_output=True, text=True, cwd=str(ROOT))
            if proc.returncode != 0:
                problems.append("proto_render.js 运行失败: %s" % proc.stderr.strip()[:500])
            else:
                out = json.loads(proc.stdout)
                problems += ["渲染错误: %s" % e for e in out["errors"]]
                for key, html in sorted(out["pages"].items()):
                    problems += check_html(html, key)
                problems += check_classes_defined(_all_html_classes(out["pages"]), css_defined)
                print("[渲染] 检查 %d 个页面状态" % len(out["pages"]))

    for p in problems:
        print("[错误] " + p)
    print("原型检查完成: 问题 %d" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

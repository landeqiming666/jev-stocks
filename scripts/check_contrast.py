#!/usr/bin/env python3
"""检查设计令牌的颜色对比度（WCAG 2.x）。仅用标准库，兼容 Python 3.9。

用法：
    python3 scripts/check_contrast.py                        检查 design/prototype/css/tokens.css
    python3 scripts/check_contrast.py --tokens PATH          指定令牌文件
    python3 scripts/check_contrast.py --list                 只列出每一对的比值，不判定

退出码：全部达标为 0；任一不达标为 1；令牌文件不存在时跳过并返回 0（便于 check.py 在早期阶段运行）。

新增文字色或背景色时，只需在 PAIRS 里加一行。
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# (前景令牌, 背景令牌, 最低比值, 说明)。正文与小字号要求 4.5；大字号（≥ 24px 或 ≥ 18.66px 粗体）与图形要求 3。
PAIRS: List[Tuple[str, str, float, str]] = [
    ("--ink", "--paper", 4.5, "正文主色 / 应用背景"),
    ("--ink", "--surface", 4.5, "正文主色 / 卡片"),
    ("--ink", "--surface-2", 4.5, "正文主色 / 次级块"),
    ("--ink-2", "--paper", 4.5, "次级文字 / 应用背景"),
    ("--ink-2", "--surface", 4.5, "次级文字 / 卡片"),
    ("--ink-2", "--surface-2", 4.5, "次级文字 / 次级块"),
    ("--muted", "--paper", 4.5, "辅助文字 / 应用背景"),
    ("--muted", "--surface", 4.5, "辅助文字 / 卡片"),
    ("--muted", "--surface-2", 4.5, "辅助文字 / 次级块"),
    ("--accent-ink", "--accent", 4.5, "强调色按钮文字"),
    ("--accent", "--surface", 4.5, "强调色文字 / 卡片"),
    ("--accent-text", "--accent-soft", 4.5, "强调色文字 / 强调底（--accent 本身在此底色上只有约 4.29，不得用作文字）"),
    ("--accent-text", "--surface", 4.5, "强调色文字 / 卡片"),
    ("--on-ink", "--ink", 4.5, "主按钮文字 / 墨色按钮"),
    ("--verdict-over", "--verdict-over-bg", 4.5, "推翻标签"),
    ("--verdict-weak", "--verdict-weak-bg", 4.5, "削弱标签"),
    ("--verdict-hold", "--verdict-hold-bg", 4.5, "支持标签"),
    ("--verdict-none", "--verdict-none-bg", 4.5, "无关标签"),
    ("--verdict-unsure", "--verdict-unsure-bg", 4.5, "待确认标签"),
    ("--verdict-over", "--surface", 4.5, "推翻文字 / 卡片"),
    ("--verdict-weak", "--surface", 4.5, "削弱文字 / 卡片"),
    ("--up", "--surface", 4.5, "上涨数字 / 卡片"),
    ("--down", "--surface", 4.5, "下跌数字 / 卡片"),
    ("--ok", "--surface", 4.5, "正常状态文字 / 卡片"),
    ("--warn", "--surface", 4.5, "警告状态文字 / 卡片"),
    ("--danger", "--surface", 4.5, "错误状态文字 / 卡片"),
    ("--danger", "--danger-bg", 4.5, "错误提示条"),
    ("--warn", "--warn-bg", 4.5, "警告提示条"),
    ("--info", "--info-bg", 4.5, "信息提示条"),
    ("--line-strong", "--paper", 1.3, "边框可见性（非文字，仅要求可辨）"),
    ("--focus-ring", "--paper", 3.0, "焦点环 / 背景（非文字组件 ≥ 3）"),
    ("--focus-ring", "--surface", 3.0, "焦点环 / 卡片（非文字组件 ≥ 3）"),
]

_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_ROOT_BLOCK = re.compile(r":root\s*\{(.*?)\}", re.S)
_DECL = re.compile(r"(--[\w\-]+)\s*:\s*([^;]+);")


@dataclass(frozen=True)
class Result:
    fg: str
    bg: str
    minimum: float
    note: str
    ratio: Optional[float]
    ok: bool
    detail: str


def _rgb(color: str) -> Tuple[float, float, float]:
    m = _HEX.match(color.strip())
    if not m:
        raise ValueError("不是十六进制颜色: %r" % color)
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    r, g, b = (_lin(c) for c in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def parse_tokens(css: str) -> Dict[str, str]:
    """只读取第一个 :root 块里的十六进制颜色令牌（平台与市场覆盖不参与）。"""
    m = _ROOT_BLOCK.search(css)
    if not m:
        return {}
    tokens: Dict[str, str] = {}
    for name, value in _DECL.findall(m.group(1)):
        value = value.strip()
        if _HEX.match(value):
            tokens[name] = value
    return tokens


def check(tokens_path: Path, pairs: Optional[Sequence[Tuple[str, str, float, str]]] = None) -> List[Result]:
    tokens = parse_tokens(tokens_path.read_text(encoding="utf-8"))
    results: List[Result] = []
    for fg, bg, minimum, note in (pairs if pairs is not None else PAIRS):
        missing = [t for t in (fg, bg) if t not in tokens]
        if missing:
            results.append(Result(fg, bg, minimum, note, None, False, "缺少令牌: " + ", ".join(missing)))
            continue
        ratio = contrast(tokens[fg], tokens[bg])
        results.append(Result(fg, bg, minimum, note, ratio, ratio >= minimum,
                              "%s on %s" % (tokens[fg], tokens[bg])))
    return results


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="检查设计令牌对比度")
    default = Path(__file__).resolve().parents[1] / "design" / "prototype" / "css" / "tokens.css"
    parser.add_argument("--tokens", default=str(default))
    parser.add_argument("--list", action="store_true", help="只列出比值，不判定")
    parser.add_argument("--only-demo-pair", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    path = Path(args.tokens)
    if not path.is_file():
        print("[说明] 没有找到令牌文件 %s，跳过对比度检查" % path)
        return 0
    pairs = [("--muted", "--paper", 4.5, "demo")] if args.only_demo_pair else None
    results = check(path, pairs)
    failed = 0
    for r in results:
        ratio = "  n/a" if r.ratio is None else "%5.2f" % r.ratio
        status = "OK  " if r.ok else "FAIL"
        if not r.ok:
            failed += 1
        print("%s %s:1 (需要 %.1f) %s / %s  %s  %s" % (status, ratio, r.minimum, r.fg, r.bg, r.note, r.detail))
    print("对比度检查完成: 共 %d 对, 不达标 %d" % (len(results), failed))
    return 0 if args.list or failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

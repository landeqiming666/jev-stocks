#!/usr/bin/env python3
"""生成 1024x1024 纯色 RGBA PNG 占位图标。仅用标准库，兼容 Python 3.9。

用法：python3 scripts/make_placeholder_icon.py --out /tmp/sentinel-icon.png
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path
from typing import List, Optional, Tuple


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def make_png(size: int, color: Tuple[int, int, int, int]) -> bytes:
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    pixel = bytes(color)
    row = b"\x00" + pixel * size
    raw = row * size
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="生成占位图标")
    parser.add_argument("--out", required=True, help="输出 PNG 路径")
    parser.add_argument("--size", type=int, default=1024, help="边长，默认 1024")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(make_png(args.size, (0x1A, 0x1C, 0x20, 0xFF)))
    print("已生成 %s (%dx%d)" % (out, args.size, args.size))
    return 0


if __name__ == "__main__":
    sys.exit(main())

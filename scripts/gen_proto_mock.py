#!/usr/bin/env python3
"""Generate the existing prototype mock bytes solely from contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__:
    from .check_contracts import ROOT, ContractError, check_contracts
else:
    from check_contracts import ROOT, ContractError, check_contracts


HEADER = "/* 由 contracts/ 的 examples 生成（scripts/gen_proto_mock.py）。请勿手改。纯 JSON，供脚本读回。 */\n"


def generate(contracts):
    index, methods, notifications = check_contracts(contracts)
    examples = {
        name: {
            e["name"]: {k: v for k, v in e.items() if k != "name"}
            for e in methods[name]["examples"]
        }
        for name in index["methods"]
    }
    payload = {
        "examples": examples,
        "notifications": {
            n: notifications[n]["example"] for n in index["notifications"]
        },
    }
    return (
        HEADER
        + "window.MOCK = "
        + json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False)
        + ";\n"
    ).encode("utf-8")


def first_difference(expected, actual):
    wanted, found = expected.splitlines(keepends=True), actual.splitlines(keepends=True)
    for i in range(max(len(wanted), len(found))):
        left = wanted[i] if i < len(wanted) else b"<EOF>"
        right = found[i] if i < len(found) else b"<EOF>"
        if left != right:
            return "mock.js differs at line %d: expected %r, found %r" % (
                i + 1,
                left[:160],
                right[:160],
            )
    return "mock.js differs"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate/check prototype mock.js")
    parser.add_argument("--contracts", type=Path, default=ROOT / "contracts")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "design/prototype/data/mock.js"
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    contracts, out = args.contracts.resolve(), args.out.resolve()
    if out == contracts or contracts in out.parents:
        print("output path must not be inside contracts", file=sys.stderr)
        return 2
    try:
        expected = generate(contracts)
        if args.check:
            if not out.is_file():
                print("mock.js differs at line 1: output file missing")
                return 1
            actual = out.read_bytes()
            if expected != actual:
                print(first_difference(expected, actual))
                return 1
            print("mock.js is up to date")
            return 0
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(expected)
    except (ContractError, OSError, RecursionError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("wrote " + str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

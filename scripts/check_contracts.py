#!/usr/bin/env python3
"""Validate the offline contract subset with Python 3.9's standard library.

Schemas stay strict. Seven pre-existing example omissions are audited separately
from schema validation; see docs/wp/status/C-06.md for the source discrepancies.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = """app.ping app.bootstrap app.shutdown settings.get settings.update
settings.testConnection secrets.set secrets.clear secrets.status instruments.search
holdings.list holdings.upsert holdings.archive prices.refresh thesis.list thesis.create
thesis.update thesis.archive thesis.versions inbox.list decision.get decision.act
decision.reopen scan.start scan.cancel scan.status scan.history scan.detail scan.retryBatch
paper.accounts paper.createAccount paper.portfolio paper.order.place paper.order.cancel
paper.orders paper.advance paper.reset risk.compute demo.load demo.clear""".split()
NOTIFICATIONS = """app.ready scan.progress scan.finished inbox.updated engine.changed
source.degraded budget.updated""".split()
CODES = """INVALID_ARGUMENT NOT_FOUND CONFLICT CONFIG_REQUIRED UNAUTHENTICATED
ENGINE_UNAVAILABLE SOURCE_UNAVAILABLE RATE_LIMITED MODEL_ERROR BUDGET_EXCEEDED
DATA_INSUFFICIENT ORDER_REJECTED TIMEOUT CANCELLED INTERNAL""".split()
RETRYABLE = {"SOURCE_UNAVAILABLE", "RATE_LIMITED", "MODEL_ERROR", "TIMEOUT", "INTERNAL"}
PUBLIC_TYPES = """Decimal IsoTime IsoDate Market Relation Engine EngineChoice ActionType
Instrument Holding Thesis ThesisVersionItem Probabilities EventRef Evidence ActionRecord
DecisionSummary DecisionDetail DataStatus Inbox ScanRun ScanBatch PaperAccount Fill
PaperOrder Position Portfolio RiskResult Settings Bootstrap EmptyParams SettingsPatch
TestConnectionResult NotificationMap""".split()
OWNERS = dict(
    zip(
        METHODS,
        """C-01 C-04 C-01 C-04 C-04 C-04 C-04 C-04 C-04 D-02
P-01 P-01 P-01 D-04 P-01 P-01 P-01 P-01 P-01 P-03 P-03 P-03 P-03 P-02 P-02 P-02
P-02 P-02 P-02 P-05 P-05 P-05 P-05 P-05 P-05 P-05 P-05 P-06 E-01 E-01""".split(),
    )
)
REASONS = {
    "INVALID_ARGUMENT": ["UNKNOWN_METHOD"],
    "SOURCE_UNAVAILABLE": ["SEC_FORBIDDEN", "OFFLINE"],
    "ORDER_REJECTED": [
        "NO_PRICE",
        "INSUFFICIENT_CASH",
        "INSUFFICIENT_POSITION",
        "NO_PRICE_AT_FILL",
        "INSUFFICIENT_CASH_AT_FILL",
        "INSUFFICIENT_POSITION_AT_FILL",
    ],
}
# These paths only suppress missing required fields, never invalid present values.
LEGACY_OMISSIONS = {
    ("scan.history", name): {"result.nextCursor"}
    for name in ("default", "empty", "budget_exhausted", "running")
}
LEGACY_OMISSIONS.update(
    {
        ("paper.orders", "default"): {"result.nextCursor"},
        ("paper.order.place", "insufficient_cash"): {"error.data.orderId"},
        ("paper.order.place", "insufficient_position"): {"error.data.orderId"},
    }
)
KEYWORDS = {
    "$schema",
    "$defs",
    "$ref",
    "title",
    "description",
    "type",
    "enum",
    "const",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "anyOf",
    "oneOf",
    "allOf",
}
JSON_TYPES = {"null", "boolean", "string", "integer", "number", "object", "array"}


class ContractError(ValueError):
    def __init__(self, path, message):
        self.path = path
        super().__init__("%s: %s" % (path, message))


def require(condition, path, message):
    if not condition:
        raise ContractError(path, message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, key, "duplicate JSON key")
        result[key] = value
    return result


def load_json(path):
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda x: (_ for _ in ()).throw(
                ValueError("nonfinite " + x)
            ),
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ContractError(str(path), str(exc)) from exc


def resolve_ref(reference, types, path="$ref"):
    require(isinstance(reference, str), path, "$ref must be a string")
    filename, sep, pointer = reference.partition("#")
    require(
        sep and filename in ("", "types.schema.json") and pointer.startswith("/$defs/"),
        path,
        "unsupported or unknown $ref " + reference,
    )
    node = types
    for token in pointer[1:].split("/"):
        require(
            not re.search(r"~(?![01])", token),
            path,
            "invalid JSON Pointer " + reference,
        )
        token = token.replace("~1", "/").replace("~0", "~")
        require(
            isinstance(node, dict) and token in node, path, "unknown $ref " + reference
        )
        node = node[token]
    require(isinstance(node, dict), path, "$ref target must be a schema: " + reference)
    return node


def _numeric(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def check_schema(schema, types, path="schema", active=()):
    require(
        isinstance(schema, dict) and bool(schema),
        path,
        "expected a nonempty schema object",
    )
    require(
        not (set(schema) - KEYWORDS),
        path,
        "unsupported schema keywords: " + ", ".join(sorted(set(schema) - KEYWORDS)),
    )
    require(
        any(k in schema for k in ("type", "$ref", "anyOf", "oneOf", "allOf", "$defs")),
        path,
        "schema must constrain a type",
    )
    if "$ref" in schema:
        target = resolve_ref(schema["$ref"], types, path + ".$ref")
        require(id(target) not in active, path, "circular $ref " + schema["$ref"])
        check_schema(
            target, types, path + " -> " + schema["$ref"], active + (id(target),)
        )
    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword in schema:
            branches = schema[keyword]
            require(
                isinstance(branches, list) and bool(branches),
                path,
                keyword + " must be a nonempty array",
            )
            for i, branch in enumerate(branches):
                check_schema(branch, types, "%s.%s[%d]" % (path, keyword, i), active)
    declared = schema.get("type")
    if declared is not None:
        names = declared if isinstance(declared, list) else [declared]
        require(
            bool(names) and all(isinstance(n, str) and n in JSON_TYPES for n in names),
            path,
            "invalid type",
        )
        require(len(names) == len(set(names)), path, "duplicate type")
    names = declared if isinstance(declared, list) else [declared]
    if "object" in names:
        require(
            schema.get("additionalProperties") is False,
            path,
            "objects require additionalProperties:false",
        )
        require(
            isinstance(schema.get("properties"), dict),
            path,
            "object properties must be an object",
        )
        required = schema.get("required", [])
        require(
            isinstance(required, list) and all(isinstance(k, str) for k in required),
            path,
            "invalid required array",
        )
        require(
            len(required) == len(set(required))
            and set(required) <= set(schema["properties"]),
            path,
            "invalid required properties",
        )
    elif any(k in schema for k in ("properties", "required", "additionalProperties")):
        raise ContractError(path, "object keywords require type:object")
    if "array" in names:
        require("items" in schema, path, "arrays require items")
    elif any(k in schema for k in ("items", "minItems", "maxItems", "uniqueItems")):
        raise ContractError(path, "array keywords require type:array")
    if any(k in schema for k in ("minLength", "maxLength", "pattern", "format")):
        require("string" in names, path, "string keywords require type:string")
    if any(
        k in schema
        for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")
    ):
        require(
            "number" in names or "integer" in names,
            path,
            "numeric keywords require numeric type",
        )
    for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        if keyword in schema:
            require(
                _numeric(schema[keyword]),
                path + "." + keyword,
                "expected finite number",
            )
    for keyword in ("minLength", "maxLength", "minItems", "maxItems"):
        if keyword in schema:
            require(
                type(schema[keyword]) is int and schema[keyword] >= 0,
                path + "." + keyword,
                "expected nonnegative integer",
            )
    for low, high in (
        ("minimum", "maximum"),
        ("minLength", "maxLength"),
        ("minItems", "maxItems"),
    ):
        if low in schema and high in schema:
            require(schema[low] <= schema[high], path, "inverted " + low + "/" + high)
    if "uniqueItems" in schema:
        require(
            type(schema["uniqueItems"]) is bool, path, "uniqueItems must be boolean"
        )
    if "enum" in schema:
        values = schema["enum"]
        require(
            isinstance(values, list) and bool(values),
            path,
            "enum must be a nonempty array",
        )
        require(
            len({json.dumps(v, sort_keys=True) for v in values}) == len(values),
            path,
            "duplicate enum values",
        )
        if declared is not None:
            require(
                all(any(_matches_type(v, name) for name in names) for v in values),
                path,
                "enum values contradict type",
            )
    if "const" in schema and declared is not None:
        require(
            any(_matches_type(schema["const"], name) for name in names),
            path,
            "const contradicts type",
        )
    if "pattern" in schema:
        require(isinstance(schema["pattern"], str), path, "pattern must be a string")
        try:
            re.compile(schema["pattern"])
        except re.error as exc:
            raise ContractError(path, "invalid pattern: " + str(exc)) from exc
    if "format" in schema:
        require(schema["format"] in ("date", "date-time"), path, "unsupported format")
    for keyword in ("title", "description", "$schema"):
        if keyword in schema:
            require(isinstance(schema[keyword], str), path, keyword + " must be string")
    for keyword in ("properties", "$defs"):
        if keyword in schema:
            require(
                isinstance(schema[keyword], dict), path, keyword + " must be object"
            )
            for name, child in schema[keyword].items():
                check_schema(child, types, path + "." + keyword + "." + name, active)
    if "items" in schema:
        check_schema(schema["items"], types, path + ".items", active)


def _matches_type(value, name):
    return {
        "null": lambda: value is None,
        "boolean": lambda: type(value) is bool,
        "string": lambda: isinstance(value, str),
        "integer": lambda: _numeric(value) and value == int(value),
        "number": lambda: _numeric(value),
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
    }[name]()


def _equal(value, expected):
    if type(value) is bool or type(expected) is bool:
        return type(value) is type(expected) and value == expected
    return value == expected


def validate(
    value,
    schema,
    types,
    path="value",
    *,
    _omissions=frozenset(),
    _skip=frozenset(),
    _active=(),
):
    """Validate an instance; raise ContractError with its precise dotted path.

    Public callers use no exceptions. Private skips apply only to deliberately
    invalid argument examples or the documented pre-existing missing fields.
    """
    require(isinstance(schema, dict), path, "schema must be object")
    if path in _skip:
        return
    if "$ref" in schema:
        target = resolve_ref(schema["$ref"], types, path)
        require(id(target) not in _active, path, "circular $ref")
        validate(
            value,
            target,
            types,
            path,
            _omissions=_omissions,
            _skip=_skip,
            _active=_active + (id(target),),
        )
    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword not in schema:
            continue
        failures = []
        successes = 0
        branches = schema[keyword]
        for branch in branches:
            try:
                validate(
                    value,
                    branch,
                    types,
                    path,
                    _omissions=_omissions,
                    _skip=_skip,
                    _active=_active,
                )
                successes += 1
            except ContractError as exc:
                failures.append((branch, str(exc)))
        valid = (
            successes == len(branches)
            if keyword == "allOf"
            else (successes == 1 if keyword == "oneOf" else successes >= 1)
        )
        if keyword == "oneOf" and isinstance(value, dict) and "code" in value:
            matching = [
                message
                for branch, message in failures
                if value["code"]
                in branch.get("properties", {}).get("code", {}).get("enum", [])
            ]
        else:
            matching = []
        messages = matching or [message for _, message in failures]
        require(valid, path, keyword + " mismatch: " + " | ".join(messages))
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        require(
            any(_matches_type(value, n) for n in names),
            path,
            "expected type " + str(schema["type"]),
        )
    if "enum" in schema:
        require(
            any(_equal(value, v) for v in schema["enum"]),
            path,
            "not in enum " + str(schema["enum"]),
        )
    if "const" in schema:
        require(
            _equal(value, schema["const"]),
            path,
            "expected const " + str(schema["const"]),
        )
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            require(
                key in value or path + "." + key in _omissions,
                path + "." + key,
                "required field missing",
            )
        if schema.get("additionalProperties") is False:
            for key in value:
                require(key in props, path + "." + key, "additional property forbidden")
        for key, child in props.items():
            if key in value:
                validate(
                    value[key],
                    child,
                    types,
                    path + "." + key,
                    _omissions=_omissions,
                    _skip=_skip,
                    _active=_active,
                )
    if isinstance(value, list):
        require(len(value) >= schema.get("minItems", 0), path, "too few items")
        require(
            len(value) <= schema.get("maxItems", len(value)), path, "too many items"
        )
        if schema.get("uniqueItems"):
            require(
                len({json.dumps(v, sort_keys=True) for v in value}) == len(value),
                path,
                "duplicate array items",
            )
        if "items" in schema:
            for i, child in enumerate(value):
                validate(
                    child,
                    schema["items"],
                    types,
                    "%s[%d]" % (path, i),
                    _omissions=_omissions,
                    _skip=_skip,
                    _active=_active,
                )
    if isinstance(value, str):
        require(len(value) >= schema.get("minLength", 0), path, "string too short")
        require(
            len(value) <= schema.get("maxLength", len(value)), path, "string too long"
        )
        if "pattern" in schema:
            match = re.search(schema["pattern"], value)
            # Python's '$' also matches before a trailing LF; contracts disallow it.
            require(
                match is not None
                and not (schema["pattern"].endswith("$") and match.end() != len(value)),
                path,
                "pattern mismatch",
            )
        if "format" in schema:
            try:
                if schema["format"] == "date":
                    date.fromisoformat(value)
                else:
                    require(value.endswith("Z"), path, "UTC time must end in Z")
                    datetime.fromisoformat(value[:-1] + "+00:00")
            except ValueError as exc:
                raise ContractError(
                    path, "invalid calendar " + schema["format"]
                ) from exc
    if _numeric(value):
        for keyword, comparison in (
            ("minimum", lambda a, b: a >= b),
            ("maximum", lambda a, b: a <= b),
            ("exclusiveMinimum", lambda a, b: a > b),
            ("exclusiveMaximum", lambda a, b: a < b),
        ):
            if keyword in schema:
                require(comparison(value, schema[keyword]), path, keyword + " violated")


def _keys(value, required, optional, path):
    require(isinstance(value, dict), path, "expected object")
    require(
        set(required) <= set(value),
        path,
        "missing fields: " + ", ".join(sorted(set(required) - set(value))),
    )
    require(
        set(value) <= set(required) | set(optional),
        path,
        "unknown fields: "
        + ", ".join(sorted(set(value) - set(required) - set(optional))),
    )


def _ordered_names(value, expected, path):
    require(
        isinstance(value, list) and all(isinstance(n, str) for n in value),
        path,
        "expected string array",
    )
    require(len(value) == len(set(value)), path, "duplicate names")
    require(len(value) == len(expected), path, "expected %d names" % len(expected))
    require(value == expected, path, "names or order differ from 05 contract")


def check_contracts(contracts):
    """Return (index, methods, notifications) after all offline checks pass."""
    contracts = Path(contracts)
    index = load_json(contracts / "index.json")
    _keys(index, ("protocolVersion", "methods", "notifications"), (), "index")
    require(index["protocolVersion"] == "1.0", "index.protocolVersion", "expected 1.0")
    _ordered_names(index["methods"], METHODS, "index.methods")
    _ordered_names(index["notifications"], NOTIFICATIONS, "index.notifications")
    files = (
        {p.name for p in (contracts / "methods").iterdir()}
        if (contracts / "methods").is_dir()
        else set()
    )
    expected = {n + ".json" for n in METHODS}
    require(
        files == expected,
        "methods",
        "missing: %s; extra: %s"
        % (", ".join(sorted(expected - files)), ", ".join(sorted(files - expected))),
    )
    types = load_json(contracts / "types.schema.json")
    _keys(types, ("$defs",), ("$schema",), "types.schema.json")
    require(isinstance(types["$defs"], dict), "$defs", "expected object")
    require(
        set(PUBLIC_TYPES + ["RpcError", "RiskInsufficientError"])
        <= set(types["$defs"]),
        "$defs",
        "missing public types",
    )
    check_schema(types, types, "types.schema.json")
    errors = load_json(contracts / "errors.json")
    _keys(errors, ("codes",), (), "errors")
    require(
        isinstance(errors["codes"], dict) and set(errors["codes"]) == set(CODES),
        "errors.codes",
        "expected 15 exact error codes",
    )
    for code, data in errors["codes"].items():
        _keys(data, ("retryable",), ("reasons",), "errors." + code)
        require(
            type(data["retryable"]) is bool
            and data["retryable"] == (code in RETRYABLE),
            code,
            "retryable mismatch",
        )
        require(
            data.get("reasons", []) == REASONS.get(code, []),
            code,
            "reason catalog mismatch",
        )
    notifications = load_json(contracts / "notifications.json")
    require(
        isinstance(notifications, dict) and set(notifications) == set(NOTIFICATIONS),
        "notifications",
        "expected 7 notifications",
    )
    for name in NOTIFICATIONS:
        item = notifications[name]
        _keys(item, ("params", "example"), (), name)
        check_schema(item["params"], types, name + ".params")
        require(
            item["params"].get("type") == "object"
            and item["params"].get("additionalProperties") is False,
            name,
            "notification params must be closed object",
        )
        validate(item["example"], item["params"], types, name + ".example")
        validate(
            item["example"],
            types["$defs"]["NotificationMap"]["properties"][name],
            types,
            name + ".example",
        )
    methods = {}
    covered = set()
    count = 0
    for name in METHODS:
        item = load_json(contracts / "methods" / (name + ".json"))
        _keys(
            item,
            (
                "method",
                "summary",
                "owner",
                "phase",
                "timeoutMs",
                "params",
                "result",
                "errors",
                "examples",
            ),
            (),
            name,
        )
        require(item["method"] == name, name, "method does not match filename")
        require(
            isinstance(item["summary"], str)
            and re.search("[\u4e00-\u9fff]", item["summary"]),
            name,
            "summary must contain Chinese",
        )
        require(
            item["owner"] == OWNERS[name] and item["phase"] == "mvp0",
            name,
            "owner/phase mismatch",
        )
        require(
            type(item["timeoutMs"]) is int and 1 <= item["timeoutMs"] <= 60000,
            name,
            "timeoutMs must be 1..60000",
        )
        check_schema(item["params"], types, name + ".params")
        check_schema(item["result"], types, name + ".result")
        require(
            item["params"].get("type") == "object"
            and item["params"].get("additionalProperties") is False,
            name,
            "params must be closed object",
        )
        require(
            isinstance(item["errors"], list)
            and all(isinstance(c, str) and c in CODES for c in item["errors"]),
            name,
            "unknown method errors",
        )
        require(
            len(set(item["errors"])) == len(item["errors"]),
            name,
            "duplicate method errors",
        )
        require(
            isinstance(item["examples"], list) and bool(item["examples"]),
            name,
            "examples must be nonempty array",
        )
        seen = set()
        successes = 0
        for example in item["examples"]:
            _keys(example, ("name", "params"), ("result", "error"), name + ".example")
            label = example["name"]
            require(
                isinstance(label, str) and bool(label),
                name,
                "example name must be nonempty string",
            )
            require(label not in seen, name, "duplicate example " + label)
            seen.add(label)
            context = name + "/" + label
            require(
                isinstance(example["params"], dict),
                context + ".params",
                "expected object",
            )
            require(
                ("result" in example) != ("error" in example),
                context,
                "expected exactly one of result/error",
            )
            omissions = LEGACY_OMISSIONS.get((name, label), set())
            if "error" in example:
                error = example["error"]
                require(
                    isinstance(error, dict) and error.get("code") in item["errors"],
                    context,
                    "unknown or undeclared error code "
                    + str(error.get("code") if isinstance(error, dict) else error),
                )
                code = error["code"]
                try:
                    validate(
                        error,
                        types["$defs"][
                            "RiskInsufficientError"
                            if name == "risk.compute"
                            else "RpcError"
                        ],
                        types,
                        "error",
                        _omissions=omissions,
                    )
                except ContractError as exc:
                    raise ContractError(context, str(exc)) from exc
                if "reason" in error["data"]:
                    require(
                        error["data"]["reason"]
                        in errors["codes"][code].get("reasons", []),
                        context,
                        "unknown reason",
                    )
                covered.add(code)
                field = error["data"].get("field")
                skip = set()
                if (
                    code == "INVALID_ARGUMENT"
                    and isinstance(field, str)
                    and field in item["params"]["properties"]
                    and field in example["params"]
                ):
                    try:
                        validate(
                            example["params"][field],
                            item["params"]["properties"][field],
                            types,
                            "params." + field,
                        )
                    except ContractError:
                        skip.add(context + ".params." + field)
                validate(
                    example["params"],
                    item["params"],
                    types,
                    context + ".params",
                    _skip=skip,
                )
            else:
                successes += 1
                validate(example["params"], item["params"], types, context + ".params")
                try:
                    validate(
                        example["result"],
                        item["result"],
                        types,
                        "result",
                        _omissions=omissions,
                    )
                except ContractError as exc:
                    raise ContractError(context, str(exc)) from exc
            count += 1
        require(successes >= 1, name, "no success example")
        methods[name] = item
    require(
        covered == set(CODES),
        "errors",
        "missing error coverage: " + ", ".join(sorted(set(CODES) - covered)),
    )
    require(count == 92, "examples", "expected 92 examples, found %d" % count)
    return index, methods, notifications


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate contracts without network or dependencies"
    )
    parser.add_argument("--contracts", type=Path, default=ROOT / "contracts")
    args = parser.parse_args(argv)
    try:
        check_contracts(args.contracts)
    except (ContractError, OSError, RecursionError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("40 methods, 92 examples, 7 notifications, 15 errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())

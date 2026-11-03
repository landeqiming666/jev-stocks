"""Contract regressions use only fictional examples and temporary copies."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def author_payload():
    with tempfile.TemporaryDirectory(prefix="author-fictional-") as tmp:
        for name in ("data.py", "data_more.py", "examples.py"):
            shutil.copyfile(ROOT / ".kiro/notes/author" / name, Path(tmp) / name)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "import json, sys; sys.path.insert(0, sys.argv[1]); "
                "import examples; print(json.dumps({'examples': examples.EX, "
                "'notifications': examples.NOTIFICATIONS}, ensure_ascii=False))",
                tmp,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(result.stdout)


def decisions(value):
    if isinstance(value, dict):
        if "decisionId" in value and "probabilities" in value:
            yield value
        for child in value.values():
            yield from decisions(child)
    elif isinstance(value, list):
        for child in value:
            yield from decisions(child)


def normalization_cases(kind):
    pad = " \t\r\n\u0085\u001c\u00a0\u3000"
    if kind == "email":

        def email(n):
            return "a" * 64 + "@" + "b" * (n - 69) + ".com"

        values = [
            None,
            "",
            pad,
            "\n" * 1000,
            "name@example.com",
            pad + "name@example.com" + pad,
            pad + email(120) + pad,
            pad + email(121) + pad,
            "😀" * 108 + "@example.com",
            "😀" * 109 + "@example.com",
            "a b@example.com",
            "a@b",
            "a@b\n.c",
            "a@b.c\nx",
            12,
        ]
    elif kind == "key":
        values = [
            "",
            pad,
            "fake-key",
            pad + "fake-key" + pad,
            pad + "k" * 512 + pad,
            pad + "k" * 513 + pad,
            pad + "😀" * 512 + pad,
            pad + "😀" * 513 + pad,
            "fake key",
            "fake\nkey",
            "fake\u001ckey",
            "fake\u0085key",
            "fake\u00a0key",
            "\ufeff" + "k" * 512,
            "\u200b" + "k" * 512,
            None,
            12,
        ]
    elif kind == "statement":
        values = [
            "",
            pad,
            "\n" * 1000,
            " 😀\n ",
            pad + "字😀" * 250 + pad,
            pad + "字😀" * 250 + "测" + pad,
            pad + "😀" * 500 + pad,
            pad + "😀" * 501 + pad,
            "😀\n" * 249 + "字😀",
            "😀\n" * 250 + "字",
            "\ufeff",
            "\u200b",
            "字" * 499 + "\ufeff字",
            None,
            12,
        ]
    else:
        limit = 200 if kind == "note" else 300
        values = [
            None,
            "",
            pad,
            "\n" * 1000,
            " 😀\n ",
            pad + "字😀" * (limit // 2) + pad,
            pad + "字😀" * (limit // 2) + "测" + pad,
            pad + "😀" * limit + pad,
            pad + "😀" * (limit + 1) + pad,
            "😀\n" * (limit // 2 - 1) + "字😀",
            "😀\n" * (limit // 2) + "字",
            "\ufeff",
            "\u200b",
            12,
        ]
    base = {
        "email": "a@example.com",
        "key": "k" * 512,
        "statement": "😀" * 500,
        "kill": "😀" * 300,
        "note": "😀" * 200,
    }[kind]
    for cp in range(0x110000):
        if chr(cp).isspace():
            whitespace = chr(cp)
            values.append(whitespace + base + whitespace)
            if kind in ("email", "key"):
                values.append("a" + whitespace + base)
            if kind in ("email", "kill", "statement", "note"):
                values.append(whitespace * 600)
    return values


def normalized_valid(kind, value):
    if value is None:
        return kind in ("email", "kill", "note")
    if not isinstance(value, str):
        return False
    text = value.strip()
    if kind == "email":
        if not text:
            return True
        if not text.isascii() or len(text) > 120 or text.count("@") != 1:
            return False
        local, domain = text.split("@")
        labels = domain.split(".")
        return bool(
            1 <= len(local) <= 64
            and re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
            and not local.startswith(".")
            and not local.endswith(".")
            and ".." not in local
            and len(labels) >= 2
            and all(
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in labels
            )
            and re.fullmatch(r"[A-Za-z]{2,63}", labels[-1])
        )
    if kind == "key":
        return 1 <= len(text) <= 512 and re.search(r"\s", text) is None
    if kind == "statement":
        return 1 <= len(text) <= 500
    return len(text) <= (200 if kind == "note" else 300)


class ContractTests(unittest.TestCase):
    def checker(self):
        from scripts import check_contracts

        return check_contracts

    def run_script(self, name, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *map(str, args)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def mutate(self, filename, change):
        with tempfile.TemporaryDirectory(prefix="contracts-含 空格-") as tmp:
            target = Path(tmp) / "contracts"
            shutil.copytree(CONTRACTS, target)
            path = target / filename
            value = read(path)
            change(value)
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            return self.run_script("check_contracts.py", "--contracts", target)

    def rejected(self, filename, change, message):
        result = self.mutate(filename, change)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stdout + result.stderr)

    def test_index_lists_exactly_40_methods_and_7_notifications(self):
        index = read(CONTRACTS / "index.json")
        self.assertEqual(index["protocolVersion"], "1.0")
        self.assertEqual(len(set(index["methods"])), 40)
        self.assertEqual(len(set(index["notifications"])), 7)
        doc = (ROOT / "docs/05-接口契约.md").read_text(encoding="utf-8")
        section = doc.split("### 5.10 方法总表（40）", 1)[1].split("## 6.", 1)[0]
        self.assertEqual(index["methods"], re.findall(r"`([a-zA-Z.]+)`", section))

    def test_every_method_file_matches_its_method_field(self):
        methods = read(CONTRACTS / "index.json")["methods"]
        self.assertEqual(
            {p.stem for p in (CONTRACTS / "methods").glob("*.json")}, set(methods)
        )
        for method in methods:
            self.assertEqual(
                read(CONTRACTS / "methods" / (method + ".json"))["method"], method
            )

    def test_every_method_has_one_success_example(self):
        paths = list((CONTRACTS / "methods").glob("*.json"))
        self.assertEqual(len(paths), 40)
        for path in paths:
            self.assertTrue(
                any("result" in e for e in read(path)["examples"]), path.name
            )

    def test_all_15_error_codes_are_exercised(self):
        codes = {
            e["error"]["code"]
            for p in (CONTRACTS / "methods").glob("*.json")
            for e in read(p)["examples"]
            if "error" in e
        }
        self.assertEqual(codes, set(read(CONTRACTS / "errors.json")["codes"]))
        self.assertEqual(len(codes), 15)

    def test_notifications_have_schema_and_example(self):
        notifications = read(CONTRACTS / "notifications.json")
        self.assertEqual(len(notifications), 7)
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        for name, item in notifications.items():
            checker.validate(item["example"], item["params"], types, name)

    def test_generator_matches_existing_mock_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "mock.js"
            result = self.run_script(
                "gen_proto_mock.py", "--contracts", CONTRACTS, "--out", out
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                out.read_bytes(), (ROOT / "design/prototype/data/mock.js").read_bytes()
            )

    def test_check_mode_detects_modified_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "mock.js"
            out.write_bytes(
                (ROOT / "design/prototype/data/mock.js").read_bytes()[:-1] + b"!"
            )
            before = out.read_bytes()
            result = self.run_script(
                "gen_proto_mock.py", "--contracts", CONTRACTS, "--out", out, "--check"
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("line", result.stdout + result.stderr)
            self.assertEqual(out.read_bytes(), before)

    def test_additional_properties_false_is_enforced(self):
        self.rejected(
            "methods/app.ping.json",
            lambda m: m["examples"][0]["params"].update(x=1),
            "params.x",
        )

    def test_unknown_ref_is_rejected(self):
        self.rejected(
            "methods/app.ping.json",
            lambda m: m.update(result={"$ref": "#/$defs/Nope"}),
            "#/$defs/Nope",
        )

    def test_error_example_requires_retryable(self):
        self.rejected(
            "methods/scan.start.json",
            lambda m: m["examples"][1]["error"]["data"].pop("retryable"),
            "retryable",
        )

    def test_prototype_state_examples_all_exist(self):
        doc = (ROOT / "docs/03-界面设计规范.md").read_text(encoding="utf-8")
        section = doc.split("## 6. 页面状态总表", 1)[1].split("## 7.", 1)[0]
        names = {
            p.stem: {e["name"] for e in read(p)["examples"]}
            for p in (CONTRACTS / "methods").glob("*.json")
        }
        for method, name in re.findall(r"`([a-zA-Z.]+)/([a-z_]+)`", section):
            self.assertIn(name, names[method], method)
        for name in (
            "overturn",
            "weaken",
            "uncertain",
            "title_only",
            "processed",
            "not_found",
        ):
            self.assertIn(name, names["decision.get"])

    def test_real_contracts_validate(self):
        result = self.run_script("check_contracts.py", "--contracts", CONTRACTS)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "40 methods, 92 examples, 7 notifications, 15 errors", result.stdout
        )

    def test_public_types_reject_invalid_fields(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        mock = (ROOT / "design/prototype/data/mock.js").read_text(encoding="utf-8")
        examples = json.loads(mock.split("window.MOCK = ", 1)[1][:-2])["examples"]
        cases = [
            ("Holding", "holdings.upsert", "ok", "quantity", 120),
            ("Holding", "holdings.upsert", "ok", "status", "unknown"),
            ("Thesis", "thesis.create", "ok", "version", True),
            ("Thesis", "thesis.create", "ok", "statement", " " * 3),
            ("PaperOrder", "paper.order.place", "pending", "side", "short"),
            ("PaperOrder", "paper.order.place", "pending", "quantity", 1.5),
            ("Settings", "settings.get", "configured", "dailyTokenBudget", 9999),
            ("Settings", "settings.get", "configured", "firstScanLookbackDays", 31),
            ("RiskResult", "risk.compute", "ok", "maxDrawdown", -0.1),
        ]
        for type_name, method, name, field, bad in cases:
            with self.subTest(type=type_name, field=field, bad=bad):
                value = copy.deepcopy(examples[method][name]["result"])
                value[field] = bad
                with self.assertRaises(checker.ContractError):
                    checker.validate(
                        value, {"$ref": "types.schema.json#/$defs/" + type_name}, types
                    )

    def test_scalar_patterns_and_bounds(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        cases = {
            "Decimal": [123, "1e3", "NaN", "1.2\n"],
            "IsoDate": ["2026-13-01", "2026-02-30", "2026-1-01"],
            "IsoTime": [
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T24:00:00Z",
                "2026-02-30T00:00:00Z",
            ],
            "Probabilities": [
                {
                    "relevant": 1.01,
                    "against": 0.5,
                    "contradicts": 0.5,
                    "killMet": None,
                    "supports": 0.5,
                }
            ],
        }
        for name, values in cases.items():
            for value in values:
                with self.subTest(type=name, value=value):
                    with self.assertRaises(checker.ContractError):
                        checker.validate(
                            value, {"$ref": "types.schema.json#/$defs/" + name}, types
                        )

    def test_optional_parameters_have_real_constraints(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        cases = [
            ("scan.history", {"limit": 201}),
            ("scan.history", {"limit": True}),
            ("scan.history", {"cursor": None}),
            ("instruments.search", {"query": "x", "limit": 51}),
            (
                "thesis.update",
                {"thesisId": "fake", "statement": "x", "expectedVersion": 0},
            ),
            ("holdings.upsert", {"instrumentId": "us:ZZAR", "quantity": "-5"}),
            ("holdings.upsert", {"instrumentId": "us:ZZAR", "quantity": "0.00001"}),
            (
                "holdings.upsert",
                {"instrumentId": "us:ZZAR", "quantity": "100000000000000"},
            ),
            (
                "decision.act",
                {"decisionId": "fake", "action": "ignore", "note": "x" * 201},
            ),
            ("secrets.set", {"name": "jevKey", "value": "two words"}),
            ("settings.update", {"secContactEmail": "not-an-email"}),
            (
                "paper.createAccount",
                {"name": "fake", "initialCash": "0.0000", "startDate": "2026-09-01"},
            ),
            (
                "paper.createAccount",
                {"name": "fake", "initialCash": "1.00001", "startDate": "2026-09-01"},
            ),
            (
                "paper.order.place",
                {
                    "accountId": "fake",
                    "instrumentId": "us:ZZAR",
                    "side": "buy",
                    "quantity": 0,
                    "orderType": "market_open",
                    "idempotencyKey": "fake",
                },
            ),
        ]
        for method, value in cases:
            with self.subTest(method=method, value=value):
                with self.assertRaises(checker.ContractError):
                    checker.validate(
                        value,
                        read(CONTRACTS / "methods" / (method + ".json"))["params"],
                        types,
                    )

    def test_schema_rejects_unknown_keyword_even_without_examples(self):
        self.rejected(
            "types.schema.json",
            lambda t: t["$defs"]["Decimal"].update(minLenght=1),
            "minLenght",
        )

    def test_refs_are_checked_inside_unused_types_and_arrays(self):
        self.rejected(
            "types.schema.json",
            lambda t: t["$defs"].update(
                Unused={"type": "array", "items": {"$ref": "https://example.com/x"}}
            ),
            "https://example.com/x",
        )

    def test_circular_ref_is_rejected(self):
        self.rejected(
            "types.schema.json",
            lambda t: t["$defs"].update(Cycle={"$ref": "#/$defs/Cycle"}),
            "circular",
        )

    def test_schema_keyword_shapes_are_checked(self):
        for schema in (
            {"type": "bogus"},
            {"type": "string", "pattern": "["},
            {
                "type": "object",
                "properties": {},
                "required": ["missing"],
                "additionalProperties": False,
            },
            {"type": "integer", "minimum": True},
            {"anyOf": []},
        ):
            with self.subTest(schema=schema):
                self.rejected(
                    "types.schema.json",
                    lambda t: t["$defs"].update(Unused=schema),
                    "Unused",
                )

    def test_index_and_file_set_are_strict(self):
        self.rejected("index.json", lambda i: i["methods"].pop(), "40")
        self.rejected(
            "index.json",
            lambda i: i["methods"].__setitem__(0, i["methods"][1]),
            "duplicate",
        )
        self.rejected(
            "methods/app.ping.json", lambda m: m.update(method="app.other"), "app.ping"
        )

    def test_error_metadata_and_method_membership_are_strict(self):
        self.rejected(
            "methods/scan.start.json",
            lambda m: m["examples"][1]["error"]["data"].update(retryable="false"),
            "retryable",
        )
        self.rejected(
            "methods/scan.start.json",
            lambda m: m["examples"][1]["error"]["data"].update(retryable=True),
            "retryable",
        )
        self.rejected(
            "methods/scan.retryBatch.json",
            lambda m: m["examples"][-1]["error"]["data"].pop("requestId"),
            "requestId",
        )
        self.rejected(
            "methods/scan.start.json",
            lambda m: m["examples"][1]["error"].update(code="NOPE"),
            "NOPE",
        )
        self.rejected(
            "methods/scan.start.json",
            lambda m: m["errors"].remove("CONFIG_REQUIRED"),
            "CONFIG_REQUIRED",
        )

    def test_invalid_argument_does_not_bypass_other_fields(self):
        self.rejected(
            "methods/holdings.upsert.json",
            lambda m: m["examples"][1]["params"].update(x=1),
            "params.x",
        )
        self.rejected(
            "methods/thesis.create.json",
            lambda m: m["examples"][1]["params"].update(instrumentId=7),
            "instrumentId",
        )

    def test_error_coverage_and_retryable_catalog_are_enforced(self):
        self.rejected(
            "methods/instruments.search.json",
            lambda m: m["examples"].pop(),
            "CANCELLED",
        )
        self.rejected(
            "errors.json",
            lambda e: e["codes"]["TIMEOUT"].update(retryable=False),
            "TIMEOUT",
        )

    def test_duplicate_example_and_result_error_union_are_rejected(self):
        self.rejected(
            "methods/app.bootstrap.json",
            lambda m: m["examples"][1].update(name=m["examples"][0]["name"]),
            "duplicate",
        )
        self.rejected(
            "methods/app.ping.json",
            lambda m: m["examples"][0].update(error={}),
            "exactly one",
        )

    def test_nested_unknown_fields_and_notification_enum_are_rejected(self):
        self.rejected(
            "methods/settings.get.json",
            lambda m: m["examples"][0]["result"]["allowedDomains"][0].update(x=1),
            "x",
        )
        self.rejected(
            "notifications.json",
            lambda n: n["scan.progress"]["example"].update(stage="unknown"),
            "stage",
        )

    def test_generator_rejects_output_inside_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "contracts"
            shutil.copytree(CONTRACTS, target)
            out = target / "mock.js"
            result = self.run_script(
                "gen_proto_mock.py", "--contracts", target, "--out", out
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(out.exists())

    def test_generator_rejects_invalid_contracts_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "contracts"
            shutil.copytree(CONTRACTS, target)
            (target / "methods/app.ping.json").unlink()
            out = Path(tmp) / "mock.js"
            result = self.run_script(
                "gen_proto_mock.py", "--contracts", target, "--out", out
            )
            self.assertEqual(result.returncode, 1)
            self.assertFalse(out.exists())

    def test_pagination_and_rejected_order_remain_required_in_schema(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        for method in ("scan.history", "paper.orders"):
            data = read(CONTRACTS / "methods" / (method + ".json"))
            checker.validate(data["examples"][0]["result"], data["result"], types)
            result = copy.deepcopy(data["examples"][0]["result"])
            result.pop("nextCursor", None)
            with self.assertRaises(checker.ContractError):
                checker.validate(result, data["result"], types)
        schema = types["$defs"]["RpcError"]
        error = read(CONTRACTS / "methods/paper.order.place.json")["examples"][1][
            "error"
        ]
        checker.validate(error, schema, types)
        error["data"].pop("orderId", None)
        with self.assertRaises(checker.ContractError):
            checker.validate(error, schema, types)

    def test_required_fields_are_not_exempt_by_example_name(self):
        for index in range(4):
            with self.subTest(method="scan.history", example=index):
                self.rejected(
                    "methods/scan.history.json",
                    lambda m: m["examples"][index]["result"].pop("nextCursor", None),
                    "nextCursor",
                )
        self.rejected(
            "methods/paper.orders.json",
            lambda m: m["examples"][0]["result"].pop("nextCursor", None),
            "nextCursor",
        )
        for index in (1, 2):
            with self.subTest(method="paper.order.place", example=index):
                self.rejected(
                    "methods/paper.order.place.json",
                    lambda m: m["examples"][index]["error"]["data"].pop(
                        "orderId", None
                    ),
                    "orderId",
                )
        self.rejected(
            "methods/paper.orders.json",
            lambda m: m["examples"][0]["result"].update(nextCursor=4),
            "nextCursor",
        )
        self.rejected(
            "methods/paper.order.place.json",
            lambda m: m["examples"][1]["error"]["data"].update(orderId=False),
            "orderId",
        )

    def test_error_failures_identify_method_and_example(self):
        result = self.mutate(
            "methods/scan.start.json",
            lambda m: m["examples"][1]["error"]["data"].pop("retryable"),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("scan.start/config_required", result.stdout + result.stderr)

    def test_generic_oneof_checks_all_branches(self):
        checker = self.checker()
        schema = {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"code": {"type": "string", "enum": ["X"]}},
                    "required": ["code"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                    "additionalProperties": False,
                },
            ]
        }
        with self.assertRaises(checker.ContractError):
            checker.validate({"code": "X"}, schema, {})

    def test_empty_or_malformed_schema_and_error_data_are_rejected(self):
        for schema in (
            {},
            {"type": "object", "properties": [], "additionalProperties": False},
            {"type": "array", "items": {}},
            {"type": "string", "enum": []},
            {"type": "string", "enum": [1]},
            {"type": "integer", "const": True},
        ):
            with self.subTest(schema=schema):
                self.rejected(
                    "types.schema.json", lambda t: t["$defs"].update(Bad=schema), "Bad"
                )
        self.rejected(
            "methods/scan.start.json",
            lambda m: m["examples"][1]["error"].update(data=[]),
            "data",
        )
        self.rejected(
            "methods/scan.start.json",
            lambda m: m["examples"][1].update(params=[]),
            "params",
        )

    def test_method_metadata_and_closed_object_schemas_are_enforced(self):
        self.rejected(
            "methods/app.ping.json", lambda m: m.update(timeoutMs=True), "timeoutMs"
        )
        self.rejected(
            "methods/app.ping.json", lambda m: m.update(owner="P-01"), "owner"
        )
        self.rejected(
            "methods/app.ping.json",
            lambda m: m.update(summary="English only"),
            "Chinese",
        )
        self.rejected(
            "methods/app.ping.json",
            lambda m: m["params"].update(additionalProperties=True),
            "additionalProperties",
        )
        self.rejected(
            "types.schema.json",
            lambda t: t["$defs"]["Instrument"].update(additionalProperties=True),
            "additionalProperties",
        )

    def test_json_duplicate_keys_and_nonfinite_numbers_are_rejected(self):
        checker = self.checker()
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "fixture.json"
                path.write_text(raw, encoding="utf-8")
                with self.assertRaises(checker.ContractError):
                    checker.load_json(path)

    def test_missing_and_extra_method_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "contracts"
            shutil.copytree(CONTRACTS, target)
            (target / "methods/app.ping.json").unlink()
            (target / "methods/app.extra.json").write_text("{}", encoding="utf-8")
            result = self.run_script("check_contracts.py", "--contracts", target)
            self.assertEqual(result.returncode, 1)
            self.assertIn("app.ping.json", result.stderr)
            self.assertIn("app.extra.json", result.stderr)

    def test_generator_output_symlink_cannot_bypass_contract_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "contracts"
            shutil.copytree(CONTRACTS, target)
            out = Path(tmp) / "linked.js"
            out.symlink_to(target / "index.json")
            before = (target / "index.json").read_bytes()
            result = self.run_script(
                "gen_proto_mock.py", "--contracts", target, "--out", out
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual((target / "index.json").read_bytes(), before)

    def test_missing_output_check_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "missing.js"
            result = self.run_script(
                "gen_proto_mock.py", "--contracts", CONTRACTS, "--out", out, "--check"
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("line 1", result.stdout)
            self.assertFalse(out.exists())

    def test_local_refs_resolve_escaped_json_pointer_tokens(self):
        checker = self.checker()
        types = {"$defs": {"a/b~c": {"type": "string"}}}
        schema = {"$ref": "#/$defs/a~1b~0c"}
        checker.check_schema(schema, types)
        checker.validate("fictional", schema, types)
        with self.assertRaises(checker.ContractError):
            checker.resolve_ref("#/$defs/a~2b", types)

    def test_money_price_and_quantity_precision_are_distinct(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        cases = [
            ("Portfolio", "cash", "12.34567"),
            ("Portfolio", "cash", "12.34"),
            ("Fill", "price", "12.3456789"),
            ("Fill", "fee", "0.00001"),
            ("Holding", "quantity", "1.00001"),
        ]
        for name, field, value in cases:
            with self.subTest(type=name, field=field, value=value):
                with self.assertRaises(checker.ContractError):
                    checker.validate(
                        value, types["$defs"][name]["properties"][field], types
                    )

    def test_zero_quantity_rejects_nonnull_cost(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        params = read(CONTRACTS / "methods/holdings.upsert.json")["params"]
        value = {"instrumentId": "us:ZZAR", "quantity": "0.0000", "avgCost": "2.0000"}
        with self.assertRaises(checker.ContractError):
            checker.validate(value, params, types)
        value["avgCost"] = None
        checker.validate(value, params, types)

    def test_holding_market_value_is_not_limited_by_quantity_storage_capacity(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        fields = types["$defs"]["Holding"]["properties"]
        # A legal maximum position valued at 1000 exceeds the quantity column's range.
        checker.validate("99999999999999.9999", fields["quantity"], types)
        checker.validate("99999999999999999.9000", fields["marketValue"], types)
        for value in ("999999999999999.0000", "1e14", "1.00000", "-1.0000"):
            with self.subTest(value=value):
                with self.assertRaises(checker.ContractError):
                    checker.validate(value, fields["quantity"], types)
        for value in ("1e17", "1.00000", "-1.0000", 1000):
            with self.subTest(value=value):
                with self.assertRaises(checker.ContractError):
                    checker.validate(value, fields["marketValue"], types)

    def test_risk_insufficient_error_requires_sample_counts(self):
        for field in ("observations", "required"):
            with self.subTest(field=field):
                self.rejected(
                    "methods/risk.compute.json",
                    lambda m: m["examples"][-1]["error"]["data"].pop(field),
                    field,
                )

    def test_contract_examples_and_mock_match_author_source(self):
        payload = author_payload()
        self.assertEqual(len(payload["examples"]), 40)
        self.assertEqual(sum(len(e) for e in payload["examples"].values()), 92)
        for method, examples in payload["examples"].items():
            actual = read(CONTRACTS / "methods" / (method + ".json"))["examples"]
            self.assertEqual(
                actual, [dict(name=name, **e) for name, e in examples.items()]
            )
        notifications = read(CONTRACTS / "notifications.json")
        for name, example in payload["notifications"].items():
            self.assertEqual(notifications[name]["example"], example)
        from scripts.gen_proto_mock import HEADER

        expected = (
            HEADER
            + "window.MOCK = "
            + json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False)
            + ";\n"
        ).encode("utf-8")
        self.assertEqual(
            expected, (ROOT / "design/prototype/data/mock.js").read_bytes()
        )

    def test_e1_high_killmet_evidence_describes_completed_sale(self):
        source = author_payload()
        mock = (ROOT / "design/prototype/data/mock.js").read_text(encoding="utf-8")
        payload = json.loads(mock.split("window.MOCK = ", 1)[1][:-2])
        for dataset in (source, payload):
            items = list(decisions(dataset))
            self.assertTrue(items)
            for item in items:
                self.assertEqual(item["questionSetVersion"], "qs-2026-11-02.2")
            e1 = [
                d for d in items if d["event"]["eventId"] == "us:0009990001-26-000001"
            ]
            self.assertTrue(e1)
            for item in e1:
                self.assertEqual(item["probabilities"]["killMet"], 0.93)
                self.assertIn("completed sale", item["event"]["title"].lower())
                text = item["evidence"]["text"]
                self.assertIn("completed the sale of 4.5%", text)
                self.assertNotIn("intends", text.lower())
                self.assertNotIn("proposed", item["evidence"]["passageText"].lower())

    def test_e1_evidence_offsets_slice_exact_completed_sentence(self):
        doc = (ROOT / "docs/06-语义判定与Jev.md").read_text(encoding="utf-8")
        section = doc.split("## 10.", 1)[1]
        passage = next(
            line[2:]
            for line in section.splitlines()
            if line.startswith("> Item 8.01 Other Events.")
        )
        payload = author_payload()
        e1 = [
            d
            for d in decisions(payload)
            if d["event"]["eventId"] == "us:0009990001-26-000001"
        ]
        self.assertTrue(e1)
        for item in e1:
            evidence = item["evidence"]
            self.assertEqual(evidence["passageText"], passage)
            start, end = evidence["sentenceStart"], evidence["sentenceEnd"]
            self.assertEqual(type(start), int)
            self.assertEqual(type(end), int)
            self.assertEqual(passage[start:end], evidence["text"])
            self.assertTrue(evidence["text"].startswith("On October 29, 2026,"))
            self.assertTrue(evidence["text"].endswith("registered secondary offering."))
            self.assertEqual(
                passage[end:],
                " Following the sale, Atlas continues to hold approximately 31.0% of the outstanding common stock. The Company did not receive any proceeds from the sale.",
            )

    def test_every_success_and_error_example_passes_strict_schema(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        for path in (CONTRACTS / "methods").glob("*.json"):
            method = read(path)
            for example in method["examples"]:
                with self.subTest(method=method["method"], example=example["name"]):
                    if "result" in example:
                        checker.validate(example["result"], method["result"], types)
                    else:
                        schema = types["$defs"][
                            "RiskInsufficientError"
                            if method["method"] == "risk.compute"
                            else "RpcError"
                        ]
                        checker.validate(example["error"], schema, types)

    def test_removing_each_required_response_field_fails(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        checked = []

        def inspect(value, schema, context):
            if "$ref" in schema:
                inspect(value, checker.resolve_ref(schema["$ref"], types), context)
            for keyword in ("anyOf", "oneOf", "allOf"):
                for branch in schema.get(keyword, []):
                    try:
                        checker.validate(value, branch, types)
                    except checker.ContractError:
                        continue
                    inspect(value, branch, context)
            if isinstance(value, dict):
                for field in schema.get("required", []):
                    with self.subTest(path=context + "." + field):
                        self.assertIn(field, value)
                        changed = copy.deepcopy(value)
                        changed.pop(field, None)
                        with self.assertRaises(checker.ContractError):
                            checker.validate(changed, schema, types)
                        checked.append(context + "." + field)
                for field, child in schema.get("properties", {}).items():
                    if field in value:
                        inspect(value[field], child, context + "." + field)
            if isinstance(value, list) and "items" in schema:
                for index, child in enumerate(value):
                    inspect(child, schema["items"], "%s[%d]" % (context, index))

        for path in (CONTRACTS / "methods").glob("*.json"):
            method = read(path)
            for example in method["examples"]:
                value = example.get("result", example.get("error"))
                schema = (
                    method["result"]
                    if "result" in example
                    else types["$defs"][
                        "RiskInsufficientError"
                        if method["method"] == "risk.compute"
                        else "RpcError"
                    ]
                )
                checker.validate(value, schema, types)
                inspect(value, schema, method["method"] + "/" + example["name"])
        self.assertTrue(checked)

    def test_generated_author_and_mock_method_order_matches_index(self):
        from scripts.gen_proto_mock import generate

        expected = read(CONTRACTS / "index.json")["methods"]
        source = author_payload()
        generated = json.loads(
            generate(CONTRACTS).decode("utf-8").split("window.MOCK = ", 1)[1][:-2]
        )
        mock = json.loads(
            (ROOT / "design/prototype/data/mock.js")
            .read_text(encoding="utf-8")
            .split("window.MOCK = ", 1)[1][:-2]
        )
        self.assertEqual(list(source["examples"]), expected)
        self.assertEqual(list(generated["examples"]), expected)
        self.assertEqual(list(mock["examples"]), expected)

    def test_rejected_order_ids_match_existing_or_reserved_fictional_identity(self):
        payload = author_payload()
        errors = payload["examples"]["paper.order.place"]
        orders = payload["examples"]["paper.orders"]["default"]["result"]["items"]
        position = errors["insufficient_position"]["error"]
        matching = next(
            order for order in orders if order["orderId"] == position["data"]["orderId"]
        )
        self.assertEqual(matching["status"], "rejected")
        self.assertEqual(matching["rejectReason"]["code"], position["data"]["reason"])
        self.assertEqual(
            matching["idempotencyKey"],
            errors["insufficient_position"]["params"]["idempotencyKey"],
        )
        cash_id = errors["insufficient_cash"]["error"]["data"]["orderId"]
        self.assertEqual(cash_id, "01JC8Z5V3Q000000000000RD85")
        self.assertNotIn(cash_id, {order["orderId"] for order in orders})

    def assert_normalized_params(self, method, field, kind):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        schema = read(CONTRACTS / "methods" / (method + ".json"))["params"]
        base = {
            "settings.update": {},
            "secrets.set": {"name": "jevKey"},
            "holdings.upsert": {"instrumentId": "us:ZZAR", "quantity": "1"},
            "thesis.create": {"instrumentId": "us:ZZAR", "statement": "虚构逻辑"},
            "thesis.update": {
                "thesisId": "fictional",
                "statement": "虚构逻辑",
                "expectedVersion": 1,
            },
        }[method]
        for value in normalization_cases(kind):
            with self.subTest(
                method=method,
                field=field,
                length=len(value) if isinstance(value, str) else None,
                preview=repr(value)[:50],
            ):
                params = dict(base, **{field: value})
                if normalized_valid(kind, value):
                    checker.validate(params, schema, types)
                else:
                    with self.assertRaises(checker.ContractError):
                        checker.validate(params, schema, types)

    def test_email_params_accept_stripped_and_empty_values(self):
        self.assert_normalized_params("settings.update", "secContactEmail", "email")

    def test_secret_params_bound_normalized_codepoints_and_internal_whitespace(self):
        self.assert_normalized_params("secrets.set", "value", "key")

    def test_thesis_statement_params_bound_stripped_unicode_codepoints(self):
        for method in ("thesis.create", "thesis.update"):
            self.assert_normalized_params(method, "statement", "statement")

    def test_thesis_kill_params_accept_empty_and_bound_stripped_codepoints(self):
        for method in ("thesis.create", "thesis.update"):
            self.assert_normalized_params(method, "killCondition", "kill")

    def test_holding_note_params_bound_stripped_unicode_codepoints(self):
        self.assert_normalized_params("holdings.upsert", "note", "note")

    def test_normalization_patterns_match_python_and_node_codepoint_semantics(self):
        cases = []
        for method, field, kind in (
            ("settings.update", "secContactEmail", "email"),
            ("secrets.set", "value", "key"),
            ("holdings.upsert", "note", "note"),
            ("thesis.create", "statement", "statement"),
            ("thesis.create", "killCondition", "kill"),
            ("thesis.update", "statement", "statement"),
            ("thesis.update", "killCondition", "kill"),
        ):
            schema = read(CONTRACTS / "methods" / (method + ".json"))["params"][
                "properties"
            ][field]
            string_schema = next(
                (s for s in schema.get("anyOf", [schema]) if s.get("type") == "string")
            )
            for value in normalization_cases(kind):
                if isinstance(value, str):
                    cases.append(
                        {
                            "method": method,
                            "field": field,
                            "pattern": string_schema["pattern"],
                            "value": value,
                            "expected": normalized_valid(kind, value),
                        }
                    )
        run = subprocess.run(
            [
                "node",
                "-e",
                "const fs=require('fs'); const cases=JSON.parse(fs.readFileSync(0,'utf8')); "
                "console.log(JSON.stringify(cases.map(c=>['','u'].map(flags=>new RegExp(c.pattern,flags).test(c.value)))));",
            ],
            input=json.dumps(cases, ensure_ascii=False),
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        all_results = json.loads(run.stdout)
        self.assertEqual(len(all_results), len(cases))
        for case, results in zip(cases, all_results):
            with self.subTest(
                method=case["method"], field=case["field"], length=len(case["value"])
            ):
                self.assertEqual(
                    re.search(case["pattern"], case["value"]) is not None,
                    case["expected"],
                )
                self.assertEqual(results, [case["expected"], case["expected"]])

    def test_output_schemas_keep_strict_canonical_lengths(self):
        checker = self.checker()
        types = read(CONTRACTS / "types.schema.json")
        for name in ("Thesis", "ThesisVersionItem"):
            props = types["$defs"][name]["properties"]
            self.assertEqual(props["statement"]["maxLength"], 500)
            self.assertEqual(props["killCondition"]["anyOf"][0]["maxLength"], 300)
            with self.assertRaises(checker.ContractError):
                checker.validate(" " + "😀" * 500 + " ", props["statement"], types)
        email = types["$defs"]["Settings"]["properties"]["secContactEmail"]
        self.assertEqual(email["anyOf"][0]["maxLength"], 120)
        with self.assertRaises(checker.ContractError):
            checker.validate(" name@example.com ", email, types)


if __name__ == "__main__":
    unittest.main()

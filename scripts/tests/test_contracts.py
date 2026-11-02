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
            with self.assertRaises(checker.ContractError):
                checker.validate(data["examples"][0]["result"], data["result"], types)
        schema = types["$defs"]["RpcError"]
        error = read(CONTRACTS / "methods/paper.order.place.json")["examples"][1][
            "error"
        ]
        with self.assertRaises(checker.ContractError):
            checker.validate(error, schema, types)

    def test_legacy_omissions_are_limited_to_named_examples(self):
        self.rejected(
            "methods/paper.orders.json",
            lambda m: m["examples"][0].update(name="new_example"),
            "nextCursor",
        )
        self.rejected(
            "methods/paper.order.place.json",
            lambda m: m["examples"][1].update(name="new_error"),
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

    def test_risk_insufficient_error_requires_sample_counts(self):
        for field in ("observations", "required"):
            with self.subTest(field=field):
                self.rejected(
                    "methods/risk.compute.json",
                    lambda m: m["examples"][-1]["error"]["data"].pop(field),
                    field,
                )


if __name__ == "__main__":
    unittest.main()

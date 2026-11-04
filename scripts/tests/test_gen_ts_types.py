import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/gen_ts_types.py"


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contracts = self.root / "contracts"
        self.out = self.root / "generated"
        shutil.copytree(ROOT / "contracts", self.contracts)

    def run_gen(self, *args):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--contracts",
                str(self.contracts),
                "--out",
                str(self.out),
                *args,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def outputs(self):
        return {p.name: p.read_bytes() for p in self.out.iterdir()}

    def test_deterministic_and_preserves_index_and_examples(self):
        self.assertEqual(self.run_gen().returncode, 0)
        first = self.outputs()
        self.assertEqual(self.run_gen().returncode, 0)
        self.assertEqual(first, self.outputs())
        self.assertEqual(self.run_gen("--check").returncode, 0)
        methods = first["methods.ts"].decode()
        names = json.loads((self.contracts / "index.json").read_text())["methods"]
        self.assertEqual(
            sorted(names, key=lambda n: methods.index('"' + n + '"')), names
        )
        text = first["mock-data.ts"].decode()
        examples = json.loads(
            text.split("export const MOCK_EXAMPLES = ")[1].split(" as const;")[0]
        )
        for name in names:
            original = json.loads(
                (self.contracts / "methods" / (name + ".json")).read_text()
            )
            self.assertEqual(examples[name], original["examples"])
        self.assertNotRegex(first["types.ts"].decode(), r"\bany\b")

    def test_check_detects_drift_without_writing(self):
        self.assertEqual(self.run_gen().returncode, 0)
        path = self.out / "types.ts"
        path.write_text("old output\n")
        before = self.outputs()
        result = self.run_gen("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("types.ts", result.stdout)
        self.assertEqual(self.outputs(), before)

    def test_check_detects_mixed_outputs_after_interrupted_publish(self):
        self.assertEqual(self.run_gen().returncode, 0)
        types_path = self.contracts / "types.schema.json"
        types = json.loads(types_path.read_text())
        types["$defs"]["NewType"] = {"type": "string"}
        types_path.write_text(json.dumps(types))
        method_path = self.contracts / "methods/app.ping.json"
        method = json.loads(method_path.read_text())
        method["timeoutMs"] = 3_000
        method["examples"][0]["result"]["uptimeMs"] = 42
        method_path.write_text(json.dumps(method))
        module, _ = self.renderer()
        expected = module.generate(self.contracts)
        (self.out / "types.ts").write_bytes(expected["types.ts"])
        before = self.outputs()
        result = self.run_gen("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("methods.ts", result.stdout)
        self.assertIn("mock-data.ts", result.stdout)
        self.assertEqual(self.outputs(), before)

    def test_late_invalid_schema_does_not_overwrite_any_output(self):
        self.assertEqual(self.run_gen().returncode, 0)
        before = self.outputs()
        path = self.contracts / "methods/demo.clear.json"
        item = json.loads(path.read_text())
        item["result"] = {"type": "unrecognized"}
        path.write_text(json.dumps(item))
        result = self.run_gen()
        self.assertEqual(result.returncode, 2)
        self.assertIn("demo.clear", result.stderr)
        self.assertEqual(self.outputs(), before)

    def test_unrepresentable_numeric_bound_fails_cleanly_without_overwriting(self):
        self.assertEqual(self.run_gen().returncode, 0)
        before = self.outputs()
        path = self.contracts / "types.schema.json"
        types = json.loads(path.read_text())
        types["$defs"]["HugeBound"] = {"type": "integer", "minimum": 10**400}
        path.write_text(json.dumps(types))
        result = self.run_gen()
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.outputs(), before)

    def test_invalid_schema_does_not_create_partial_output(self):
        path = self.contracts / "notifications.json"
        item = json.loads(path.read_text())
        item["budget.updated"]["params"] = {"type": "array"}
        path.write_text(json.dumps(item))
        self.assertEqual(self.run_gen().returncode, 2)
        self.assertFalse(self.out.exists())

    def renderer(self):
        spec = importlib.util.spec_from_file_location("gen_ts_types", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, module.SchemaTypes({"$defs": {"Text": {"type": "string"}}})

    def test_refs_nullable_combinations_arrays_and_objects(self):
        _, renderer = self.renderer()
        cases = [
            ({"$ref": "types.schema.json#/$defs/Text"}, "Text"),
            ({"anyOf": [{"$ref": "#/$defs/Text"}, {"type": "null"}]}, "(Text | null)"),
            ({"type": ["number", "null"]}, "(number | null)"),
            (
                {"oneOf": [{"type": "string"}, {"type": "boolean"}]},
                "(string | boolean)",
            ),
            (
                {"allOf": [{"type": "string"}, {"type": "string", "const": "x"}]},
                '(string & "x")',
            ),
            ({"type": "array", "items": {"type": "number"}}, "Array<number>"),
            (
                {"type": "object", "properties": {}, "additionalProperties": False},
                "Record<string, never>",
            ),
            (
                {"type": "object", "additionalProperties": True},
                "Record<string, unknown>",
            ),
            (
                {"type": "object", "additionalProperties": {"type": "number"}},
                "Record<string, number>",
            ),
        ]
        for schema, expected in cases:
            with self.subTest(schema=schema):
                self.assertEqual(renderer.render(schema, "case"), expected)
        obj = renderer.render(
            {
                "type": "object",
                "properties": {"odd-key": {"type": "string"}},
                "additionalProperties": False,
            },
            "object",
        )
        self.assertIn('"odd-key"?: string', obj)

    def test_invalid_keywords_refs_constraints_are_rejected(self):
        module, renderer = self.renderer()
        invalid = [
            {},
            {"type": "mystery"},
            {"anyOf": []},
            {"$ref": "#/$defs/Missing"},
            {"$ref": "https://example.com/schema"},
            {"type": "string", "not": {"const": "x"}},
            {"type": "array"},
            {"type": "number", "minimum": "0"},
            {"type": "string", "enum": [1]},
            {"type": "string", "minLength": 4, "maxLength": 1},
            {"type": "object", "properties": {}, "required": ["missing"]},
            {"type": "object", "additionalProperties": "bad"},
            {"type": "string", "$defs": []},
        ]
        for schema in invalid:
            with self.subTest(schema=schema), self.assertRaises(module.SchemaError):
                renderer.render(schema, "invalid.path")

    def test_duplicate_json_key_is_rejected(self):
        (self.contracts / "types.schema.json").write_text('{"$defs":{},"$defs":{}}')
        self.assertEqual(self.run_gen().returncode, 2)

    def test_output_cannot_overwrite_contracts(self):
        result = self.run_gen("--out", str(self.contracts))
        self.assertEqual(result.returncode, 2)

    def test_partial_publish_failure_rolls_back_prior_outputs(self):
        module, _ = self.renderer()
        self.assertEqual(self.run_gen().returncode, 0)
        before = self.outputs()
        replace = module.os.replace
        calls = []

        def fail_second(source, target):
            calls.append(str(target))
            if len(calls) == 2:
                raise OSError("injected replacement failure")
            return replace(source, target)

        with (
            patch.object(module.os, "replace", side_effect=fail_second),
            self.assertRaises(OSError),
        ):
            module.publish(self.out, {name: b"changed\n" for name in before})
        self.assertEqual(self.outputs(), before)

    def test_nested_refs_additional_properties_and_literals(self):
        _, renderer = self.renderer()
        renderer.types["$defs"]["Fields"] = {
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "additionalProperties": False,
        }
        self.assertEqual(
            renderer.render({"$ref": "#/$defs/Fields/properties/value"}), "number"
        )
        result = renderer.render(
            {
                "type": "object",
                "properties": {"required": {"type": "number"}},
                "required": ["required"],
                "additionalProperties": {"type": "number"},
            }
        )
        self.assertIn('"required": number', result)
        self.assertIn("Record<string, number>", result)
        self.assertEqual(renderer.render({"type": "boolean", "const": True}), "true")

    def test_invalid_root_schema_reports_path(self):
        path = self.contracts / "types.schema.json"
        item = json.loads(path.read_text())
        item["$schema"] = 5
        path.write_text(json.dumps(item))
        result = self.run_gen()
        self.assertEqual(result.returncode, 2)
        self.assertIn("types.schema.json.$schema", result.stderr)

    def test_object_with_combination_emits_type_alias(self):
        path = self.contracts / "types.schema.json"
        item = json.loads(path.read_text())
        item["$defs"]["Combined"] = {
            "type": "object",
            "properties": {"value": {"type": "number"}},
            "required": ["value"],
            "additionalProperties": False,
            "allOf": [{"type": "object", "additionalProperties": True}],
        }
        path.write_text(json.dumps(item))
        self.assertEqual(self.run_gen().returncode, 0)
        text = (self.out / "types.ts").read_text()
        self.assertIn("export type Combined = ", text)
        self.assertNotIn("export interface Combined", text)

    def assert_invalid_metadata_preserves_outputs(self, filename, field, values):
        self.assertEqual(self.run_gen().returncode, 0)
        before = self.outputs()
        path = self.contracts / filename
        original = json.loads(path.read_text())
        for value in values:
            item = dict(original)
            item[field] = value
            path.write_text(json.dumps(item))
            for args in [(), ("--check",)]:
                with self.subTest(
                    filename=filename, field=field, value=value, args=args
                ):
                    result = self.run_gen(*args)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn(field, result.stderr)
                    self.assertEqual(self.outputs(), before)
        path.write_text(json.dumps(original))

    def test_invalid_method_index_preserves_all_outputs(self):
        index = json.loads((self.contracts / "index.json").read_text())
        self.assert_invalid_metadata_preserves_outputs(
            "index.json",
            "methods",
            [
                [],
                None,
                "app.ping",
                index["methods"] + [index["methods"][0]],
                [""],
                [1],
                [{}],
            ],
        )

    def test_invalid_notification_index_preserves_all_outputs(self):
        index = json.loads((self.contracts / "index.json").read_text())
        self.assert_invalid_metadata_preserves_outputs(
            "index.json",
            "notifications",
            [
                [],
                None,
                "app.ready",
                index["notifications"] + [index["notifications"][0]],
                [""],
                [1],
                [{}],
            ],
        )

    def test_invalid_error_codes_preserve_all_outputs(self):
        self.assert_invalid_metadata_preserves_outputs(
            "errors.json",
            "codes",
            [{}, [], None, {"": {"retryable": False}}],
        )

    def test_invalid_retryable_preserves_all_outputs(self):
        codes = json.loads((self.contracts / "errors.json").read_text())["codes"]
        values = []
        for invalid in [None, "false", 0, 1, {}, []]:
            values.append({**codes, "INTERNAL": {"retryable": invalid}})
        values.extend([{**codes, "INTERNAL": {}}, {**codes, "INTERNAL": None}])
        self.assert_invalid_metadata_preserves_outputs("errors.json", "codes", values)


if __name__ == "__main__":
    unittest.main()

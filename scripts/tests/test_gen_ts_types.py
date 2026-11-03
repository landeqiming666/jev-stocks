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


if __name__ == "__main__":
    unittest.main()

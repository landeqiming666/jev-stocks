from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "vendors" / "jevdb"))
import build as builder  # noqa: E402


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jev build space ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.pin_path = self.root / "pin.json"
        self.data = json.loads(builder.PIN_PATH.read_text())
        self.pin_path.write_text(json.dumps(self.data))
        self.pin = builder.load_pin(self.pin_path)

    def test_pin_rejects_non_mvp0_duckdb_version(self):
        self.data["duckdb_version"] = "1.4.2"
        self.pin_path.write_text(json.dumps(self.data))
        with self.assertRaises(ValueError):
            builder.load_pin(self.pin_path)

    def test_build_plan_uses_static_openssl_and_unsigned_extension(self):
        prefix = self.root / "openssl prefix"
        plan = builder.build_plan(self.pin, self.root, prefix)
        self.assertIn("-DOPENSSL_USE_STATIC_LIBS=ON", plan[0])
        self.assertIn("-DEXTENSION_STATIC_BUILD=ON", plan[0])
        self.assertIn("-DBUILD_EXTENSIONS_ONLY=OFF", plan[0])
        self.assertIn(f"-DOPENSSL_ROOT_DIR={prefix}", plan[0])
        self.assertEqual(plan[-1][-2:], ["--parallel", "2"])
        self.assertEqual(
            builder.extension_path(self.root).relative_to(self.root).as_posix(),
            "src/build/release/extension/jevdb/jevdb.duckdb_extension",
        )

    def test_build_plan_rejects_quote_in_extension_path(self):
        for bad in ("a'b", 'a"b', "a\x00b", "a\nb", "a\rb"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                builder.build_plan(self.pin, self.root / bad, Path("/openssl"))

    def test_build_plan_supports_repository_spaces_without_shell(self):
        plan = builder.build_plan(self.pin, self.root, Path("/openssl"))
        self.assertIn(str(self.root / "src/build/dependencies/duckdb-1.4.3"), plan[0])
        self.assertIn(str(self.root / "src/build/release"), plan[1])

    def test_explicit_dynamic_mode_remains_a_diagnostic_and_unknown_mode_fails(self):
        plan = builder.build_plan(self.pin, self.root, Path("/openssl"), link_mode="dynamic")
        self.assertIn("-DEXTENSION_STATIC_BUILD=OFF", plan[0])
        self.assertIn("-DBUILD_EXTENSIONS_ONLY=ON", plan[0])
        with self.assertRaises(ValueError):
            builder.build_plan(self.pin, self.root, Path("/openssl"), link_mode="guess")

    def test_build_metadata_does_not_depend_on_enclosing_git_head(self):
        plan = builder.build_plan(self.pin, self.root, Path("/openssl"))
        self.assertIn("-DOVERRIDE_GIT_DESCRIBE=v1.4.3-0-gd1dc88f950", plan[0])
        self.assertIn("-DGIT_COMMIT_HASH=d1dc88f950", plan[0])

    def test_unknown_pin_url_or_hash_is_rejected(self):
        for key in ("commit", "source_url", "source_sha256", "duckdb_sha256"):
            data = dict(self.data, **{key: "unknown"})
            self.pin_path.write_text(json.dumps(data))
            with self.subTest(key=key), self.assertRaises(ValueError):
                builder.load_pin(self.pin_path)

    def test_build_plan_rejects_forged_url_even_with_valid_commit(self):
        pin = builder.BuildPin("https://example.invalid/source", builder.COMMIT, "1.4.3", "0.1.0")
        with self.assertRaises(ValueError):
            builder.build_plan(pin, self.root, Path("/openssl"))

    def test_preflight_reports_missing_tool_and_static_library(self):
        with (
            patch.object(builder.shutil, "which", return_value=None),
            self.assertRaisesRegex(ValueError, "cmake"),
        ):
            builder.preflight(self.root, self.root, host="Darwin arm64", version="1.4.3")
        with (
            patch.object(builder.shutil, "which", return_value="/tool"),
            self.assertRaisesRegex(ValueError, "libssl.a"),
        ):
            builder.preflight(self.root, self.root, host="Darwin arm64", version="1.4.3")

    def archive(self, names):
        path = self.root / "source.tar.gz"
        with tarfile.open(path, "w:gz") as stream:
            for name, kind in names:
                item = tarfile.TarInfo(name)
                if kind == "file":
                    item.size = 1
                    stream.addfile(item, io.BytesIO(b"x"))
                else:
                    item.type = tarfile.SYMTYPE
                    item.linkname = "../../escape"
                    stream.addfile(item)
        return path

    def test_archive_rejects_traversal_links_and_wrong_root(self):
        for bad, kind in (
            ("root/../../escape", "file"),
            ("/root/file", "file"),
            ("other/file", "file"),
            ("root/link", "link"),
        ):
            dest = self.root / "unpacked"
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                builder.safe_extract(self.archive([("root/ok", "file"), (bad, kind)]), dest, "root")
            self.assertFalse(dest.exists())

    def test_archive_rejects_existing_destination_symlink(self):
        destination = self.root / "unpacked"
        try:
            destination.symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) != 1314:
                raise
            self.skipTest("Windows session lacks the symlink creation privilege")
        with self.assertRaises(ValueError):
            builder.safe_extract(self.archive([("root/ok", "file")]), destination, "root")

    def symlink_archive(self, *, nested=False):
        archive = self.root / "source.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            file = tarfile.TarInfo("root/file")
            file.size = 1
            stream.addfile(file, io.BytesIO(b"x"))
            link = tarfile.TarInfo("root/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "file"
            stream.addfile(link)
            if nested:
                file.name = "root/link/child"
                stream.addfile(file, io.BytesIO(b"x"))
        return archive

    def test_safe_fixture_symlink_is_preserved(self):
        archive = self.symlink_archive()
        dest = self.root / "unpacked"
        try:
            builder.safe_extract(archive, dest, "root")
        except OSError as error:
            if getattr(error, "winerror", None) != 1314:
                raise
            self.assertFalse(dest.exists())
            self.skipTest("Windows session lacks the symlink creation privilege")
        self.assertTrue((dest / "link").is_symlink())
        builder.verify_tree(archive, dest, "root")

    def test_archive_rejects_member_nested_under_symlink(self):
        archive = self.symlink_archive(nested=True)
        with self.assertRaisesRegex(ValueError, "nested under symlink"):
            builder.safe_extract(archive, self.root / "unsafe", "root")
        self.assertFalse((self.root / "unsafe").exists())

    def test_extracted_source_drift_is_rejected(self):
        archive = self.archive([("root/file", "file")])
        dest = self.root / "unpacked"
        builder.safe_extract(archive, dest, "root")
        (dest / "file").write_text("drift")
        with self.assertRaisesRegex(ValueError, "drift"):
            builder.verify_tree(archive, dest, "root")

    def test_archive_size_and_wrong_host_or_abi_are_rejected(self):
        with patch.object(builder, "MAX_WORK_DIR_BYTES", 0), self.assertRaises(ValueError):
            builder.safe_extract(self.archive([("root/file", "file")]), self.root / "large", "root")
        for host, version in (("Darwin x86_64", "1.4.3"), ("Darwin arm64", "1.4.2")):
            with self.subTest(host=host), self.assertRaises(ValueError):
                builder.preflight(self.root, self.root, host=host, version=version)

    def test_download_error_or_bad_hash_never_publishes_archive(self):
        destination = self.root / "download.tar.gz"
        for result in (OSError("download error"), None):

            def retrieve(url, filename, result=result):
                Path(filename).write_bytes(b"bad gateway")
                if result:
                    raise result

            with self.subTest(result=result), patch.object(builder, "retrieve", retrieve):
                with self.assertRaises((OSError, ValueError)):
                    builder.download(self.pin.source_url, "0" * 64, destination)
                self.assertFalse(destination.exists())

    def test_sha256_and_private_lock(self):
        source = self.root / "artifact"
        source.write_bytes(b"artifact")
        digest = hashlib.sha256(b"artifact").hexdigest()
        self.assertEqual(builder.sha256_file(source), digest)
        lock = self.root / "build.lock.json"
        builder.write_lock(lock, {"sha": digest})
        self.assertEqual(json.loads(lock.read_text(encoding="utf-8")), {"sha": digest})
        if os.name == "posix":
            self.assertEqual(lock.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PIN_PATH = Path(__file__).with_name("pin.json")
MAX_WORK_DIR_BYTES = 2147483648
COMMIT = "47a9070cba09012bedcc60f5e47e09ccb5c2c1fe"
SOURCE_SHA = "cd52048a08b54a34409e507373b7b1d48c6885f28ef2d76db4e080a584c1d775"
DUCKDB_SHA = "b6a2afd09d9cf07e50d5cd07077df7f7697b61cca2eb00754f5adf89a1ae6c64"


@dataclass(frozen=True)
class BuildPin:
    source_url: str
    commit: str
    duckdb_version: str
    extension_version: str
    source_sha256: str = SOURCE_SHA
    duckdb_url: str = "https://codeload.github.com/duckdb/duckdb/tar.gz/refs/tags/v1.4.3"
    duckdb_sha256: str = DUCKDB_SHA
    license: str = "MIT"
    duckdb_source_id: str = "d1dc88f950"


def load_pin(path: Path) -> BuildPin:
    expected = BuildPin(
        f"https://codeload.github.com/PDAIS/JEVDB/tar.gz/{COMMIT}", COMMIT, "1.4.3", "0.1.0"
    )
    pin = BuildPin(**json.loads(path.read_text(encoding="utf-8")))
    if pin != expected:
        raise ValueError("unknown pin, URL, hash, license or DuckDB ABI")
    return pin


def valid_path(path: Path) -> Path:
    if any(c in str(path) for c in ("'", '"', "\0", "\n", "\r")):
        raise ValueError("path contains a quote, NUL or newline")
    resolved = path.resolve()
    if any(c in str(resolved) for c in ("'", '"', "\0", "\n", "\r")):
        raise ValueError("resolved path contains a quote, NUL or newline")
    return resolved


def extension_path(work_dir: Path) -> Path:
    return valid_path(work_dir) / "src/build/release/extension/jevdb/jevdb.duckdb_extension"


def build_plan(
    pin: BuildPin, work_dir: Path, openssl_prefix: Path, *, link_mode: str = "static"
) -> list[list[str]]:
    if pin != BuildPin(
        f"https://codeload.github.com/PDAIS/JEVDB/tar.gz/{COMMIT}", COMMIT, "1.4.3", "0.1.0"
    ):
        raise ValueError("unsupported pin")
    if link_mode not in ("static", "dynamic"):
        raise ValueError("unknown extension link mode")
    src = valid_path(work_dir) / "src"
    prefix = valid_path(openssl_prefix)
    release = str(src / "build/release")
    return [
        [
            "cmake",
            "-S",
            str(src / "build/dependencies/duckdb-1.4.3"),
            "-B",
            release,
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DBUILD_EXTENSIONS_ONLY={'OFF' if link_mode == 'static' else 'ON'}",
            f"-DEXTENSION_STATIC_BUILD={'ON' if link_mode == 'static' else 'OFF'}",
            "-DBUILD_UNITTESTS=OFF",
            "-DBUILD_SHELL=OFF",
            "-DDISABLE_BUILTIN_EXTENSIONS=ON",
            f"-DDUCKDB_EXTENSION_CONFIGS={src / 'extension_config.cmake'}",
            f"-DOVERRIDE_GIT_DESCRIBE=v1.4.3-0-g{pin.duckdb_source_id}",
            f"-DGIT_COMMIT_HASH={pin.duckdb_source_id}",
            f"-DOPENSSL_ROOT_DIR={prefix}",
            "-DOPENSSL_USE_STATIC_LIBS=ON",
            f"-DOPENSSL_SSL_LIBRARY={prefix / 'lib/libssl.a'}",
            f"-DOPENSSL_CRYPTO_LIBRARY={prefix / 'lib/libcrypto.a'}",
        ],
        ["cmake", "--build", release, "--target", "jevdb_loadable_extension", "--parallel", "2"],
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def retrieve(url: str, filename: str) -> None:
    with urllib.request.urlopen(url, timeout=30) as response, open(filename, "wb") as out:
        if response.status != 200 or not response.url.startswith("https://codeload.github.com/"):
            raise ValueError("unexpected source download response")
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_WORK_DIR_BYTES:
                raise ValueError("source download exceeds limit")
            out.write(chunk)


def download(url: str, expected: str, destination: Path) -> None:
    if destination.is_symlink():
        raise ValueError("archive cannot be a symlink")
    if destination.exists():
        if sha256_file(destination) != expected:
            raise ValueError("cached source checksum mismatch")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(dir=destination.parent, prefix="download-")
    os.close(fd)
    try:
        retrieve(url, filename)
        if sha256_file(Path(filename)) != expected:
            raise ValueError("source checksum mismatch")
        os.replace(filename, destination)
    finally:
        Path(filename).unlink(missing_ok=True)


def archive_members(stream: tarfile.TarFile, root: str):
    members = stream.getmembers()
    total = 0
    seen = set()
    for item in members:
        parts = PurePosixPath(item.name).parts
        if (
            not parts
            or parts[0] != root
            or item.name.startswith("/")
            or ".." in parts
            or "\\" in item.name
            or not (item.isdir() or item.isfile() or item.issym())
            or item.name in seen
        ):
            raise ValueError("unsafe archive member or unexpected source root")
        if item.issym():
            linked = posixpath.normpath(posixpath.join(posixpath.dirname(item.name), item.linkname))
            if (
                item.linkname.startswith("/")
                or "\\" in item.linkname
                or not linked.startswith(root + "/")
            ):
                raise ValueError("archive symlink escapes source root")
        seen.add(item.name)
        total += item.size
        if total > MAX_WORK_DIR_BYTES or len(members) > 100000:
            raise ValueError("unpacked source exceeds limit")
    links = {item.name for item in members if item.issym()}
    for item in members:
        if any(parent.as_posix() in links for parent in PurePosixPath(item.name).parents):
            raise ValueError("archive member nested under symlink")
    return members


def safe_extract(archive: Path, destination: Path, root: str) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError("extraction destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as stream:
        members = archive_members(stream, root)
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix="unpack-") as tmp:
            staging = Path(tmp) / "tree"
            staging.mkdir()
            for item in members:
                target = staging.joinpath(*PurePosixPath(item.name).parts[1:])
                if item.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif item.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with stream.extractfile(item) as source, target.open("xb") as out:
                        shutil.copyfileobj(source, out)
                    target.chmod(0o755 if item.mode & 0o111 else 0o644)
            for item in members:
                if item.issym():
                    target = staging.joinpath(*PurePosixPath(item.name).parts[1:])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(item.linkname)
                    target.resolve().relative_to(staging.resolve())
            os.replace(staging, destination)


def verify_tree(archive: Path, destination: Path, root: str) -> None:
    with tarfile.open(archive) as stream:
        for item in archive_members(stream, root):
            relative = PurePosixPath(item.name).parts[1:]
            target = destination.joinpath(*relative)
            if item.issym():
                if not target.is_symlink() or os.readlink(target) != item.linkname:
                    raise ValueError("source symlink drift")
                target.resolve().relative_to(destination.resolve())
                continue
            if target.is_symlink() or target.resolve() != destination.resolve().joinpath(*relative):
                raise ValueError("source tree symlink escape")
            if item.isfile():
                with stream.extractfile(item) as source:
                    expected = hashlib.sha256(source.read()).hexdigest()
                if not target.is_file() or sha256_file(target) != expected:
                    raise ValueError("extracted source drift")


def preflight(work_dir: Path, prefix: Path, *, host: str, version: str) -> None:
    if host != "Darwin arm64" or version != "1.4.3":
        raise ValueError("requires macOS arm64 and installed DuckDB 1.4.3")
    for name in ("cmake", "ninja", "git", "cc"):
        if not shutil.which(name):
            raise ValueError(f"missing {name}; provision the tool before retrying")
    for name in ("lib/libssl.a", "lib/libcrypto.a", "include/openssl/ssl.h"):
        if not (prefix / name).is_file():
            raise ValueError(f"missing static OpenSSL {name}; provision OpenSSL before retrying")
    if shutil.disk_usage(work_dir).free < MAX_WORK_DIR_BYTES:
        raise ValueError("requires at least 2 GiB free workspace")


def write_lock(path: Path, data: dict) -> None:
    fd, filename = tempfile.mkstemp(dir=path.parent, prefix="lock-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(filename, path)
    finally:
        Path(filename).unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pinned macOS arm64 JEVDB source build")
    parser.add_argument("--openssl-prefix", type=Path, default=Path("/opt/homebrew/opt/openssl@3"))
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".dev-data/jevdb")
    parser.add_argument("--pin", type=Path, default=PIN_PATH)
    parser.add_argument("--link-mode", choices=("static", "dynamic"), default="static")
    args = parser.parse_args(argv)
    command = ["preflight"]
    log_path = ROOT / ".dev-data/jevdb/logs/build.log"
    try:
        pin = load_pin(args.pin)
        work = valid_path(args.work_dir)
        work.relative_to(valid_path(ROOT / ".dev-data/jevdb"))
        prefix = valid_path(args.openssl_prefix)
        work.mkdir(parents=True, exist_ok=True)
        log_path = work / "logs/build.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        python = ROOT / "core/.venv/bin/python"
        installed = json.loads(
            subprocess.check_output(
                [
                    str(python),
                    "-c",
                    "import duckdb, _duckdb, json; "
                    "print(json.dumps({'version': duckdb.__version__, "
                    "'wheel_path': _duckdb.__file__}))",
                ],
                text=True,
            )
        )
        version = installed["version"]
        wheel = Path(installed["wheel_path"])
        wheel_sha256 = sha256_file(wheel)
        host = subprocess.check_output(["uname", "-sm"], text=True).strip()
        preflight(work, prefix, host=host, version=version)
        sources = [
            (pin.source_url, pin.source_sha256, "jevdb.tar.gz", "src", f"JEVDB-{pin.commit}"),
            (
                pin.duckdb_url,
                pin.duckdb_sha256,
                "duckdb-v1.4.3.tar.gz",
                "src/build/dependencies/duckdb-1.4.3",
                "duckdb-1.4.3",
            ),
        ]
        for url, digest, name, directory, root in sources:
            command = ["download/verify", url]
            archive = work / "downloads" / name
            download(url, digest, archive)
            destination = work / directory
            if not destination.exists():
                safe_extract(archive, destination, root)
            verify_tree(archive, destination, root)
        license_text = (work / "src/LICENSE").read_text()
        if (
            not license_text.startswith("MIT License\n")
            or "Permission is hereby granted" not in license_text
        ):
            raise ValueError("MIT license verification failed")
        build_script = work / "src/scripts/build.sh"
        if '"$@"' not in build_script.read_text() or "--parallel 4" not in build_script.read_text():
            raise ValueError("upstream build interface changed")
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "JEV_API_KEY",
                "TYPESAFE_API_KEY",
                "OPENAI_API_KEY",
                "CMAKE_ARGS",
                "CMAKE_BUILD_PARALLEL_LEVEL",
            }
        }
        plan = build_plan(pin, work, prefix, link_mode=args.link_mode)
        with log_path.open("w", encoding="utf-8") as log:
            for command in plan:
                log.write(shlex.join(command) + "\n")
                log.flush()
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, env=env)
        artifact = extension_path(work)
        command = ["otool", "-L", str(artifact)]
        links = subprocess.check_output(command, text=True)
        if any(name in links for name in ("libssl", "libcrypto", "libduckdb.")):
            raise ValueError("extension unexpectedly links dynamic OpenSSL or DuckDB")
        if sha256_file(wheel) != wheel_sha256:
            raise ValueError("installed DuckDB wheel changed during build")
        tools = {
            name: subprocess.check_output([name, "--version"], text=True).splitlines()[0]
            for name in ("cmake", "ninja", "cc")
        }
        write_lock(
            work / "build.lock.json",
            {
                "build": {"status": "PASS"},
                "commit": pin.commit,
                "duckdb_version": version,
                "duckdb_source_id": pin.duckdb_source_id,
                "extension_version": pin.extension_version,
                "link_mode": args.link_mode,
                "wheel_path": str(wheel),
                "wheel_sha256": wheel_sha256,
                "wheel_sha256_before": wheel_sha256,
                "wheel_sha256_after": sha256_file(wheel),
                "source_sha256": pin.source_sha256,
                "duckdb_sha256": pin.duckdb_sha256,
                "extension_sha256": sha256_file(artifact),
                "extension_path": str(artifact),
                "openssl_prefix": str(prefix),
                "tools": tools,
                "commands": plan,
                "upstream_build_sha256": sha256_file(build_script),
                "dynamic_dependencies": links.splitlines()[1:],
                "built_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        print(artifact)
        return 0
    except (OSError, ValueError, TypeError, tarfile.TarError, subprocess.SubprocessError) as error:
        detail = str(error)
        for name in ("JEV_API_KEY", "TYPESAFE_API_KEY", "OPENAI_API_KEY"):
            if os.environ.get(name):
                detail = detail.replace(os.environ[name], "[redacted]")
        print(
            f"BUILD FAILED: {shlex.join(command)}; {detail[:512]}; log: {log_path}", file=sys.stderr
        )
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"FAILED {shlex.join(command)}: {detail[:512]}\n")
        except OSError:
            pass
        return 3


if __name__ == "__main__":
    sys.exit(main())

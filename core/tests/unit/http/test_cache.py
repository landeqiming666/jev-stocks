from pathlib import Path

import httpx
import pytest

from sentinel.http import HttpClient


def test_cache_reuses_body_on_304(tmp_path: Path) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, headers={"ETag": '"one"'}, content=b"hello")
        assert request.headers["If-None-Match"] == '"one"'
        return httpx.Response(304)

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(respond))
    first = client.get("https://example.test/a", source="sec")
    second = client.get("https://example.test/a", source="sec")
    assert not first.from_cache
    assert second.from_cache
    assert second.status == 304
    assert second.content == first.content


@pytest.mark.parametrize(
    "damage", ["body", "missing_body", "metadata", "validators", "digest", "url"]
)
def test_corrupt_cache_refetches_without_validators(tmp_path: Path, damage: str) -> None:
    import json

    from sentinel.http.cache import HttpCache

    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert "if-none-match" not in request.headers
        assert "if-modified-since" not in request.headers
        return httpx.Response(200, headers={"ETag": '"fresh"'}, content=b"fresh")

    cache = HttpCache(tmp_path)
    url = "https://example.test/a"
    with HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(respond)) as client:
        client.get(url, source="sec")
        meta_path = tmp_path / "http" / f"{cache.key(url)}.meta.json"
        body_path = next((tmp_path / "http").glob("*.body"))
        meta = json.loads(meta_path.read_bytes())
        if damage == "body":
            body_path.write_bytes(b"wrong")
        elif damage == "missing_body":
            body_path.unlink()
        elif damage == "metadata":
            meta_path.write_bytes(b"{broken")
        else:
            if damage == "validators":
                meta["etag"] = None
                meta["last_modified"] = None
            elif damage == "digest":
                meta["sha256"] = "../malicious"
            else:
                meta["url"] = "https://other.test/a"
            meta_path.write_text(json.dumps(meta))
        result = client.get(url, source="sec")
    assert not result.from_cache
    assert result.content == b"fresh"
    assert len(calls) == 2


def test_missing_validators_never_cached(tmp_path: Path) -> None:
    with HttpClient(
        cache_dir=tmp_path,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"hello")),
    ) as client:
        client.get("https://example.test/a", source="sec")
    assert not list(tmp_path.rglob("*.meta.json"))
    assert not list(tmp_path.rglob("*.body"))


def test_orphan_304_refetches_unconditionally(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(304)
        assert "if-none-match" not in request.headers
        return httpx.Response(200, content=b"fresh")

    with HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(respond)) as client:
        result = client.get(
            "https://example.test/a", source="sec", headers={"If-None-Match": '"unknown"'}
        )
    assert result.attempts == 2
    assert not result.from_cache
    assert result.content == b"fresh"


def test_atomic_manifest_failure_keeps_previous_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sentinel.http import cache as cache_module
    from sentinel.http.cache import HttpCache

    cache = HttpCache(tmp_path)
    url = "https://example.test/a"
    cache.store(url, b"old", {"ETag": "old"})
    replace = cache_module.os.replace

    def fail_manifest(src: Path, dst: Path) -> None:
        if dst.name.endswith(".meta.json"):
            raise OSError("simulated commit failure")
        replace(src, dst)

    monkeypatch.setattr(cache_module.os, "replace", fail_manifest)
    with pytest.raises(OSError):
        cache.store(url, b"new", {"ETag": "new"})
    entry = cache.load(url)
    assert entry is not None
    assert entry.content == b"old" and entry.etag == "old"
    assert len(list(cache.directory.glob("*.body"))) == 1
    assert not list(cache.directory.glob(".http-*"))


def test_concurrent_cache_bodies_and_metadata_match(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from sentinel.http.cache import HttpCache

    caches = [HttpCache(tmp_path), HttpCache(tmp_path)]
    url = "https://example.test/shared"

    def save(number: int) -> None:
        cache = caches[number % 2]
        value = str(number)
        cache.store(url, value.encode(), {"ETag": value})
        entry = cache.load(url)
        assert entry is not None
        assert entry.content.decode() == entry.etag

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(save, range(30)))


def test_last_modified_charset_and_source_context(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 2:
            assert request.headers["if-modified-since"] == "Mon, 02 Nov 2026 00:00:00 GMT"
            return httpx.Response(304, headers={"Content-Length": "0"})
        assert "if-modified-since" not in request.headers
        return httpx.Response(
            200,
            content=b"\x93hi\x94",
            headers={
                "Last-Modified": "Mon, 02 Nov 2026 00:00:00 GMT",
                "Content-Type": "text/plain; charset=windows-1252",
            },
        )

    with HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(respond)) as client:
        first = client.get("https://example.test/a", source="sec")
        second = client.get("https://example.test/a", source="sec")
        third = client.get("https://example.test/a", source="nasdaq", use_cache=True)
    assert first.text == second.text == third.text == "\u201chi\u201d"
    assert second.from_cache and second.headers["content-length"] == "4"
    assert not third.from_cache


def test_concurrent_304_keeps_its_own_snapshot(tmp_path: Path) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    old_requested = threading.Event()
    release_old = threading.Event()
    url = "https://example.test/shared"

    def respond(request: httpx.Request) -> httpx.Response:
        if request.headers.get("x-variant") == "new":
            assert "if-none-match" not in request.headers
            return httpx.Response(200, headers={"ETag": "new"}, content=b"new")
        if request.headers.get("if-none-match") == "old":
            old_requested.set()
            assert release_old.wait(2.0)
            return httpx.Response(304)
        return httpx.Response(200, headers={"ETag": "old"}, content=b"old")

    with HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(respond)) as client:
        assert client.get(url, source="sec").content == b"old"
        old_path = next((tmp_path / "http").glob("*.body"))
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.get, url, source="sec")
            try:
                assert old_requested.wait(2.0)
                new = client.get(url, source="sec", headers={"X-Variant": "new"})
                assert new.content == b"new" and not new.from_cache
                assert not old_path.exists()
                assert len(list((tmp_path / "http").glob("*.body"))) == 1
            finally:
                release_old.set()
            old = pending.result(timeout=2.0)
        assert old.content == b"old" and old.headers["etag"] == "old" and old.from_cache
        # The stale 304 must not overwrite a newer representation/variant manifest.
        import json

        meta = json.loads(next((tmp_path / "http").glob("*.meta.json")).read_bytes())
        assert meta["etag"] == "new"


def test_unchanged_304_updates_validator_and_preserves_body(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, headers={"ETag": "one"}, content=b"body")
        expected = "one" if len(calls) == 2 else "two"
        assert request.headers["if-none-match"] == expected
        return httpx.Response(304, headers={"ETag": "two"})

    with HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(respond)) as client:
        for _ in range(3):
            assert client.get("https://example.test/a", source="sec").content == b"body"


def test_recorded_fixture_pair_and_retry_header(tmp_path: Path) -> None:
    import json

    from sentinel.http.retry import parse_retry_after

    fixtures = Path(__file__).resolve().parents[2] / "fixtures" / "http"
    pair = json.loads((fixtures / "etag_304.json").read_bytes())
    retry_lines = (fixtures / "error_429_retry_after_2.http").read_text().splitlines()
    value = next(
        line.partition(":")[2].strip() for line in retry_lines if line.startswith("Retry-After:")
    )
    assert parse_retry_after(value) == 2.0
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        response = pair["first" if len(calls) == 1 else "second"]
        return httpx.Response(
            response["status"],
            headers=response["headers"],
            content=response.get("body", "").encode(),
        )

    with HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(respond)) as client:
        assert client.get_text("https://example.test/fixture", source="sec") == "synthetic-body"
        assert client.get("https://example.test/fixture", source="sec").from_cache


def test_repeated_updates_keep_one_body_per_url_and_read_snapshots(tmp_path: Path) -> None:
    from sentinel.http.cache import HttpCache

    cache = HttpCache(tmp_path)
    url = "https://example.test/updates"
    other_url = "https://example.test/other"
    cache.store(other_url, b"other", {"ETag": "other"})
    cache.store(url, b"old", {"ETag": "old"})
    snapshot = cache.load(url)
    assert snapshot is not None
    for version in range(20):
        value = str(version)
        cache.store(url, value.encode(), {"ETag": value})
        assert len(list(cache.directory.glob(f"{cache.key(url)}.*.body"))) == 1
        current = cache.load(url)
        assert current is not None and current.content == value.encode()
    assert snapshot.content == b"old" and snapshot.etag == "old"
    other = cache.load(other_url)
    assert other is not None and other.content == b"other"


@pytest.mark.parametrize("stage", ["body", "manifest"])
def test_repeated_write_failures_preserve_old_cache_without_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    from sentinel.http import cache as cache_module
    from sentinel.http.cache import HttpCache

    cache = HttpCache(tmp_path)
    url = "https://example.test/failure"
    cache.store(url, b"old", {"ETag": "old"})
    replace = cache_module.os.replace

    def fail_write(src: Path, dst: Path) -> None:
        if dst.name.endswith(".body" if stage == "body" else ".meta.json"):
            raise OSError("simulated publication failure")
        replace(src, dst)

    with monkeypatch.context() as patch:
        patch.setattr(cache_module.os, "replace", fail_write)
        for version in range(8):
            with pytest.raises(OSError):
                cache.store(url, str(version).encode(), {"ETag": str(version)})
            entry = cache.load(url)
            assert entry is not None and entry.content == b"old" and entry.etag == "old"
            assert len(list(cache.directory.glob("*.body"))) == 1
        with pytest.raises(OSError):
            cache.store(url, b"old", {"ETag": "changed"})
        entry = cache.load(url)
        assert entry is not None and entry.content == b"old" and entry.etag == "old"
    cache.store(url, b"recovered", {"ETag": "recovered"})
    assert len(list(cache.directory.glob("*.body"))) == 1


def test_cleanup_failure_keeps_published_cache_and_next_update_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sentinel.http.cache import HttpCache

    cache = HttpCache(tmp_path)
    url = "https://example.test/cleanup"
    cache.store(url, b"old", {"ETag": "old"})
    old_path = next(cache.directory.glob("*.body"))
    unlink = Path.unlink

    def fail_old_body(path: Path, *, missing_ok: bool = False) -> None:
        if path == old_path:
            raise PermissionError("simulated cleanup failure")
        unlink(path, missing_ok=missing_ok)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_old_body)
        cache.store(url, b"new", {"ETag": "new"})
        entry = cache.load(url)
        assert entry is not None and entry.content == b"new" and entry.etag == "new"
        assert old_path.exists()
    cache.store(url, b"newer", {"ETag": "newer"})
    assert len(list(cache.directory.glob("*.body"))) == 1
    assert not old_path.exists()

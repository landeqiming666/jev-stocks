"""Immutable bodies with a single atomic manifest commit per URL."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from sentinel import clock

from .policy import MAX_BYTES
from .telemetry import get_logger, log_event

_locks_guard = threading.Lock()
_locks: dict[Path, threading.RLock] = {}


@dataclass(frozen=True)
class CacheEntry:
    content: bytes
    headers: Mapping[str, str]
    etag: str | None
    last_modified: str | None


class HttpCache:
    def __init__(self, cache_dir: Path) -> None:
        self.directory = cache_dir / "http"
        with _locks_guard:
            self._lock = _locks.setdefault(self.directory.resolve(), threading.RLock())

    @staticmethod
    def key(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def _meta(self, url: str) -> Path:
        return self.directory / f"{self.key(url)}.meta.json"

    def load(self, url: str, *, context: str = "", max_bytes: int = MAX_BYTES) -> CacheEntry | None:
        with self._lock:
            metadata_read = False
            try:
                with self._meta(url).open("rb") as file:
                    raw = file.read(65537)
                metadata_read = True
                if len(raw) > 65536:
                    raise ValueError("oversized metadata")
                meta = json.loads(raw)
                if not isinstance(meta, dict) or meta.get("url") != url:
                    raise ValueError("invalid metadata")
                if meta.get("context", "") != context:
                    return None
                digest = meta["sha256"]
                if (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(c not in "0123456789abcdef" for c in digest)
                ):
                    raise ValueError("invalid body digest")
                with (self.directory / f"{self.key(url)}.{digest}.body").open("rb") as file:
                    body = file.read(max_bytes + 1)
                if len(body) > max_bytes or hashlib.sha256(body).hexdigest() != digest:
                    raise ValueError("invalid body")
                etag, modified = meta["etag"], meta["last_modified"]
                if any(
                    value is not None and not isinstance(value, str) for value in (etag, modified)
                ):
                    raise ValueError("invalid validators")
                if not etag and not modified:
                    raise ValueError("missing validators")
                headers = meta["headers"]
                if (
                    not isinstance(headers, dict)
                    or any(
                        not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()
                    )
                    or any("\r" in v or "\n" in v for v in headers.values())
                    or not isinstance(meta["fetched_at"], str)
                ):
                    raise ValueError("invalid headers/timestamp")
                if datetime.fromisoformat(meta["fetched_at"]).tzinfo is None:
                    raise ValueError("invalid timestamp")
                if headers.get("etag") != etag or headers.get("last-modified") != modified:
                    raise ValueError("inconsistent validators")
                return CacheEntry(body, MappingProxyType(headers), etag, modified)
            except FileNotFoundError:
                if metadata_read:
                    self.discard(url)
                return None
            except (OSError, ValueError, KeyError, TypeError, UnicodeError, RecursionError):
                self.discard(url)
                log_event(get_logger(__name__), logging.WARNING, event="http.cache_corrupt")
                return None

    def discard(self, url: str) -> None:
        with self._lock:
            try:
                self._meta(url).unlink(missing_ok=True)
            except OSError:
                log_event(get_logger(__name__), logging.WARNING, event="http.cache_discard_failed")
                return
            self._prune_bodies(url)

    def store(
        self,
        url: str,
        content: bytes,
        headers: Mapping[str, str],
        *,
        context: str = "",
    ) -> None:
        headers = {key.lower(): value for key, value in headers.items()}
        etag, modified = headers.get("etag"), headers.get("last-modified")
        with self._lock:
            if not etag and not modified:
                self.discard(url)
                return
            if len(content) > MAX_BYTES:
                raise ValueError("oversized body")
            self.directory.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(content).hexdigest()
            meta = {
                "url": url,
                "context": context,
                "sha256": digest,
                "etag": etag,
                "last_modified": modified,
                "headers": headers,
                "fetched_at": clock.now().isoformat(),
            }
            body_path = self.directory / f"{self.key(url)}.{digest}.body"
            body_existed = body_path.exists()
            try:
                self._atomic_write(body_path, content)
                # Only the manifest is mutable. Publish before pruning previous generations.
                self._atomic_write(self._meta(url), json.dumps(meta).encode())
            except OSError:
                if not body_existed:
                    self._remove_file(body_path)
                raise
            # load() copies bytes under this same root lock; old snapshots no longer need files.
            self._prune_bodies(url, keep=body_path)

    def _prune_bodies(self, url: str, *, keep: Path | None = None) -> None:
        try:
            for path in self.directory.glob(f"{self.key(url)}.*.body"):
                if path != keep:
                    self._remove_file(path)
        except OSError:
            log_event(get_logger(__name__), logging.WARNING, event="http.cache_cleanup_failed")

    @staticmethod
    def _remove_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log_event(get_logger(__name__), logging.WARNING, event="http.cache_cleanup_failed")

    def revalidate(
        self, url: str, entry: CacheEntry, headers: Mapping[str, str], *, context: str = ""
    ) -> None:
        with self._lock:
            if self.load(url, context=context) == entry:
                self.store(url, entry.content, headers, context=context)

    def _atomic_write(self, target: Path, content: bytes) -> None:
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".http-")
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            self._remove_file(temporary)

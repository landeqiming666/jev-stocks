"""引擎装配：按当前设置构造语义引擎，并在配置变更后重建。"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from sentinel.errors import EngineError, ErrorCode, SentinelError, UserError
from sentinel.semantic.base import EngineName, SemanticEngine
from sentinel.semantic.engines import EngineChange, EngineFactories, select_engine
from sentinel.semantic.engines.jev_direct import JevDirectEngine
from sentinel.semantic.engines.jevdb import DuckDBConnection, JevdbEngine
from sentinel.settings.models import EngineChoice, EngineSnapshot

MODEL_ID = "jev-1.14.0"
ENV_JEVDB_PATH = "SENTINEL_JEVDB_PATH"
ENV_ENDPOINT = "JEV_ENDPOINT"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class _Fingerprint:
    choice: EngineChoice
    key: str
    endpoint: str | None
    extension: str | None


class EngineRuntime:
    """持有唯一活动引擎；配置指纹变化时关闭旧实例再重建。"""

    def __init__(
        self,
        *,
        choice: Callable[[], EngineChoice],
        secret: Callable[[], str | None],
        env: Mapping[str, str],
        notify: Callable[[str, dict[str, object]], None] | None = None,
        jevdb_connection_factory: Callable[..., DuckDBConnection] | None = None,
    ) -> None:
        self._choice, self._secret, self._env, self._notify = choice, secret, env, notify
        self._lock = threading.RLock()
        self._engine: SemanticEngine | None = None
        self._fingerprint: _Fingerprint | None = None
        self._change: EngineChange | None = None
        self._jevdb_connection_factory = jevdb_connection_factory

    # -- 配置读取 ---------------------------------------------------------
    def _key(self) -> str:
        value = self._secret()
        if not isinstance(value, str) or not value:
            raise UserError("CONFIG_REQUIRED", params={"missing": ["jevKey"]})
        return value

    def _endpoint(self) -> str | None:
        raw = self._env.get(ENV_ENDPOINT)
        return raw.strip() or None if isinstance(raw, str) else None

    def _extension(self) -> Path | None:
        raw = self._env.get(ENV_JEVDB_PATH)
        if not isinstance(raw, str) or not raw.strip():
            return None
        return Path(raw).expanduser()

    def jevdb_available(self) -> bool:
        path = self._extension()
        return path is not None and path.is_file()

    # -- 构造 -------------------------------------------------------------
    def _direct(self, key: str) -> SemanticEngine:
        endpoint = self._endpoint()
        engine = (
            JevDirectEngine(api_key=key, model_id=MODEL_ID)
            if endpoint is None
            else JevDirectEngine(api_key=key, model_id=MODEL_ID, endpoint=endpoint)
        )
        return cast(SemanticEngine, engine)

    def _factories(self, key: str) -> EngineFactories:
        def jevdb() -> SemanticEngine:
            path = self._extension()
            if path is None or not path.is_file():
                raise EngineError(ErrorCode.ENGINE_UNAVAILABLE, reason="JEVDB_EXTENSION_MISSING")
            engine = JevdbEngine(
                extension_path=path,
                model_id=MODEL_ID,
                secret_provider=self._key,
                endpoint=self._endpoint(),
                connection_factory=self._jevdb_connection_factory,
            )
            return cast(SemanticEngine, engine)

        def jev_direct() -> SemanticEngine:
            return self._direct(key)

        return EngineFactories(jevdb=jevdb, jev_direct=jev_direct)

    def _build(self, choice: EngineChoice, key: str) -> SemanticEngine:
        if choice == "jev_direct":
            return self._direct(key)
        selection = select_engine(choice, self._factories(key))
        if selection.changed is not None:
            with self._lock:
                if self._change is None:
                    self._change = selection.changed
        return selection.engine

    @staticmethod
    def _close(engine: object | None) -> None:
        closer = getattr(engine, "close", None)
        if callable(closer):
            with suppress(Exception):  # 关闭失败不掩盖新引擎
                closer()

    def engine_for(self, choice: EngineChoice) -> SemanticEngine:
        key = self._key()
        extension = self._extension()
        fingerprint = _Fingerprint(
            choice, _digest(key), self._endpoint(), str(extension) if extension else None
        )
        with self._lock:
            if self._engine is not None and self._fingerprint == fingerprint:
                return self._engine
            engine = self._build(choice, key)
            previous = self._engine
            self._engine, self._fingerprint = engine, fingerprint
        self._close(previous)
        return engine

    def current(self) -> SemanticEngine | None:
        with self._lock:
            return self._engine

    # -- 快照与健康 -------------------------------------------------------
    def snapshot(self) -> EngineSnapshot:
        requested = self._choice()
        if not self._secret():
            return EngineSnapshot(requested=requested, active=None, jevdb_available=False)
        try:
            engine = self.engine_for(requested)
        except SentinelError:
            return EngineSnapshot(requested=requested, active=None, jevdb_available=False)
        return EngineSnapshot(
            requested=requested,
            active=engine.name,
            jevdb_available=engine.name == "jevdb" and self.jevdb_available(),
        )

    def health(self) -> tuple[EngineName | None, Literal["ok", "degraded", "unconfigured"]]:
        if not self._secret():
            return None, "unconfigured"
        try:
            engine = self.engine_for(self._choice())
        except SentinelError:
            return None, "unconfigured"
        state = engine.health().state
        return engine.name, state

    def take_change(self) -> EngineChange | None:
        with self._lock:
            change, self._change = self._change, None
            return change

    def load_jevdb(self) -> bool:
        """显式验证扩展可加载；只用于连接测试，不影响当前活动引擎。"""
        path = self._extension()
        if path is None or not path.is_file():
            return False
        try:
            probe = JevdbEngine(
                extension_path=path,
                model_id=MODEL_ID,
                secret_provider=self._key,
                endpoint=self._endpoint(),
            )
        except Exception:
            return False
        try:
            probe.load()
            return True
        except Exception:
            return False
        finally:
            self._close(probe)

    def invalidate(self) -> None:
        """配置或密钥变更后关闭当前引擎；下一次调用按新指纹重建。"""
        with self._lock:
            engine, self._engine = self._engine, None
            self._fingerprint = None
        self._close(engine)

    def close(self) -> None:
        self.invalidate()


__all__ = [
    "ENV_ENDPOINT",
    "ENV_JEVDB_PATH",
    "MODEL_ID",
    "EngineChange",
    "EngineRuntime",
]

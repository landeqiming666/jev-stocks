"""Immutable migration discovery, SQL splitting and whole-batch recovery."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import duckdb

from sentinel import clock
from sentinel.errors import InternalError

from .backup import _synced_copy
from .db import Database

MAX_MIGRATION_BYTES = 2_097_152
DEFAULT_MIGRATIONS_DIR = Path(__file__).with_suffix("")
SQL_NAME_RE = re.compile(r"^(\d{3})_([a-z0-9_]+)\.sql$")
SCHEMA_TABLE_SQL = r"""CREATE TABLE IF NOT EXISTS schema_version (
  version    INTEGER PRIMARY KEY,
  name       VARCHAR NOT NULL,
  checksum   VARCHAR NOT NULL,       -- 迁移文件内容（UTF-8，换行统一为 \n）的 sha256 十六进制
  applied_at TIMESTAMP NOT NULL
);"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql_path: Path
    checksum: str
    sql: str


@dataclass(frozen=True)
class MigrationReport:
    applied: tuple[int, ...]
    current_version: int
    backup_path: Path | None


def discover_migrations(directory: Path) -> tuple[Migration, ...]:
    if not directory.is_dir():
        raise InternalError(detail=f"migrations directory missing: {directory}")
    migrations: dict[int, Migration] = {}
    for path in sorted(directory.glob("*.sql")):
        match = SQL_NAME_RE.fullmatch(path.name)
        if match is None or int(match[1]) == 0:
            raise InternalError(detail=f"invalid migration filename: {path.name}")
        version = int(match[1])
        if version in migrations:
            raise InternalError(detail=f"duplicate migration version: {path.name}")
        try:
            with path.open("rb") as file:
                content = file.read(MAX_MIGRATION_BYTES + 1)
            if len(content) > MAX_MIGRATION_BYTES:
                raise InternalError(detail=f"migration exceeds 2 MiB: {path.name}")
            sql = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except (OSError, UnicodeError) as exc:
            raise InternalError(detail=f"cannot read migration: {path.name}") from exc
        migrations[version] = Migration(
            version, match[2], path, hashlib.sha256(sql.encode("utf-8")).hexdigest(), sql
        )
    return tuple(migrations[version] for version in sorted(migrations))


def split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    start = index = 0
    quote = ""
    escaped_string = False
    block_depth = 0
    line_comment = False
    dollar = ""
    while index < len(sql):
        character = sql[index]
        pair = sql[index : index + 2]
        if line_comment:
            line_comment = character != "\n"
        elif block_depth:
            if pair == "/*":
                block_depth += 1
                index += 1
            elif pair == "*/":
                block_depth -= 1
                index += 1
        elif dollar:
            if sql.startswith(dollar, index):
                index += len(dollar) - 1
                dollar = ""
        elif quote:
            if escaped_string and character == "\\":
                index += 1
            elif character == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 1
                else:
                    quote = ""
        elif pair == "--":
            line_comment = True
            index += 1
        elif pair == "/*":
            block_depth = 1
            index += 1
        elif character in "'\"":
            quote = character
            escaped_string = (
                character == "'"
                and index > 0
                and sql[index - 1] in "Ee"
                and (index < 2 or not (sql[index - 2].isalnum() or sql[index - 2] == "_"))
            )
        elif character == "$" and (
            match := re.match(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$", sql[index:])
        ):
            dollar = match[0]
            index += len(dollar) - 1
        elif character == ";":
            statements.append(sql[start:index])
            start = index + 1
        index += 1
    statements.append(sql[start:])
    # 保留语法错误给 DuckDB 报告；只排除完全由注释、空白组成的片段。
    return [statement.strip() for statement in statements if _has_sql(statement)]


def _has_sql(statement: str) -> bool:
    index = depth = 0
    while index < len(statement):
        pair = statement[index : index + 2]
        if depth:
            if pair == "/*":
                depth += 1
                index += 1
            elif pair == "*/":
                depth -= 1
                index += 1
        elif pair == "/*":
            depth = 1
            index += 1
        elif pair == "--":
            end = statement.find("\n", index)
            index = len(statement) if end < 0 else end
        elif not statement[index].isspace():
            return True
        index += 1
    return depth != 0


def _creation_allowed(statement: str) -> bool:
    words: list[str] = []
    index = 0
    while index < len(statement) and len(words) < 3:
        pair = statement[index : index + 2]
        if statement[index].isspace():
            index += 1
        elif pair == "--":
            end = statement.find("\n", index)
            index = len(statement) if end < 0 else end
        elif pair == "/*":
            depth = 1
            index += 2
            while index < len(statement) and depth:
                pair = statement[index : index + 2]
                if pair == "/*":
                    depth += 1
                    index += 2
                elif pair == "*/":
                    depth -= 1
                    index += 2
                else:
                    index += 1
        elif match := re.match(r"[A-Za-z_]+", statement[index:]):
            words.append(match[0].upper())
            index += len(match[0])
        else:
            break
    return words[:2] in (["CREATE", "TABLE"], ["CREATE", "INDEX"], ["CREATE", "VIEW"]) or words == [
        "CREATE",
        "UNIQUE",
        "INDEX",
    ]


def _restore_file(backup_path: Path, db_path: Path) -> None:
    with _synced_copy(backup_path, db_path.parent, ".storage-restore-") as temporary:
        temporary.replace(db_path)
        Path(str(db_path) + ".wal").unlink(missing_ok=True)


def migrate(db: Database, directory: Path | None = None) -> MigrationReport:
    migrations = discover_migrations(directory or DEFAULT_MIGRATIONS_DIR)
    with db.read() as reader:
        reader.execute("SELECT version, name, checksum FROM schema_version")
        recorded = cast(list[tuple[int, str, str]], reader.fetchall())
    by_version = {migration.version: migration for migration in migrations}
    for version, name, checksum in recorded:
        migration = by_version.get(version)
        filename = f"{version:03}_{name}.sql"
        if migration is None or migration.name != name or migration.checksum != checksum:
            raise InternalError(detail=f"missing or changed migration: {filename}")
    applied_versions = {row[0] for row in recorded}
    pending = [migration for migration in migrations if migration.version not in applied_versions]
    if not pending:
        return MigrationReport((), db.schema_version, None)
    try:
        backup_path = None if db._new_file else db._backup(None)
    except (OSError, ValueError, duckdb.Error) as exc:
        raise InternalError(detail="migration backup failed; no migrations applied") from exc
    applied: list[int] = []
    for migration in pending:
        ordinal = 1
        try:
            with db.write() as tx:
                for number, statement in enumerate(split_sql(migration.sql), 1):
                    ordinal = number
                    parsed = tx._cursor.extract_statements(statement)
                    if any(
                        item.type.name not in ("CREATE", "INSERT")
                        or (item.type.name == "CREATE" and not _creation_allowed(item.query))
                        for item in parsed
                    ):
                        raise RuntimeError("migration only permits CREATE and INSERT")
                    tx.execute(statement)
                ordinal += 1
                tx.execute(
                    "INSERT INTO schema_version VALUES (?, ?, ?, ?)",
                    [migration.version, migration.name, migration.checksum, clock.now()],
                )
            applied.append(migration.version)
        except BaseException as exc:
            # 前面已提交的文件也必须还原；先关闭所有连接，避免旧 WAL 重放。
            db._close_handles()
            try:
                if backup_path is not None:
                    _restore_file(backup_path, db.path)
                else:
                    for path in db._created_files:
                        path.unlink(missing_ok=True)
            except OSError as restore_exc:
                raise InternalError(
                    detail=(
                        f"restore failed: {migration.sql_path.name}, statement {ordinal}; "
                        f"backup={backup_path}"
                    )
                ) from restore_exc
            raise InternalError(
                detail=f"migration failed: {migration.sql_path.name}, statement {ordinal}"
            ) from exc
    db._new_file = False
    return MigrationReport(tuple(applied), db.schema_version, backup_path)

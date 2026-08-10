from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class DatabaseIntegrityError(RuntimeError):
    """The peripheral database failed an integrity gate."""


class DatabaseMigrationError(RuntimeError):
    """A versioned database migration could not be applied."""


class Database:
    def __init__(self, path: Path, migrations_dir: Path) -> None:
        self.path = path.resolve()
        self.migrations_dir = migrations_dir.resolve()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed_before = self.path.exists()
        with self._connection() as connection:
            pending = self._pending_migrations(connection)
            if existed_before and pending:
                self._write_backup(connection)
            for version, name, migration_path in pending:
                self._apply_migration(connection, version, name, migration_path)
            self._require_integrity(connection)

    @contextmanager
    def read_connection(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            yield connection

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA journal_mode=WAL")
            yield connection
        finally:
            connection.close()

    def _pending_migrations(
        self,
        connection: sqlite3.Connection,
    ) -> list[tuple[int, str, Path]]:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        applied: set[int] = set()
        if table_exists is not None:
            applied = {
                int(row[0])
                for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
            }

        migrations: list[tuple[int, str, Path]] = []
        for migration_path in sorted(self.migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            prefix, separator, remainder = migration_path.stem.partition("_")
            if not separator or not prefix.isdigit():
                continue
            version = int(prefix)
            if version not in applied:
                migrations.append((version, remainder, migration_path))
        return migrations

    def _write_backup(self, source: sqlite3.Connection) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = self.path.with_name(
            f"{self.path.name}.pre-migration-{timestamp}.bak"
        )
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
        return backup_path

    def _apply_migration(
        self,
        connection: sqlite3.Connection,
        version: int,
        name: str,
        migration_path: Path,
    ) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in _sql_statements(migration_path.read_text(encoding="utf-8")):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, _utc_text(datetime.now(UTC))),
            )
        except Exception as error:
            connection.rollback()
            raise DatabaseMigrationError(
                f"failed to apply migration {migration_path.name}"
            ) from error
        else:
            connection.commit()

    @staticmethod
    def _require_integrity(connection: sqlite3.Connection) -> None:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()
        if quick_check is None or quick_check[0] != "ok":
            raise DatabaseIntegrityError("database quick_check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise DatabaseIntegrityError("database foreign_key_check failed")


def _sql_statements(script: str) -> Iterator[str]:
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                yield statement
            buffer = ""
    if buffer.strip():
        raise DatabaseMigrationError("migration contains an incomplete SQL statement")


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

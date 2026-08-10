from __future__ import annotations

from pathlib import Path

from peripheral_host.database import Database


def test_initialize_enables_wal_foreign_keys_and_integrity(database: Database):
    with database.read_connection() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_initialize_is_idempotent(tmp_path: Path, migrations_dir: Path):
    database = Database(tmp_path / "peripheral.db", migrations_dir)

    database.initialize()
    database.initialize()

    with database.read_connection() as connection:
        applied = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert [tuple(row) for row in applied] == [(1, "s0_core")]

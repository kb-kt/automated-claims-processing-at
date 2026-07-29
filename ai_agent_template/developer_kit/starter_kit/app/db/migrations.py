from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path


class MigrationRunner:
    """Minimal SQLite migration runner.

    It keeps `schema.sql` as a full schema snapshot while applying ordered
    `db/migrations/*.sql` files as the executable change history.
    """

    def __init__(
        self,
        *,
        db_path: str | Path,
        migrations_dir: str | Path,
        schema_path: str | Path,
    ):
        self.db_path = Path(db_path)
        self.migrations_dir = Path(migrations_dir)
        self.schema_path = Path(schema_path)

    def apply(self) -> list[str]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            self._ensure_migration_table(connection)
            applied: list[str] = []
            migrations = self._discover_migrations()
            if migrations:
                for migration in migrations:
                    if self._is_applied(connection, migration.version):
                        continue
                    connection.executescript(migration.path.read_text(encoding="utf-8"))
                    connection.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                        (migration.version,),
                    )
                    applied.append(migration.version)
            else:
                connection.executescript(self.schema_path.read_text(encoding="utf-8"))
            connection.commit()
            return applied

    def applied_versions(self) -> list[str]:
        if not self.db_path.exists():
            return []
        with closing(sqlite3.connect(self.db_path)) as connection:
            self._ensure_migration_table(connection)
            rows = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        return [row[0] for row in rows]

    def _discover_migrations(self) -> list[Migration]:
        if not self.migrations_dir.exists():
            return []
        return [
            Migration(version=path.stem, path=path)
            for path in sorted(self.migrations_dir.glob("*.sql"))
        ]

    @staticmethod
    def _ensure_migration_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version TEXT PRIMARY KEY,
              applied_at TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def _is_applied(connection: sqlite3.Connection, version: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (version,),
        ).fetchone()
        return row is not None


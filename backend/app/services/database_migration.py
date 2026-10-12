import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import calls_table, contacts_table, metadata, settings_table


MIGRATION_TABLES = {
    "contacts": contacts_table,
    "settings": settings_table,
    "calls": calls_table,
}
APPEND_ONLY_TABLES = ("contacts", "calls")


def _read_sqlite_rows(source_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source database not found: {source_path}")

    rows: dict[str, list[dict[str, Any]]] = {}
    with closing(sqlite3.connect(source_path)) as source:
        source.row_factory = sqlite3.Row
        for table_name in MIGRATION_TABLES:
            table_rows = source.execute(f"SELECT * FROM {table_name}").fetchall()
            rows[table_name] = [dict(row) for row in table_rows]
    return rows


def _normalize_timestamps(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        value = row.get("created_at")
        if isinstance(value, str):
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            row["created_at"] = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)


def migrate_sqlite_to_engine(source_path: Path, target_engine: Engine) -> dict[str, int]:
    source_path = source_path.resolve()
    rows = _read_sqlite_rows(source_path)
    for table_name in ("contacts", "calls"):
        _normalize_timestamps(rows[table_name])

    metadata.create_all(target_engine)
    counts = {name: len(table_rows) for name, table_rows in rows.items()}
    with target_engine.begin() as target:
        for table_name in APPEND_ONLY_TABLES:
            existing_count = target.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")
            ).scalar_one()
            if existing_count:
                raise ValueError("Target contacts and calls tables must be empty before migration.")

        settings = rows["settings"]
        if settings:
            existing_settings = target.execute(
                text("SELECT id FROM settings WHERE id = 1")
            ).first()
            if existing_settings:
                target.execute(
                    text("UPDATE settings SET value = :value WHERE id = 1"),
                    {"value": settings[0]["value"]},
                )
            else:
                target.execute(settings_table.insert(), settings)

        for table_name in APPEND_ONLY_TABLES:
            table_rows = rows[table_name]
            if table_rows:
                target.execute(MIGRATION_TABLES[table_name].insert(), table_rows)

        if target_engine.dialect.name == "postgresql":
            for table_name in APPEND_ONLY_TABLES:
                if rows[table_name]:
                    target.execute(
                        text(
                            "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), :max_id, true)"
                        ),
                        {
                            "table_name": table_name,
                            "max_id": max(row["id"] for row in rows[table_name]),
                        },
                    )

    return counts
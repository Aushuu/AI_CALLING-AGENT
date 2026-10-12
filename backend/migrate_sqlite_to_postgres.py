import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine

from app.database import DATABASE_PATH, normalize_database_url
from app.services.database_migration import migrate_sqlite_to_engine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy Calling Agent SQLite settings, contacts, and calls into PostgreSQL."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DATABASE_PATH,
        help="SQLite database path (defaults to DATABASE_PATH).",
    )
    args = parser.parse_args()

    database_url = normalize_database_url(os.getenv("DATABASE_URL"))
    if not database_url:
        parser.error("Set DATABASE_URL to the managed PostgreSQL connection URL first.")

    target_engine = create_engine(database_url, pool_pre_ping=True)
    try:
        counts = migrate_sqlite_to_engine(args.source, target_engine)
    except (FileNotFoundError, ValueError):
        parser.exit(1, "Migration stopped. Check the source file and ensure target contacts/calls are empty.\n")
    except Exception:
        parser.exit(1, "Migration failed. Check DATABASE_URL, database connectivity, and the source schema.\n")
    finally:
        target_engine.dispose()

    print(
        "Migration complete: "
        f"{counts['settings']} settings row(s), "
        f"{counts['contacts']} contact(s), "
        f"{counts['calls']} call(s)."
    )


if __name__ == "__main__":
    main()
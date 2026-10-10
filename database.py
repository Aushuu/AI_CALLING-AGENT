"""SQLite persistence for simulated calls."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DEFAULT_DATABASE_PATH = Path(__file__).with_name("call_agent.db")
VALID_CLASSIFICATIONS = {"Important", "Spam", "General Inquiry"}
VALID_CONTACT_RULES = {"screen", "always_transfer", "always_handle"}
DEFAULT_SETTINGS = {
    "manual_active": True,
    "schedule_enabled": False,
    "timezone": "UTC",
    "schedule_days": [0, 1, 2, 3, 4],
    "schedule_start": "09:00",
    "schedule_end": "17:00",
    "transfer_number": "",
    "preferences": "",
}


def _database_path() -> Path:
    configured_path = os.getenv("CALL_AGENT_DB_PATH")
    return Path(configured_path).expanduser() if configured_path else DEFAULT_DATABASE_PATH


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db() -> None:
    """Create and gently migrate the call-agent tables."""
    with _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT NOT NULL UNIQUE,
                caller_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                transcript TEXT NOT NULL,
                classification TEXT NOT NULL CHECK (
                    classification IN ('Important', 'Spam', 'General Inquiry')
                ),
                summary TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL CHECK (duration_seconds >= 0),
                decision TEXT NOT NULL DEFAULT 'Handle' CHECK (decision IN ('Handle', 'Transfer', 'Review')),
                risk_level TEXT NOT NULL DEFAULT 'Medium' CHECK (risk_level IN ('Low', 'Medium', 'High')),
                caller_name TEXT NOT NULL DEFAULT '',
                decision_reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(call_logs)").fetchall()
        }
        migrations = {
            "decision": "TEXT NOT NULL DEFAULT 'Handle'",
            "risk_level": "TEXT NOT NULL DEFAULT 'Medium'",
            "caller_name": "TEXT NOT NULL DEFAULT ''",
            "decision_reason": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in migrations.items():
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE call_logs ADD COLUMN {column} {definition}")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                phone_key TEXT PRIMARY KEY,
                phone_number TEXT NOT NULL,
                name TEXT NOT NULL,
                rule TEXT NOT NULL CHECK (rule IN ('screen', 'always_transfer', 'always_handle')),
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                settings_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO agent_settings (id, settings_json) VALUES (1, ?)",
            (json.dumps(DEFAULT_SETTINGS),),
        )


def get_settings() -> dict[str, Any]:
    with _connection() as connection:
        row = connection.execute(
            "SELECT settings_json FROM agent_settings WHERE id = 1"
        ).fetchone()
    if row is None:
        return dict(DEFAULT_SETTINGS)
    try:
        settings = json.loads(row["settings_json"])
    except (TypeError, json.JSONDecodeError):
        settings = {}
    return {**DEFAULT_SETTINGS, **settings}


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = {**DEFAULT_SETTINGS, **settings}
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO agent_settings (id, settings_json) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET settings_json = excluded.settings_json
            """,
            (json.dumps(normalized, ensure_ascii=False),),
        )
    return normalized


def normalize_phone(phone_number: str) -> str:
    digits = re.sub(r"\D", "", phone_number)
    return digits[-10:] if len(digits) > 10 else digits


def get_contact(phone_number: str) -> dict[str, Any] | None:
    phone_key = normalize_phone(phone_number)
    if not phone_key:
        return None
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM contacts WHERE phone_key = ?", (phone_key,)
        ).fetchone()
    return dict(row) if row else None


def get_contacts() -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM contacts ORDER BY name COLLATE NOCASE, phone_number"
        ).fetchall()
    return [dict(row) for row in rows]


def save_contact(*, phone_number: str, name: str, rule: str, notes: str = "") -> dict[str, Any]:
    phone_key = normalize_phone(phone_number)
    if len(phone_key) < 7:
        raise ValueError("Enter a phone number with at least seven digits")
    if not name.strip() or len(name.strip()) > 100:
        raise ValueError("Contact name must contain between 1 and 100 characters")
    if rule not in VALID_CONTACT_RULES:
        raise ValueError("Invalid contact screening rule")
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO contacts (phone_key, phone_number, name, rule, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(phone_key) DO UPDATE SET
                phone_number = excluded.phone_number,
                name = excluded.name,
                rule = excluded.rule,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (phone_key, phone_number.strip()[:40], name.strip(), rule, notes.strip()[:500], timestamp),
        )
        row = connection.execute(
            "SELECT * FROM contacts WHERE phone_key = ?", (phone_key,)
        ).fetchone()
    if row is None:
        raise RuntimeError("Saved contact could not be read back")
    return dict(row)


def delete_contact(phone_number: str) -> bool:
    phone_key = normalize_phone(phone_number)
    with _connection() as connection:
        cursor = connection.execute("DELETE FROM contacts WHERE phone_key = ?", (phone_key,))
    return cursor.rowcount > 0


def save_call(
    *,
    call_id: str,
    caller_id: str,
    transcript: list[dict[str, str]],
    classification: str,
    summary: str,
    duration_seconds: int,
    decision: str = "Handle",
    risk_level: str = "Medium",
    caller_name: str = "",
    decision_reason: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Insert or update one call, keyed by its client-generated UUID."""
    if classification not in VALID_CLASSIFICATIONS:
        raise ValueError("Invalid call classification")
    if decision not in {"Handle", "Transfer", "Review"}:
        raise ValueError("Invalid call decision")
    if risk_level not in {"Low", "Medium", "High"}:
        raise ValueError("Invalid risk level")
    if not call_id.strip() or not caller_id.strip():
        raise ValueError("Call ID and caller ID are required")
    normalized_duration = max(0, int(duration_seconds))
    normalized_timestamp = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")
    encoded_transcript = json.dumps(transcript, ensure_ascii=False)

    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO call_logs (
                call_id, caller_id, timestamp, transcript, classification, summary, duration_seconds,
                decision, risk_level, caller_name, decision_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(call_id) DO UPDATE SET
                caller_id = excluded.caller_id,
                timestamp = excluded.timestamp,
                transcript = excluded.transcript,
                classification = excluded.classification,
                summary = excluded.summary,
                duration_seconds = excluded.duration_seconds,
                decision = excluded.decision,
                risk_level = excluded.risk_level,
                caller_name = excluded.caller_name,
                decision_reason = excluded.decision_reason
            """,
            (
                call_id.strip(),
                caller_id.strip()[:80],
                normalized_timestamp,
                encoded_transcript,
                classification,
                summary.strip()[:500],
                normalized_duration,
                decision,
                risk_level,
                caller_name.strip()[:100],
                decision_reason.strip()[:300],
            ),
        )
        row = connection.execute(
            "SELECT * FROM call_logs WHERE call_id = ?", (call_id.strip(),)
        ).fetchone()
    return _row_to_dict(row)


def get_logs(limit: int = 100) -> list[dict[str, Any]]:
    """Return newest call records first."""
    bounded_limit = min(max(int(limit), 1), 500)
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM call_logs ORDER BY timestamp DESC, id DESC LIMIT ?",
            (bounded_limit,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        raise RuntimeError("Saved call could not be read back")
    result = dict(row)
    try:
        result["transcript"] = json.loads(result["transcript"])
    except (TypeError, json.JSONDecodeError):
        result["transcript"] = []
    return result
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    URL,
    create_engine,
    func,
    inspect,
    text,
)
from sqlalchemy.engine import Connection, Engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", PROJECT_ROOT / "backend" / "data" / "call_agent.db"))
DATABASE_URL = os.getenv("DATABASE_URL")
WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
DEFAULT_SETTINGS: dict[str, Any] = {
    "manual_enabled": True,
    "schedule_enabled": False,
    "schedule_start": "09:00",
    "schedule_end": "17:00",
    "schedule_days": WEEKDAY_NAMES.copy(),
    "timezone": "UTC",
    "owner_phone": "",
}


def normalize_database_url(database_url: str | None) -> str | None:
    if database_url and database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url and database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def create_database_engine(database_url: str | None, database_path: Path) -> Engine:
    normalized_url = normalize_database_url(database_url)
    if normalized_url:
        return create_engine(normalized_url, pool_pre_ping=True)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    sqlite_url = URL.create("sqlite", database=str(database_path))
    return create_engine(sqlite_url, connect_args={"check_same_thread": False})


engine = create_database_engine(DATABASE_URL, DATABASE_PATH)
metadata = MetaData()

contacts_table = Table(
    "contacts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(80), nullable=False),
    Column("phone", String(16), nullable=False, unique=True),
    Column("rule", String(32), nullable=False, server_default="always_screen"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

settings_table = Table(
    "settings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("value", Text, nullable=False),
    CheckConstraint("id = 1", name="settings_singleton_id"),
)

calls_table = Table(
    "calls",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("call_sid", String(64), unique=True),
    Column("caller_phone", String(32), nullable=False),
    Column("caller_name", String(80), nullable=False),
    Column("caller_known", Integer, nullable=False),
    Column("transcript", Text, nullable=False),
    Column("intent", String(64), nullable=False),
    Column("urgency", String(32), nullable=False),
    Column("risk", String(32), nullable=False),
    Column("risk_reasons", Text, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("action", String(32), nullable=False),
    Column("summary", Text, nullable=False),
    Column("provider", String(64), nullable=False),
    Column("simulated", Integer, nullable=False, server_default="1"),
    Column("call_status", String(32), nullable=False, server_default="unknown"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

push_subscriptions_table = Table(
    "push_subscriptions",
    metadata,
    Column("endpoint", String(2048), primary_key=True),
    Column("p256dh", String(256), nullable=False),
    Column("auth", String(256), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

push_delivery_claims_table = Table(
    "push_delivery_claims",
    metadata,
    Column("call_sid", String(64), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


@contextmanager
def connect() -> Iterator[Connection]:
    with engine.begin() as connection:
        yield connection


def database_backend() -> str:
    return engine.dialect.name


def validate_database_configuration(database_url: str | None, is_render: bool) -> None:
    if is_render and not database_url:
        raise RuntimeError("DATABASE_URL must point to persistent PostgreSQL storage on Render.")


def initialize_database() -> None:
    validate_database_configuration(DATABASE_URL, bool(os.getenv("RENDER")))
    metadata.create_all(engine)
    call_columns = {column["name"] for column in inspect(engine).get_columns("calls")}
    if "call_status" not in call_columns:
        with connect() as connection:
            connection.execute(
                text(
                    "ALTER TABLE calls ADD COLUMN call_status "
                    "VARCHAR(32) NOT NULL DEFAULT 'unknown'"
                )
            )
    with connect() as connection:
        connection.execute(
            text(
                "INSERT INTO settings (id, value) VALUES (1, :value) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"value": json.dumps(DEFAULT_SETTINGS)},
        )


def get_settings() -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute(text("SELECT value FROM settings WHERE id = 1")).mappings().first()
    return {**DEFAULT_SETTINGS, **json.loads(row["value"])} if row else DEFAULT_SETTINGS.copy()


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    settings = {**get_settings(), **updates}
    with connect() as connection:
        connection.execute(
            text(
                "INSERT INTO settings (id, value) VALUES (1, :value) "
                "ON CONFLICT (id) DO UPDATE SET value = excluded.value"
            ),
            {"value": json.dumps(settings)},
        )
    return settings


def list_contacts() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            text("SELECT id, name, phone, rule, created_at FROM contacts ORDER BY lower(name)")
        ).mappings().all()
    return [dict(row) for row in rows]


def find_contact(phone: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            text("SELECT id, name, phone, rule, created_at FROM contacts WHERE phone = :phone"),
            {"phone": phone},
        ).mappings().first()
    return dict(row) if row else None


def add_contact(name: str, phone: str, rule: str) -> dict[str, Any]:
    with connect() as connection:
        connection.execute(
            text("INSERT INTO contacts (name, phone, rule) VALUES (:name, :phone, :rule)"),
            {"name": name, "phone": phone, "rule": rule},
        )
        row = connection.execute(
            text("SELECT id, name, phone, rule, created_at FROM contacts WHERE phone = :phone"),
            {"phone": phone},
        ).mappings().one()
    return dict(row)


def delete_contact(contact_id: int) -> bool:
    with connect() as connection:
        result = connection.execute(
            text("DELETE FROM contacts WHERE id = :contact_id"), {"contact_id": contact_id}
        )
    return result.rowcount > 0


def save_call(call: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "call_sid", "caller_phone", "caller_name", "caller_known", "transcript", "intent",
        "urgency", "risk", "risk_reasons", "confidence", "action", "summary", "provider",
        "simulated", "call_status",
    )
    values = {field: call.get(field) for field in fields}
    values["caller_known"] = int(bool(values["caller_known"]))
    values["risk_reasons"] = json.dumps(values["risk_reasons"])
    values["simulated"] = int(bool(values["simulated"]))
    values["call_status"] = call.get("call_status") or (
        "simulated" if values["simulated"] else "in-progress"
    )
    columns = ", ".join(fields)
    parameters = ", ".join(f":{field}" for field in fields)
    updates = ", ".join(
        f"{field} = excluded.{field}"
        for field in fields
        if field not in {"call_sid", "call_status"}
    )
    with connect() as connection:
        inserted = connection.execute(
            text(
                f"INSERT INTO calls ({columns}) VALUES ({parameters}) "
                f"ON CONFLICT (call_sid) DO UPDATE SET {updates} RETURNING id"
            ),
            values,
        )
        call_id = inserted.scalar_one()
        row = connection.execute(
            text("SELECT * FROM calls WHERE id = :call_id"), {"call_id": call_id}
        ).mappings().one()
    return call_from_row(row)


def list_calls(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            text("SELECT * FROM calls ORDER BY id DESC LIMIT :limit"), {"limit": limit}
        ).mappings().all()
    return [call_from_row(row) for row in rows]


def save_push_subscription(endpoint: str, p256dh: str, auth: str) -> None:
    with connect() as connection:
        connection.execute(
            text(
                "INSERT INTO push_subscriptions (endpoint, p256dh, auth) "
                "VALUES (:endpoint, :p256dh, :auth) "
                "ON CONFLICT (endpoint) DO UPDATE SET p256dh = excluded.p256dh, auth = excluded.auth"
            ),
            {"endpoint": endpoint, "p256dh": p256dh, "auth": auth},
        )


def list_push_subscriptions() -> list[dict[str, str]]:
    with connect() as connection:
        rows = connection.execute(
            text("SELECT endpoint, p256dh, auth FROM push_subscriptions")
        ).mappings().all()
    return [dict(row) for row in rows]


def claim_call_notification(call_sid: str) -> bool:
    with connect() as connection:
        result = connection.execute(
            text(
                "INSERT INTO push_delivery_claims (call_sid) VALUES (:call_sid) "
                "ON CONFLICT (call_sid) DO NOTHING RETURNING call_sid"
            ),
            {"call_sid": call_sid},
        )
        return result.scalar_one_or_none() is not None


def delete_push_subscription(endpoint: str) -> None:
    with connect() as connection:
        connection.execute(
            text("DELETE FROM push_subscriptions WHERE endpoint = :endpoint"),
            {"endpoint": endpoint},
        )


def find_call_by_sid(call_sid: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            text("SELECT * FROM calls WHERE call_sid = :call_sid"), {"call_sid": call_sid}
        ).mappings().first()
    return call_from_row(row) if row else None


def update_call_transcript(call_sid: str, transcript: str) -> None:
    with connect() as connection:
        result = connection.execute(
            text("UPDATE calls SET transcript = :transcript WHERE call_sid = :call_sid"),
            {"call_sid": call_sid, "transcript": transcript},
        )
    if result.rowcount != 1:
        raise RuntimeError("The call transcript could not be updated.")


CALL_STATUS_ORDER = {
    "unknown": -1,
    "queued": 0,
    "ringing": 1,
    "in-progress": 2,
    "completed": 3,
    "busy": 3,
    "failed": 3,
    "no-answer": 3,
    "canceled": 3,
}
TERMINAL_CALL_STATUSES = {
    "completed",
    "busy",
    "failed",
    "no-answer",
    "canceled",
}


def update_call_status(call_sid: str, call_status: str) -> bool:
    if call_status not in CALL_STATUS_ORDER:
        raise ValueError("Unsupported Twilio call status.")

    with connect() as connection:
        row = connection.execute(
            text("SELECT call_status FROM calls WHERE call_sid = :call_sid"),
            {"call_sid": call_sid},
        ).mappings().first()
        if row is None:
            return False

        current_status = row["call_status"]
        if current_status in TERMINAL_CALL_STATUSES:
            return True
        if CALL_STATUS_ORDER[call_status] < CALL_STATUS_ORDER.get(current_status, -1):
            return True

        connection.execute(
            text("UPDATE calls SET call_status = :call_status WHERE call_sid = :call_sid"),
            {"call_sid": call_sid, "call_status": call_status},
        )
    return True


def call_from_row(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["caller_known"] = bool(item["caller_known"])
    item["simulated"] = bool(item["simulated"])
    if isinstance(item["risk_reasons"], str):
        item["risk_reasons"] = json.loads(item["risk_reasons"])
    return item

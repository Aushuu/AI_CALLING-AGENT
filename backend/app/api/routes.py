import re
import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError

from app.database import (
    add_contact,
    database_backend,
    delete_contact,
    delete_push_subscription,
    find_contact,
    WEEKDAY_NAMES,
    find_call_by_sid,
    get_settings,
    list_calls,
    list_contacts,
    save_call,
    save_push_subscription,
    save_settings,
)
from app.services.agent import RISK_LEVEL, is_agent_available, process_call
from app.services.analysis import analyze_call
from app.services.auth import auth_configured, auth_required, issue_access_token, require_owner
from app.services.gemini import classify_with_gemini, generate_demo_reply


router = APIRouter(prefix="/api")


def normalize_schedule_days(value: list[str] | str | None) -> list[str]:
    if value is None:
        return WEEKDAY_NAMES.copy()
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",") if part.strip()]
    else:
        values = [str(part).strip() for part in value if str(part).strip()]

    normalized = []
    for item in values:
        match = re.sub(r"[^A-Za-z]", "", item).title()
        if match in WEEKDAY_NAMES:
            normalized.append(match)
    if not normalized:
        return []

    unique = []
    seen: set[str] = set()
    for day in normalized:
        if day not in seen:
            unique.append(day)
            seen.add(day)
    return unique


def normalize_phone(value: str) -> str:
    value = value.strip()
    prefix = "+" if value.startswith("+") else ""
    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15:
        raise ValueError("Enter a phone number with 7 to 15 digits.")
    return prefix + digits


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_enabled: bool
    schedule_enabled: bool
    schedule_days: list[str] = Field(default_factory=lambda: WEEKDAY_NAMES.copy())
    schedule_start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    schedule_end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str
    owner_phone: str = ""

    @field_validator("schedule_days")
    @classmethod
    def validate_schedule_days(cls, value: list[str]) -> list[str]:
        return normalize_schedule_days(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Choose a valid IANA timezone.") from error
        return value

    @field_validator("owner_phone")
    @classmethod
    def validate_owner_phone(cls, value: str) -> str:
        return normalize_phone(value) if value.strip() else ""


class ContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    phone: str
    rule: Literal["always_screen", "always_message", "always_transfer", "delivery_agent", "block_reject"] = "always_screen"

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("phone")
    @classmethod
    def normalize_contact_phone(cls, value: str) -> str:
        return normalize_phone(value)


class SimulateCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caller_phone: str
    transcript: str = Field(max_length=1200)

    @field_validator("caller_phone")
    @classmethod
    def normalize_caller_phone(cls, value: str) -> str:
        return normalize_phone(value)


class OwnerLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class DemoCallStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caller_phone: str = "+15550000000"
    caller_name: str = "Demo caller"

    @field_validator("caller_name")
    @classmethod
    def trim_caller_name(cls, value: str) -> str:
        return value.strip() or "Demo caller"

    @field_validator("caller_phone")
    @classmethod
    def normalize_demo_phone(cls, value: str) -> str:
        return normalize_phone(value)


class DemoCallMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1500)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        return value.strip()


class PushSubscriptionKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: str = Field(min_length=1, max_length=256)
    auth: str = Field(min_length=1, max_length=256)


class PushSubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=1, max_length=2048)
    keys: PushSubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Push endpoint must be an HTTPS URL.")
        return value


class PushSubscriptionDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=1, max_length=2048)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Push endpoint must be an HTTPS URL.")
        return value


def append_demo_turn(transcript: str, speaker: str, message: str) -> str:
    cleaned = message.strip()
    if not cleaned:
        return transcript.strip()
    previous = transcript.strip()
    turn = f"{speaker}: {cleaned}"
    return f"{previous}\n{turn}" if previous else turn


def parse_demo_messages(transcript: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for line in transcript.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        speaker, text = line.split(":", 1)
        speaker = speaker.strip()
        text = text.strip()
        if not speaker or not text:
            continue
        messages.append({"speaker": speaker, "text": text})
    return messages


@router.get("/health")
def health() -> dict[str, object]:
    import os

    settings = get_settings()
    required_twilio_config = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
    missing_twilio_config = [name for name in required_twilio_config if not os.getenv(name)]
    inbound_phone_configured = bool(os.getenv("INBOUND_PHONE_NUMBER", "").strip())
    if not inbound_phone_configured:
        missing_twilio_config.append(
            "INBOUND_PHONE_NUMBER (Twilio Voice number or carrier DID)"
        )
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    parsed_public_base_url = urlparse(public_base_url)
    webhook_uses_public_https = (
        parsed_public_base_url.scheme == "https"
        and parsed_public_base_url.hostname is not None
        and parsed_public_base_url.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}
        and not parsed_public_base_url.hostname.lower().endswith(".localhost")
    )
    if not webhook_uses_public_https:
        missing_twilio_config.append("PUBLIC_BASE_URL (must be public HTTPS)")
    return {
        "status": "ok",
        "auth_required": auth_required(),
        "auth_configured": auth_configured(),
        "ai_enabled": bool(os.getenv("GEMINI_API_KEY")),
        "push_notifications_enabled": bool(
            os.getenv("VAPID_PUBLIC_KEY")
            and os.getenv("VAPID_PRIVATE_KEY")
            and os.getenv("VAPID_SUBJECT")
        ),
        "twilio_enabled": not missing_twilio_config,
        "twilio_missing_config": missing_twilio_config,
        "twilio_webhook_uses_public_https": webhook_uses_public_https,
        "inbound_phone_configured": inbound_phone_configured,
        "twilio_webhook_url": f"{public_base_url}/api/twilio/voice" if public_base_url else None,
        "agent_available": is_agent_available(settings),
        "storage": database_backend(),
    }


@router.get("/notifications/public-key")
def push_public_key() -> dict[str, object]:
    import os

    public_key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    configured = bool(public_key and os.getenv("VAPID_PRIVATE_KEY") and os.getenv("VAPID_SUBJECT"))
    return {"enabled": configured, "public_key": public_key or None}


@router.post("/notifications/subscriptions", status_code=201, dependencies=[Depends(require_owner)])
def subscribe_to_call_notifications(subscription: PushSubscriptionCreate) -> dict[str, bool]:
    save_push_subscription(
        subscription.endpoint,
        subscription.keys.p256dh,
        subscription.keys.auth,
    )
    return {"saved": True}


@router.delete("/notifications/subscriptions", status_code=204, dependencies=[Depends(require_owner)])
def unsubscribe_from_call_notifications(subscription: PushSubscriptionDelete) -> None:
    delete_push_subscription(subscription.endpoint)


@router.post("/auth/login")
def owner_login(credentials: OwnerLogin) -> dict[str, str | int]:
    return issue_access_token(credentials.username, credentials.password)


@router.get("/settings", dependencies=[Depends(require_owner)])
def read_settings() -> dict[str, object]:
    return get_settings()


@router.put("/settings", dependencies=[Depends(require_owner)])
def update_settings(settings: SettingsUpdate) -> dict[str, object]:
    return save_settings(settings.model_dump())


@router.get("/contacts", dependencies=[Depends(require_owner)])
def read_contacts() -> list[dict[str, object]]:
    return list_contacts()


@router.post("/contacts", status_code=201, dependencies=[Depends(require_owner)])
def create_contact(contact: ContactCreate) -> dict[str, object]:
    try:
        return add_contact(contact.name, contact.phone, contact.rule)
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="That phone number is already saved.") from error


@router.delete("/contacts/{contact_id}", status_code=204, dependencies=[Depends(require_owner)])
def remove_contact(contact_id: int) -> None:
    if not delete_contact(contact_id):
        raise HTTPException(status_code=404, detail="Contact not found.")


@router.post("/calls/simulate", status_code=201, dependencies=[Depends(require_owner)])
def simulate_call(call: SimulateCall) -> dict[str, object]:
    return process_call(call.caller_phone, call.transcript, simulated=True)


@router.post("/demo/calls", status_code=201, dependencies=[Depends(require_owner)])
def start_demo_call(call: DemoCallStart) -> dict[str, object]:
    session_id = f"demo-{uuid.uuid4().hex[:12]}"
    contact = find_contact(call.caller_phone)
    caller_known = contact is not None
    caller_name = contact["name"] if contact else call.caller_name
    transcript = f"Caller: Hello, I am calling the account owner."
    response = generate_demo_reply(transcript, caller_name)
    initial_analysis = analyze_call(
        transcript,
        caller_known=caller_known,
        contact_rule=contact["rule"] if contact else None,
        owner_phone=None,
    )
    saved = save_call({
        "call_sid": session_id,
        "caller_phone": call.caller_phone,
        "caller_name": caller_name,
        "caller_known": caller_known,
        "transcript": transcript,
        "intent": initial_analysis.get("intent", "general"),
        "urgency": initial_analysis.get("urgency", "low"),
        "risk": initial_analysis.get("risk", "low"),
        "risk_reasons": initial_analysis.get("risk_reasons", []),
        "confidence": initial_analysis.get("confidence", 0.8),
        "action": initial_analysis.get("action", "take_message"),
        "summary": "Demo session started with screening assistant.",
        "provider": "demo",
        "simulated": True,
        "call_status": "simulated",
    })
    return {
        **saved,
        "session_id": session_id,
        "transcript": transcript,
        "agent_reply": response,
        "demo_mode": True,
        "status": "simulated",
        "inferred_caller": initial_analysis.get("inferred_caller"),
        "identity_note": initial_analysis.get("identity_note"),
    }


@router.post("/demo/calls/{session_id}/message", dependencies=[Depends(require_owner)])
def send_demo_message(session_id: str, payload: DemoCallMessage) -> dict[str, object]:
    call = find_call_by_sid(session_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Demo session not found.")

    transcript = append_demo_turn(call["transcript"], "Caller", payload.message)
    reply = generate_demo_reply(transcript, call["caller_name"])
    transcript = append_demo_turn(transcript, "Agent", reply)

    settings = get_settings()
    contact = find_contact(call["caller_phone"])
    caller_known = contact is not None

    analysis = analyze_call(
        transcript,
        caller_known=caller_known,
        contact_rule=contact["rule"] if contact else None,
        owner_phone=settings.get("owner_phone"),
    )
    ai_result = classify_with_gemini(transcript, caller_known)
    if ai_result:
        analysis["intent"] = ai_result["intent"]
        analysis["urgency"] = ai_result["urgency"]
        analysis["confidence"] = ai_result["confidence"]
        if ai_result.get("inferred_caller"):
            analysis["inferred_caller"] = ai_result["inferred_caller"]
        if ai_result.get("inferred_organization"):
            analysis["inferred_organization"] = ai_result["inferred_organization"]
        if RISK_LEVEL.get(ai_result["risk"], 0) > RISK_LEVEL.get(analysis["risk"], 0):
            analysis["risk"] = ai_result["risk"]
            analysis["risk_reasons"] = ai_result["risk_reasons"] or analysis["risk_reasons"]

    # Determine caller name (using inferred if unknown)
    caller_name = call["caller_name"]
    if not caller_known and analysis.get("inferred_caller"):
        caller_name = f"{analysis['inferred_caller']} (Unverified)"

    updated = save_call({
        **call,
        "caller_name": caller_name,
        "caller_known": caller_known,
        "transcript": transcript[-4000:],
        "intent": analysis["intent"],
        "urgency": analysis["urgency"],
        "risk": analysis["risk"],
        "risk_reasons": analysis["risk_reasons"],
        "confidence": analysis["confidence"],
        "action": analysis["action"],
        "summary": analysis["summary"],
        "call_status": "simulated",
    })
    return {
        **updated,
        "session_id": session_id,
        "transcript": transcript,
        "agent_reply": reply,
        "demo_mode": True,
        "status": "simulated",
        "inferred_caller": analysis.get("inferred_caller"),
        "identity_note": analysis.get("identity_note"),
    }


@router.get("/calls", dependencies=[Depends(require_owner)])
def read_calls(limit: int = 30) -> list[dict[str, object]]:
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100.")
    return list_calls(limit)

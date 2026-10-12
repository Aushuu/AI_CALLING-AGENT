from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.database import WEEKDAY_NAMES, find_contact, get_settings, save_call
from app.services.analysis import analyze_call
from app.services.gemini import classify_with_gemini


RISK_LEVEL = {"low": 0, "unknown": 1, "spam": 2, "suspicious": 3, "possible_scam": 4}


def is_agent_available(settings: dict[str, Any], now: datetime | None = None) -> bool:
    if settings["manual_enabled"]:
        return True
    if not settings["schedule_enabled"]:
        return False

    schedule_days = settings.get("schedule_days")
    if schedule_days is None:
        schedule_days = WEEKDAY_NAMES.copy()
    if isinstance(schedule_days, str):
        schedule_days = [schedule_days]
    if not schedule_days:
        return False

    try:
        timezone = ZoneInfo(settings["timezone"])
        if now is None:
            local_now = datetime.now(timezone)
        elif now.tzinfo is None:
            local_now = now.replace(tzinfo=timezone)
        else:
            local_now = now.astimezone(timezone)
        current_day = local_now.strftime("%A")
        current = local_now.strftime("%H:%M")
    except (ZoneInfoNotFoundError, ValueError):
        return False

    start, end = settings["schedule_start"], settings["schedule_end"]
    if start < end:
        return current_day in schedule_days and start <= current < end
    if start > end and current < end:
        previous_day = WEEKDAY_NAMES[(WEEKDAY_NAMES.index(current_day) - 1) % len(WEEKDAY_NAMES)]
        return previous_day in schedule_days
    return current_day in schedule_days


def process_call(
    caller_phone: str,
    transcript: str,
    call_sid: str | None = None,
    simulated: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    contact = find_contact(caller_phone)
    caller_name = contact["name"] if contact else "Unknown caller"
    if not is_agent_available(settings):
        decision = {
            "intent": "not_screened", "urgency": "low", "risk": "unknown",
            "risk_reasons": ["Agent mode is off and no active schedule applies."],
            "confidence": 1.0, "action": "agent_off",
            "reply": "The call assistant is currently unavailable.",
            "summary": "Call was not screened because agent mode is off.", "provider": "policy",
        }
    else:
        decision = analyze_call(
            transcript,
            caller_known=contact is not None,
            contact_rule=contact["rule"] if contact else None,
            owner_phone=settings["owner_phone"] or None,
        )
        ai_result = classify_with_gemini(transcript, contact is not None)
        if ai_result:
            decision["intent"] = ai_result["intent"]
            decision["urgency"] = ai_result["urgency"]
            decision["confidence"] = ai_result["confidence"]
            if ai_result.get("inferred_caller"):
                decision["inferred_caller"] = ai_result["inferred_caller"]
            if ai_result.get("inferred_organization"):
                decision["inferred_organization"] = ai_result["inferred_organization"]
            if RISK_LEVEL[ai_result["risk"]] > RISK_LEVEL[decision["risk"]]:
                decision["risk"] = ai_result["risk"]
                decision["risk_reasons"] = ai_result["risk_reasons"] or decision["risk_reasons"]
            decision["provider"] = "gemini"
            if decision["risk"] == "possible_scam":
                decision["action"] = "take_message"
                decision["reply"] = "I cannot help with sensitive codes or financial information. This call will be saved in the account owner's call history."
            elif decision["risk"] == "spam":
                decision["action"] = "take_message"
                decision["reply"] = "I cannot transfer an unsolicited sales call. This call will be saved in the account owner's call history."
            elif decision["risk"] == "suspicious":
                decision["action"] = "take_message"
                decision["reply"] = "I will not transfer a call involving suspicious pressure or sensitive information. This call will be saved in the account owner's call history."
            elif contact and contact["rule"] == "always_message":
                decision["action"] = "take_message"
            elif contact and contact["rule"] == "always_transfer" and settings["owner_phone"]:
                decision["action"] = "transfer"
            elif contact and contact["rule"] == "block_reject":
                decision["action"] = "take_message"
                decision["reply"] = "The account owner is currently unavailable to accept this call. Goodbye."
            elif contact and contact["rule"] == "delivery_agent" and decision["intent"] == "delivery":
                decision["action"] = "take_message"
                decision["reply"] = "For deliveries, please leave the package safely at the door or parcel box. Thank you."
            elif decision["confidence"] < 0.4:
                decision["action"] = "clarify"
            elif decision["urgency"] == "high" and settings["owner_phone"]:
                decision["action"] = "transfer"
            if decision["action"] == "transfer":
                decision["reply"] = "This sounds important. I will try to connect you now."
            elif decision["action"] == "clarify":
                decision["reply"] = "I am not certain I understood. Could you say that another way?"

        # If caller is unknown but self-identified in speech, display inferred name with uncertainty badge
        if not contact and decision.get("inferred_caller"):
            caller_name = f"{decision['inferred_caller']} (Unverified)"

    saved_call = save_call({
        "call_sid": call_sid,
        "caller_phone": caller_phone,
        "caller_name": caller_name,
        "caller_known": contact is not None,
        "transcript": transcript[:1200],
        **decision,
        "simulated": simulated,
    })
    return {
        **saved_call,
        "reply": decision["reply"],
        "inferred_caller": decision.get("inferred_caller"),
        "inferred_organization": decision.get("inferred_organization"),
        "identity_note": decision.get("identity_note"),
    }

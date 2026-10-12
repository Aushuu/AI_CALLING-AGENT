import re
from typing import Any


RISK_TERMS = {
    "possible_scam": (
        r"\b(one[- ]time|verification|security) code\b",
        r"\bpassword|passcode|otp\b",
        r"\b(gift card|wire transfer|crypto wallet|seed phrase)\b",
        r"\b(remote access|install this app|anydesk|teamviewer|quicksupport)\b",
    ),
    "suspicious": (
        r"\b(act now|immediately|urgent payment|arrest warrant|legal action)\b",
        r"\b(bank account|social security number|ssn|debit card|credit card pin)\b",
    ),
    "spam": (
        r"\b(robocall|telemarketing|cold call|unsolicited sales pitch)\b",
        r"\bautomated (warranty sales|warranty|sales|marketing) call\b",
        r"\b(pre[- ]approved loan|exclusive investment opportunity|debt relief)\b",
    ),
}

INTENT_TERMS = {
    "emergency": ("emergency", "urgent", "hospital", "accident", "ambulance", "help me"),
    "appointment": ("appointment", "schedule", "reschedule", "meeting", "doctor visit"),
    "delivery": ("delivery", "package", "parcel", "drop off", "courier", "shipment"),
    "work": ("interview", "work", "project", "client", "office", "colleague"),
    "sales": ("offer", "discount", "selling", "marketing", "insurance quote", "credit card offer"),
}


def infer_caller_identity(text: str) -> dict[str, str | None]:
    """Extract self-declared caller identity and organization from speech."""
    if not text:
        return {"inferred_caller": None, "inferred_organization": None}

    cleaned = text.strip()
    name_match = re.search(
        r"\b(?:this is|my name is|i am|i'm|it's)\s+((?:(?:Dr|Mr|Mrs|Ms)\.?\s+)?[A-Z][a-zA-Z\s]{1,30}?)(?:\s+(?:from|with|calling from|at)\s+([A-Z0-9a-zA-Z\s]{2,40}?))?(?=[,;?!]|\s+calling|\s+regarding|\.\s|$)",
        cleaned,
    )
    if name_match:
        name = name_match.group(1).strip().rstrip(".,")
        org = name_match.group(2).strip().rstrip(".,") if name_match.group(2) else None
        # Exclude common non-name phrases
        if name.lower() not in {"a", "an", "the", "calling", "just", "here", "waiting", "wondering", "reaching out"}:
            return {"inferred_caller": name, "inferred_organization": org}

    org_match = re.search(
        r"\b(?:calling from|calling on behalf of|with)\s+([A-Z0-9a-zA-Z\s]{2,40}?)(?=[,;?!]|\s+calling|\s+regarding|\.\s|$)",
        cleaned,
    )
    if org_match:
        return {"inferred_caller": None, "inferred_organization": org_match.group(1).strip().rstrip(".,")}

    return {"inferred_caller": None, "inferred_organization": None}


def analyze_call(
    transcript: str,
    caller_known: bool,
    contact_rule: str | None,
    owner_phone: str | None,
    confidence: float = 0.55,
) -> dict[str, Any]:
    """Produce a cautious baseline decision when a live AI key is unavailable."""
    text = re.sub(r"\s+", " ", transcript).strip()
    normalized = text.casefold()
    matched_intent = next(
        (
            intent
            for intent, terms in INTENT_TERMS.items()
            if any(term in normalized for term in terms)
        ),
        "general",
    )

    risk = "low"
    reasons: list[str] = []
    for label in ("possible_scam", "suspicious", "spam"):
        matches = [term for term in RISK_TERMS[label] if re.search(term, normalized)]
        if matches:
            risk = label
            reasons.append(
                "The caller mentioned a request associated with credential or payment scams."
                if label == "possible_scam"
                else "The caller used pressure or requested sensitive financial information."
                if label == "suspicious"
                else "The caller described an unsolicited or automated sales call."
            )
            break
    if not reasons:
        reasons.append("No high-risk phrase was detected; this is not proof the call is safe.")

    urgency = "high" if matched_intent == "emergency" else "medium" if matched_intent in {"appointment", "delivery"} else "low"
    if not text:
        return {
            "intent": "unclear",
            "urgency": "low",
            "risk": "unknown",
            "risk_reasons": ["No caller statement was received."],
            "confidence": 0.0,
            "action": "clarify",
            "reply": "I did not catch that. Could you briefly tell me why you are calling?",
            "summary": "Caller reason was not captured.",
            "provider": "rules",
            "inferred_caller": None,
            "inferred_organization": None,
            "identity_verified": False,
            "identity_note": "No statement received.",
        }

    inferred_id = infer_caller_identity(text)

    if contact_rule == "block_reject":
        action = "take_message"
    elif contact_rule == "always_transfer" and owner_phone and risk in {"low", "unknown"}:
        action = "transfer"
    elif contact_rule == "always_message" or risk in {"spam", "suspicious", "possible_scam"}:
        action = "take_message"
    elif matched_intent == "emergency" and owner_phone and risk in {"low", "unknown"}:
        action = "transfer"
    elif confidence < 0.4:
        action = "clarify"
    else:
        action = "take_message"

    caller_label = "a number matching a saved contact" if caller_known else "an unknown number"
    replies = {
        "transfer": "This sounds important. I will try to connect you now.",
        "clarify": "I am not certain I understood. Could you say that another way?",
        "take_message": "Thank you. I will save what you shared in the call history for the account owner to review.",
    }
    if contact_rule == "block_reject":
        replies["take_message"] = "The account owner is currently unavailable to accept this call. Goodbye."
    elif contact_rule == "delivery_agent" and matched_intent == "delivery":
        replies["take_message"] = "For deliveries, please leave the package safely at the door or parcel box. Thank you."
    elif risk == "spam":
        replies["take_message"] = "I cannot transfer an unsolicited sales call. This call will be saved in the account owner's call history."
    elif risk == "suspicious":
        replies["take_message"] = (
            "I will not transfer a call involving suspicious pressure or sensitive information. "
            "This call will be saved in the account owner's call history."
        )

    identity_note = (
        "Contact number matched in saved address book."
        if caller_known
        else (
            f"Caller self-identified as '{inferred_id['inferred_caller']}' (unverified number)."
            if inferred_id.get("inferred_caller")
            else "Unknown caller identity not independently verified."
        )
    )

    return {
        "intent": matched_intent,
        "urgency": urgency,
        "risk": risk,
        "risk_reasons": reasons,
        "confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "action": action,
        "reply": replies.get(action, replies["take_message"]),
        "summary": f"Caller from {caller_label}: {text[:240]}",
        "provider": "rules",
        "inferred_caller": inferred_id.get("inferred_caller"),
        "inferred_organization": inferred_id.get("inferred_organization"),
        "identity_verified": bool(caller_known),
        "identity_note": identity_note,
    }

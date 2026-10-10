"""Gemini-backed call analysis with validated, deterministic fallbacks."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

try:
    import google.generativeai as genai
except ImportError:  # The web app can still run in offline/demo mode.
    genai = None


logger = logging.getLogger(__name__)
Classification = Literal["Important", "Spam", "General Inquiry"]
Decision = Literal["Handle", "Transfer", "Review"]
RiskLevel = Literal["Low", "Medium", "High"]


def _sentences(value: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", value.strip()) if part]


class CallAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    response: str = Field(min_length=1, max_length=300)
    classification: Classification
    summary: str = Field(min_length=1, max_length=300)
    decision: Decision = "Handle"
    risk_level: RiskLevel = "Medium"
    caller_identity: str = Field(default="Unknown caller", min_length=1, max_length=100)
    decision_reason: str = Field(default="The call needs further context.", min_length=1, max_length=300)

    @field_validator("response")
    @classmethod
    def response_has_at_most_two_sentences(cls, value: str) -> str:
        if len(_sentences(value)) > 2:
            raise ValueError("Response must contain no more than two sentences")
        return value

    @field_validator("summary")
    @classmethod
    def summary_is_one_sentence(cls, value: str) -> str:
        if len(_sentences(value)) > 1:
            raise ValueError("Summary must contain exactly one sentence")
        return value


def _fallback_analysis(transcript: str) -> CallAnalysis:
    normalized = transcript.lower()
    spam_terms = ("scam", "prize", "crypto", "wire transfer", "password", "social security")
    important_terms = ("emergency", "urgent", "hospital", "accident", "deadline", "meeting")
    if any(term in normalized for term in spam_terms):
        classification: Classification = "Spam"
        summary = "The caller used language commonly associated with spam or fraud."
        response = "I cannot share personal or financial information. Please send details through an official channel."
        decision: Decision = "Handle"
        risk_level: RiskLevel = "High"
        decision_reason = "The conversation includes language commonly associated with fraud."
    elif any(term in normalized for term in important_terms):
        classification = "Important"
        summary = "The caller raised a time-sensitive matter that may need follow-up."
        response = "I understand this may be important. I will make sure the caller's message is noted for follow-up."
        decision = "Transfer"
        risk_level = "High"
        decision_reason = "The caller raised a time-sensitive matter that may need your attention."
    else:
        classification = "General Inquiry"
        summary = "The caller shared a general request or inquiry for follow-up."
        response = "Thanks for sharing that. I have noted your message and it can be followed up soon."
        decision = "Handle"
        risk_level = "Low"
        decision_reason = "The request appears suitable for routine agent handling."
    return CallAnalysis(
        response=response,
        classification=classification,
        summary=summary,
        decision=decision,
        risk_level=risk_level,
        decision_reason=decision_reason,
    )


def _transcript_text(transcript: str | list[dict[str, str]]) -> str:
    if isinstance(transcript, str):
        return transcript.strip()[:12000]
    lines = []
    for entry in transcript[-60:]:
        speaker = str(entry.get("speaker", "caller"))[:20]
        text = str(entry.get("text", "")).strip()[:1000]
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines)[:12000]


def analyze_call(
    transcript: str | list[dict[str, str]],
    caller_id: str = "caller",
    context: dict[str, str] | None = None,
) -> CallAnalysis:
    """Analyze a call turn; always return a schema-valid result."""
    text = _transcript_text(transcript)
    caller_context = context or {}
    if not text:
        return _fallback_analysis("")

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or genai is None:
        return _fallback_analysis(text)

    try:
        genai.configure(api_key=api_key)
    except Exception as error:
        logger.warning("Gemini configuration failed; using offline fallback: %s", error)
        return _fallback_analysis(text)
    configured_model = os.getenv("GEMINI_MODEL", "gemini-1.5-pro").strip()
    model_names = list(dict.fromkeys((configured_model, "gemini-1.5-flash", "gemini-2.5-flash")))
    prompt = (
        "You are a concise, careful personal call-screening assistant. Analyze the latest caller message "
        "in context and respond naturally as the recipient's assistant. Classify only as Important, Spam, "
        "or General Inquiry. Important means urgent, personal, or time-sensitive; Spam means unsolicited "
        "fraudulent or clearly unwanted solicitation; otherwise use General Inquiry. Never claim an action "
        "was completed if it was not. Do not guess a caller's identity. If identity is not verified, state "
        "that clearly. Transfer time-sensitive or high-risk personal matters; safely handle obvious spam; "
        "handle routine inquiries. If evidence is ambiguous, recommend Review rather than claiming certainty. "
        "Return only JSON with response (at most two short sentences), classification, summary (one sentence), "
        "decision (Handle, Transfer, Review), risk_level (Low, Medium, High), caller_identity, and decision_reason.\n\n"
        f"Caller ID: {caller_id[:80]}\nVerified contact context: {json.dumps(caller_context, ensure_ascii=False)}"
        f"\nUser preferences: {caller_context.get('preferences', 'No custom preferences provided.')}"
        f"\nCall transcript so far:\n{text}"
    )

    for model_name in model_names:
        try:
            model = genai.GenerativeModel(model_name)
            result = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": CallAnalysis,
                    "temperature": 0.3,
                    "max_output_tokens": 300,
                },
                request_options={"timeout": 20},
            )
            raw_text = getattr(result, "text", "")
            return CallAnalysis.model_validate_json(raw_text)
        except (ValidationError, ValueError, json.JSONDecodeError) as error:
            logger.warning("Gemini response from %s failed schema validation: %s", model_name, error)
        except Exception as error:  # Provider errors should not interrupt a live demo.
            logger.warning("Gemini model %s is unavailable: %s", model_name, error)

    return _fallback_analysis(text)